"""Tank volume service tests: business rules with mocked repositories (no DB)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from tanks.domain import Page, TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume, TankNotFound, TankVolumeNotFound
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.repositories.tank_volume_repository import BaseTankVolumeRepository
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
def tank_volume_service(mock_tank_repository, mock_tank_volume_repository) -> TankVolumeService:
    return TankVolumeService(
        tank_repository=mock_tank_repository,
        tank_volume_repository=mock_tank_volume_repository,
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
        self, tank_volume_service, mock_tank_volume_repository
    ):
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
