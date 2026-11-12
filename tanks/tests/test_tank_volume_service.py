"""Tank volume service tests: business rules with mocked repositories (no DB)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from tanks.domain import Page, TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume, TankNotFound, TankVolumeNotFound
from tanks.models import TankVolume
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.repositories.tank_volume_repository import BaseTankVolumeRepository
from tanks.services.daily_sales_service import BaseDailySalesService
from tanks.services.tank_volume_service import TankVolumeService

READING_TIME = datetime(2023, 1, 2, 10, tzinfo=UTC)


@pytest.fixture
def mock_tank_repository(unsaved_tank) -> Mock:
    """Defaults to an active tank. Tests set get_by_id.return_value = None for a missing one."""
    tank_repository = Mock(spec=BaseTankRepository)
    tank_repository.get_by_id.return_value = unsaved_tank
    return tank_repository


@pytest.fixture
def mock_tank_volume_repository() -> Mock:
    return Mock(spec=BaseTankVolumeRepository)


@pytest.fixture
def mock_daily_sales_service() -> Mock:
    return Mock(spec=BaseDailySalesService)


@pytest.fixture
def tank_volume_service(
    mock_tank_repository, mock_tank_volume_repository, mock_daily_sales_service, recording_atomic
) -> TankVolumeService:
    return TankVolumeService(
        tank_repository=mock_tank_repository,
        tank_volume_repository=mock_tank_volume_repository,
        daily_sales_service=mock_daily_sales_service,
        atomic=recording_atomic,
    )


class TestListTankVolumes:
    def test_returns_page_from_repository(
        self, tank_volume_service, mock_tank_volume_repository, unsaved_tank_volume
    ):
        page = Page(items=[unsaved_tank_volume], count=1, limit=100, offset=0)
        mock_tank_volume_repository.list_for_tank.return_value = page

        result = tank_volume_service.list_tank_volumes(
            tank_id=1, limit=100, offset=0, start=None, end=None
        )

        assert result is page
        mock_tank_volume_repository.list_for_tank.assert_called_once_with(
            tank_id=1, limit=100, offset=0, start=None, end=None
        )

    def test_bails_early_when_tank_missing(
        self, tank_volume_service, mock_tank_repository, mock_tank_volume_repository
    ):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            tank_volume_service.list_tank_volumes(
                tank_id=999, limit=100, offset=0, start=None, end=None
            )
        mock_tank_volume_repository.list_for_tank.assert_not_called()


class TestCreateTankVolumes:
    def test_creates_when_no_duplicates(
        self, tank_volume_service, mock_tank_volume_repository, unsaved_tank_volume
    ):
        tank_volume_creates = [TankVolumeCreate(volume=Decimal("30"), created_at=READING_TIME)]
        mock_tank_volume_repository.existing_created_ats.return_value = []
        mock_tank_volume_repository.bulk_create.return_value = [unsaved_tank_volume]

        result = tank_volume_service.create_tank_volumes(
            tank_id=1, tank_volume_creates=tank_volume_creates
        )

        assert result == [unsaved_tank_volume]
        mock_tank_volume_repository.existing_created_ats.assert_called_once_with(
            tank_id=1, created_ats=[READING_TIME]
        )
        mock_tank_volume_repository.bulk_create.assert_called_once_with(
            tank_id=1, tank_volume_creates=tank_volume_creates
        )

    def test_raises_on_existing_duplicate_and_creates_nothing(
        self, tank_volume_service, mock_tank_volume_repository
    ):
        mock_tank_volume_repository.existing_created_ats.return_value = [READING_TIME]

        with pytest.raises(DuplicateTankVolume) as raised:
            tank_volume_service.create_tank_volumes(
                tank_id=1,
                tank_volume_creates=[
                    TankVolumeCreate(volume=Decimal("30"), created_at=READING_TIME)
                ],
            )
        assert raised.value.created_ats == [READING_TIME]
        mock_tank_volume_repository.bulk_create.assert_not_called()

    def test_skips_duplicate_check_when_no_timestamps_provided(
        self, tank_volume_service, mock_tank_volume_repository, unsaved_tank_volume
    ):
        mock_tank_volume_repository.bulk_create.return_value = [unsaved_tank_volume]

        tank_volume_service.create_tank_volumes(
            tank_id=1, tank_volume_creates=[TankVolumeCreate(volume=Decimal("30"))]
        )

        mock_tank_volume_repository.existing_created_ats.assert_not_called()
        mock_tank_volume_repository.bulk_create.assert_called_once()

    def test_bails_early_when_tank_missing(
        self, tank_volume_service, mock_tank_repository, mock_tank_volume_repository
    ):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            tank_volume_service.create_tank_volumes(
                tank_id=999, tank_volume_creates=[TankVolumeCreate(volume=Decimal("30"))]
            )
        mock_tank_volume_repository.bulk_create.assert_not_called()


class TestCreateTankVolumesRecalculatesDailySales:
    def test_recalculates_reading_days_and_next_days_inside_transaction(
        self,
        tank_volume_service,
        mock_tank_volume_repository,
        mock_daily_sales_service,
        recording_atomic,
        unsaved_tank,
    ):
        mock_tank_volume_repository.existing_created_ats.return_value = []
        mock_tank_volume_repository.bulk_create.return_value = [
            TankVolume(id=1, tank_id=1, volume=Decimal("30"), created_at=datetime(2023, 1, 2, 10, tzinfo=UTC)),
            TankVolume(id=2, tank_id=1, volume=Decimal("10"), created_at=datetime(2023, 1, 4, 10, tzinfo=UTC)),
        ]
        recalculated_inside_transaction = []
        mock_daily_sales_service.recalculate_days.side_effect = (
            lambda tank, dates: recalculated_inside_transaction.append(recording_atomic.active)
        )

        tank_volume_service.create_tank_volumes(
            tank_id=1,
            tank_volume_creates=[
                TankVolumeCreate(volume=Decimal("30"), created_at=datetime(2023, 1, 2, 10, tzinfo=UTC)),
                TankVolumeCreate(volume=Decimal("10"), created_at=datetime(2023, 1, 4, 10, tzinfo=UTC)),
            ],
        )

        mock_daily_sales_service.recalculate_days.assert_called_once_with(
            unsaved_tank, {date(2023, 1, 2), date(2023, 1, 3), date(2023, 1, 4), date(2023, 1, 5)}
        )
        assert recalculated_inside_transaction == [True]

    def test_affected_days_use_tank_local_date(
        self, tank_volume_service, mock_tank_volume_repository, mock_daily_sales_service, unsaved_tank
    ):
        unsaved_tank.timezone = "America/Chicago"
        reading_time = datetime(2023, 1, 3, 2, tzinfo=UTC)  # Jan 2, 20:00 in Chicago
        mock_tank_volume_repository.existing_created_ats.return_value = []
        mock_tank_volume_repository.bulk_create.return_value = [
            TankVolume(id=1, tank_id=1, volume=Decimal("30"), created_at=reading_time)
        ]

        tank_volume_service.create_tank_volumes(
            tank_id=1,
            tank_volume_creates=[TankVolumeCreate(volume=Decimal("30"), created_at=reading_time)],
        )

        mock_daily_sales_service.recalculate_days.assert_called_once_with(
            unsaved_tank, {date(2023, 1, 2), date(2023, 1, 3)}
        )

    def test_no_recalculation_when_insert_fails(
        self, tank_volume_service, mock_tank_volume_repository, mock_daily_sales_service
    ):
        mock_tank_volume_repository.existing_created_ats.return_value = []
        mock_tank_volume_repository.bulk_create.side_effect = DuplicateTankVolume(1)

        with pytest.raises(DuplicateTankVolume):
            tank_volume_service.create_tank_volumes(
                tank_id=1,
                tank_volume_creates=[TankVolumeCreate(volume=Decimal("30"), created_at=READING_TIME)],
            )
        mock_daily_sales_service.recalculate_days.assert_not_called()

    def test_no_recalculation_when_duplicate_found_up_front(
        self, tank_volume_service, mock_tank_volume_repository, mock_daily_sales_service
    ):
        mock_tank_volume_repository.existing_created_ats.return_value = [READING_TIME]

        with pytest.raises(DuplicateTankVolume):
            tank_volume_service.create_tank_volumes(
                tank_id=1,
                tank_volume_creates=[TankVolumeCreate(volume=Decimal("30"), created_at=READING_TIME)],
            )
        mock_daily_sales_service.recalculate_days.assert_not_called()


class TestUpdateTankVolume:
    def test_updates_reading_belonging_to_tank(
        self, tank_volume_service, mock_tank_volume_repository, unsaved_tank_volume
    ):
        mock_tank_volume_repository.get_for_tank.return_value = unsaved_tank_volume
        mock_tank_volume_repository.update_volume.return_value = unsaved_tank_volume

        result = tank_volume_service.update_tank_volume(
            tank_id=1, tank_volume_id=57, volume=Decimal("12.50")
        )

        assert result is unsaved_tank_volume
        mock_tank_volume_repository.get_for_tank.assert_called_once_with(
            tank_id=1, tank_volume_id=57
        )
        mock_tank_volume_repository.update_volume.assert_called_once_with(
            unsaved_tank_volume, volume=Decimal("12.50")
        )

    def test_raises_when_reading_missing_or_on_another_tank(
        self, tank_volume_service, mock_tank_volume_repository
    ):
        mock_tank_volume_repository.get_for_tank.return_value = None

        with pytest.raises(TankVolumeNotFound):
            tank_volume_service.update_tank_volume(
                tank_id=1, tank_volume_id=57, volume=Decimal("12.50")
            )
        mock_tank_volume_repository.update_volume.assert_not_called()

    def test_bails_early_when_tank_missing(
        self, tank_volume_service, mock_tank_repository, mock_tank_volume_repository
    ):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            tank_volume_service.update_tank_volume(
                tank_id=999, tank_volume_id=57, volume=Decimal("12.50")
            )
        mock_tank_volume_repository.get_for_tank.assert_not_called()


class TestDeleteTankVolume:
    def test_deletes_reading_belonging_to_tank(
        self, tank_volume_service, mock_tank_volume_repository, unsaved_tank_volume
    ):
        mock_tank_volume_repository.get_for_tank.return_value = unsaved_tank_volume

        tank_volume_service.delete_tank_volume(tank_id=1, tank_volume_id=57)

        mock_tank_volume_repository.delete.assert_called_once_with(unsaved_tank_volume)

    def test_raises_when_reading_missing_or_on_another_tank(
        self, tank_volume_service, mock_tank_volume_repository
    ):
        mock_tank_volume_repository.get_for_tank.return_value = None

        with pytest.raises(TankVolumeNotFound):
            tank_volume_service.delete_tank_volume(tank_id=1, tank_volume_id=57)
        mock_tank_volume_repository.delete.assert_not_called()


# unsaved_tank_volume.created_at is 2023-01-02T10:00Z, so the affected days are Jan 2 and Jan 3.
JAN_2_AND_3 = {date(2023, 1, 2), date(2023, 1, 3)}


def run_operation(tank_volume_service, operation: str) -> None:
    if operation == "update":
        tank_volume_service.update_tank_volume(tank_id=1, tank_volume_id=57, volume=Decimal("12.50"))
    else:
        tank_volume_service.delete_tank_volume(tank_id=1, tank_volume_id=57)


@pytest.mark.parametrize("operation", ["update", "delete"])
class TestCorrectionsRecalculateDailySales:
    """Part 3: PATCH and DELETE refresh the affected daily totals in the same transaction."""

    def test_recalculates_reading_day_and_next_day_inside_transaction(
        self,
        tank_volume_service,
        mock_tank_volume_repository,
        mock_daily_sales_service,
        recording_atomic,
        unsaved_tank,
        unsaved_tank_volume,
        operation,
    ):
        mock_tank_volume_repository.get_for_tank.return_value = unsaved_tank_volume
        mock_tank_volume_repository.update_volume.return_value = unsaved_tank_volume
        recalculated_inside_transaction = []
        mock_daily_sales_service.recalculate_days.side_effect = (
            lambda tank, dates: recalculated_inside_transaction.append(recording_atomic.active)
        )

        run_operation(tank_volume_service, operation)

        mock_daily_sales_service.recalculate_days.assert_called_once_with(unsaved_tank, JAN_2_AND_3)
        assert recalculated_inside_transaction == [True]

    def test_affected_days_use_tank_local_date(
        self,
        tank_volume_service,
        mock_tank_volume_repository,
        mock_daily_sales_service,
        unsaved_tank,
        unsaved_tank_volume,
        operation,
    ):
        unsaved_tank.timezone = "America/Chicago"
        unsaved_tank_volume.created_at = datetime(2023, 1, 3, 2, tzinfo=UTC)  # Jan 2 in Chicago
        mock_tank_volume_repository.get_for_tank.return_value = unsaved_tank_volume
        mock_tank_volume_repository.update_volume.return_value = unsaved_tank_volume

        run_operation(tank_volume_service, operation)

        mock_daily_sales_service.recalculate_days.assert_called_once_with(unsaved_tank, JAN_2_AND_3)

    def test_no_recalculation_when_reading_not_found(
        self, tank_volume_service, mock_tank_volume_repository, mock_daily_sales_service, operation
    ):
        mock_tank_volume_repository.get_for_tank.return_value = None

        with pytest.raises(TankVolumeNotFound):
            run_operation(tank_volume_service, operation)
        mock_daily_sales_service.recalculate_days.assert_not_called()

    def test_no_recalculation_when_tank_not_found(
        self,
        tank_volume_service,
        mock_tank_repository,
        mock_daily_sales_service,
        operation,
    ):
        mock_tank_repository.get_by_id.return_value = None

        with pytest.raises(TankNotFound):
            run_operation(tank_volume_service, operation)
        mock_daily_sales_service.recalculate_days.assert_not_called()

    def test_no_recalculation_when_write_fails(
        self,
        tank_volume_service,
        mock_tank_volume_repository,
        mock_daily_sales_service,
        unsaved_tank_volume,
        operation,
    ):
        mock_tank_volume_repository.get_for_tank.return_value = unsaved_tank_volume
        mock_tank_volume_repository.update_volume.side_effect = RuntimeError("db down")
        mock_tank_volume_repository.delete.side_effect = RuntimeError("db down")

        with pytest.raises(RuntimeError):
            run_operation(tank_volume_service, operation)
        mock_daily_sales_service.recalculate_days.assert_not_called()


def test_delete_uses_timestamp_captured_before_deleting(
    tank_volume_service,
    mock_tank_volume_repository,
    mock_daily_sales_service,
    unsaved_tank,
    unsaved_tank_volume,
):
    mock_tank_volume_repository.get_for_tank.return_value = unsaved_tank_volume

    def delete_and_clear(tank_volume):
        tank_volume.created_at = None  # the row (and its timestamp) is gone after delete

    mock_tank_volume_repository.delete.side_effect = delete_and_clear

    tank_volume_service.delete_tank_volume(tank_id=1, tank_volume_id=57)

    mock_daily_sales_service.recalculate_days.assert_called_once_with(unsaved_tank, JAN_2_AND_3)
