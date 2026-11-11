"""Tank volume repository tests: run against the real test database."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tanks.domain import TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume
from tanks.models import TankVolume
from tanks.repositories.tank_volume_repository import TankVolumeRepository

pytestmark = pytest.mark.django_db

JAN_2 = datetime(2023, 1, 2, tzinfo=UTC)
JAN_3 = datetime(2023, 1, 3, tzinfo=UTC)
JAN_4 = datetime(2023, 1, 4, tzinfo=UTC)


@pytest.fixture
def tank_volume_repository() -> TankVolumeRepository:
    return TankVolumeRepository()


class TestGetForTank:
    def test_returns_reading_belonging_to_tank(
        self, tank_volume_repository, tank, tank_volume_factory
    ):
        tank_volume = tank_volume_factory(tank)

        assert tank_volume_repository.get_for_tank(tank.id, tank_volume.id) == tank_volume

    def test_returns_none_when_reading_belongs_to_another_tank(
        self, tank_volume_repository, tank_factory, tank_volume_factory
    ):
        tank = tank_factory(name="Mine")
        other_tank = tank_factory(name="Other")
        other_tank_volume = tank_volume_factory(other_tank)

        assert tank_volume_repository.get_for_tank(tank.id, other_tank_volume.id) is None

    def test_returns_none_for_missing_id(self, tank_volume_repository, tank):
        assert tank_volume_repository.get_for_tank(tank.id, 999) is None


class TestListForTank:
    def test_orders_by_created_at_and_scopes_to_tank(
        self, tank_volume_repository, tank_factory, tank_volume_factory
    ):
        tank = tank_factory(name="Mine")
        other_tank = tank_factory(name="Other")
        later = tank_volume_factory(tank, created_at=JAN_3)
        earlier = tank_volume_factory(tank, created_at=JAN_2)
        tank_volume_factory(other_tank, created_at=JAN_2)

        page = tank_volume_repository.list_for_tank(
            tank.id, limit=100, offset=0, start=None, end=None
        )

        assert page.items == [earlier, later]
        assert page.count == 2

    def test_start_is_inclusive_and_end_is_exclusive(
        self, tank_volume_repository, tank, tank_volume_factory
    ):
        tank_volume_factory(tank, created_at=JAN_2)
        on_start = tank_volume_factory(tank, created_at=JAN_3)
        tank_volume_factory(tank, created_at=JAN_4)

        page = tank_volume_repository.list_for_tank(
            tank.id, limit=100, offset=0, start=JAN_3, end=JAN_4
        )

        assert page.items == [on_start]
        assert page.count == 1

    def test_applies_limit_and_offset_and_counts_all(
        self, tank_volume_repository, tank, tank_volume_factory
    ):
        tank_volumes = [tank_volume_factory(tank) for _ in range(5)]

        page = tank_volume_repository.list_for_tank(
            tank.id, limit=2, offset=1, start=None, end=None
        )

        assert page.items == tank_volumes[1:3]
        assert page.count == 5


class TestExistingCreatedAts:
    def test_returns_only_timestamps_already_saved_for_tank(
        self, tank_volume_repository, tank_factory, tank_volume_factory
    ):
        tank = tank_factory(name="Mine")
        other_tank = tank_factory(name="Other")
        tank_volume_factory(tank, created_at=JAN_2)
        tank_volume_factory(other_tank, created_at=JAN_3)

        existing = tank_volume_repository.existing_created_ats(tank.id, [JAN_2, JAN_3, JAN_4])

        assert existing == [JAN_2]


class TestBulkCreate:
    def test_creates_all_in_request_order_with_ids(self, tank_volume_repository, tank):
        tank_volumes = tank_volume_repository.bulk_create(
            tank.id,
            [
                TankVolumeCreate(volume=Decimal("30"), created_at=JAN_3),
                TankVolumeCreate(volume=Decimal("10"), created_at=JAN_2),
            ],
        )

        assert [tank_volume.created_at for tank_volume in tank_volumes] == [JAN_3, JAN_2]
        assert all(tank_volume.id is not None for tank_volume in tank_volumes)
        assert TankVolume.objects.filter(tank=tank).count() == 2

    def test_missing_created_at_defaults_to_now(self, tank_volume_repository, tank):
        before = datetime.now(UTC)

        (tank_volume,) = tank_volume_repository.bulk_create(
            tank.id, [TankVolumeCreate(volume=Decimal("30"))]
        )

        assert tank_volume.created_at >= before

    def test_duplicate_raises_and_saves_nothing(
        self, tank_volume_repository, tank, tank_volume_factory
    ):
        tank_volume_factory(tank, created_at=JAN_2)

        with pytest.raises(DuplicateTankVolume):
            tank_volume_repository.bulk_create(
                tank.id,
                [
                    TankVolumeCreate(volume=Decimal("30"), created_at=JAN_3),
                    TankVolumeCreate(volume=Decimal("10"), created_at=JAN_2),
                ],
            )

        assert TankVolume.objects.filter(tank=tank).count() == 1


class TestUpdateVolume:
    def test_changes_volume_only(self, tank_volume_repository, tank, tank_volume_factory):
        tank_volume = tank_volume_factory(tank, volume=Decimal("30.00"), created_at=JAN_2)

        tank_volume_repository.update_volume(tank_volume, volume=Decimal("12.50"))

        tank_volume.refresh_from_db()
        assert tank_volume.volume == Decimal("12.50")
        assert tank_volume.created_at == JAN_2


class TestDelete:
    def test_removes_reading(self, tank_volume_repository, tank, tank_volume_factory):
        tank_volume = tank_volume_factory(tank)

        tank_volume_repository.delete(tank_volume)

        assert not TankVolume.objects.filter(id=tank_volume.id).exists()
