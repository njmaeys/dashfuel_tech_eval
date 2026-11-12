"""Tank service tests: business rules with a mocked repository (no DB).

Pure passthroughs (list_tanks, create_tank) aren't tested here; the API and repository tests
cover both ends of them.
"""

from unittest.mock import Mock

import pytest

from tanks.domain import TankUpdate
from tanks.exceptions import TankNotFound
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.services.daily_sales_service import BaseDailySalesService
from tanks.services.tank_service import TankService


@pytest.fixture
def mock_tank_repository() -> Mock:
    return Mock(spec=BaseTankRepository)


@pytest.fixture
def mock_daily_sales_service() -> Mock:
    return Mock(spec=BaseDailySalesService)


@pytest.fixture
def tank_service(mock_tank_repository, mock_daily_sales_service, recording_atomic) -> TankService:
    return TankService(
        repository=mock_tank_repository,
        daily_sales_service=mock_daily_sales_service,
        atomic=recording_atomic,
    )


class TestGetTank:
    def test_returns_tank_from_repository(self, tank_service, mock_tank_repository, unsaved_tank):
        mock_tank_repository.get_by_id.return_value = unsaved_tank

        assert tank_service.get_tank(1) is unsaved_tank
        mock_tank_repository.get_by_id.assert_called_once_with(1)

    def test_raises_when_tank_missing(self, tank_service, mock_tank_repository):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            tank_service.get_tank(999)


class TestUpdateTank:
    def test_updates_existing_tank(self, tank_service, mock_tank_repository, unsaved_tank):
        mock_tank_repository.get_by_id.return_value = unsaved_tank
        mock_tank_repository.update.return_value = unsaved_tank
        tank_update = TankUpdate(name="Renamed")

        assert tank_service.update_tank(1, tank_update) is unsaved_tank
        mock_tank_repository.update.assert_called_once_with(unsaved_tank, tank_update)

    def test_bails_early_when_tank_missing(self, tank_service, mock_tank_repository):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            tank_service.update_tank(999, TankUpdate(name="Renamed"))
        mock_tank_repository.update.assert_not_called()

    def test_timezone_change_rebuilds_daily_sales_inside_transaction(
        self,
        tank_service,
        mock_tank_repository,
        mock_daily_sales_service,
        recording_atomic,
        unsaved_tank,
    ):
        mock_tank_repository.get_by_id.return_value = unsaved_tank  # timezone "UTC"
        mock_tank_repository.update.return_value = unsaved_tank
        mock_daily_sales_service.recalculate_all_days.side_effect = (
            lambda tank: assert_inside_transaction(recording_atomic)
        )

        tank_service.update_tank(1, TankUpdate(timezone="America/Chicago"))

        mock_daily_sales_service.recalculate_all_days.assert_called_once_with(unsaved_tank)

    @pytest.mark.parametrize(
        "tank_update",
        [
            pytest.param(TankUpdate(name="Renamed"), id="other field"),
            pytest.param(TankUpdate(timezone="UTC"), id="same timezone"),
        ],
    )
    def test_no_rebuild_when_timezone_unchanged(
        self, tank_service, mock_tank_repository, mock_daily_sales_service, unsaved_tank, tank_update
    ):
        mock_tank_repository.get_by_id.return_value = unsaved_tank  # timezone "UTC"
        mock_tank_repository.update.return_value = unsaved_tank

        tank_service.update_tank(1, tank_update)

        mock_daily_sales_service.recalculate_all_days.assert_not_called()


def assert_inside_transaction(recording_atomic) -> None:
    assert recording_atomic.active, "expected to run inside the service's transaction"


class TestDeleteTank:
    def test_soft_deletes_with_current_utc_time(
        self, tank_service, mock_tank_repository, unsaved_tank
    ):
        mock_tank_repository.get_by_id.return_value = unsaved_tank

        tank_service.delete_tank(1)

        mock_tank_repository.soft_delete.assert_called_once()
        (soft_deleted_tank,) = mock_tank_repository.soft_delete.call_args.args
        deleted_at = mock_tank_repository.soft_delete.call_args.kwargs["deleted_at"]
        assert soft_deleted_tank is unsaved_tank
        assert deleted_at.utcoffset().total_seconds() == 0

    def test_bails_early_when_tank_missing(self, tank_service, mock_tank_repository):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            tank_service.delete_tank(999)
        mock_tank_repository.soft_delete.assert_not_called()
