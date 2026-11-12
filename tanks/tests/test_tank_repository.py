"""Tank repository tests: run against the real test database."""

import pytest
from django.utils import timezone

from tanks.domain import TankCreate, TankUpdate
from tanks.models import Tank
from tanks.repositories.tank_repository import TankRepository

pytestmark = pytest.mark.django_db


@pytest.fixture
def tank_repository() -> TankRepository:
    return TankRepository()


class TestGetById:
    def test_returns_active_tank(self, tank_repository, tank):
        assert tank_repository.get_by_id(tank.id) == tank

    def test_returns_none_for_missing_id(self, tank_repository):
        assert tank_repository.get_by_id(999) is None

    def test_returns_none_for_soft_deleted_tank(self, tank_repository, tank_factory):
        deleted_tank = tank_factory(deleted_at=timezone.now())

        assert tank_repository.get_by_id(deleted_tank.id) is None


class TestListActive:
    def test_excludes_soft_deleted_and_orders_by_tank_id(self, tank_repository, tank_factory):
        first_tank = tank_factory(name="First")
        tank_factory(name="Deleted", deleted_at=timezone.now())
        third_tank = tank_factory(name="Third")

        page = tank_repository.list_active(limit=100, offset=0)

        assert page.items == [first_tank, third_tank]
        assert page.count == 2

    def test_applies_limit_and_offset_and_counts_all(self, tank_repository, tank_factory):
        tanks = [tank_factory(name=f"Tank {number}") for number in range(5)]

        page = tank_repository.list_active(limit=2, offset=1)

        assert page.items == tanks[1:3]
        assert (page.count, page.limit, page.offset) == (5, 2, 1)


class TestListActiveByIds:
    def test_none_returns_all_active_tanks_in_order(self, tank_repository, tank_factory):
        first_tank = tank_factory(name="First")
        tank_factory(name="Deleted", deleted_at=timezone.now())
        second_tank = tank_factory(name="Second")

        assert tank_repository.list_active_by_ids(None) == [first_tank, second_tank]

    def test_filters_by_ids_and_skips_unknown_and_deleted(self, tank_repository, tank_factory):
        wanted_tank = tank_factory(name="Wanted")
        deleted_tank = tank_factory(name="Deleted", deleted_at=timezone.now())
        tank_factory(name="Not requested")

        tanks = tank_repository.list_active_by_ids([wanted_tank.id, deleted_tank.id, 999])

        assert tanks == [wanted_tank]


class TestCreate:
    def test_persists_tank(self, tank_repository):
        tank = tank_repository.create(
            TankCreate(name="New Tank", location="456 Oak Ave", timezone="America/Chicago")
        )

        saved_tank = Tank.objects.get(id=tank.id)
        assert (saved_tank.name, saved_tank.location, saved_tank.timezone) == (
            "New Tank",
            "456 Oak Ave",
            "America/Chicago",
        )
        assert saved_tank.deleted_at is None


class TestUpdate:
    def test_changes_only_provided_fields(self, tank_repository, tank_factory):
        tank = tank_factory(name="Old Name", location="Old Location")

        tank_repository.update(tank, TankUpdate(name="New Name"))

        tank.refresh_from_db()
        assert tank.name == "New Name"
        assert tank.location == "Old Location"

    def test_no_provided_fields_is_a_no_op(self, tank_repository, tank):
        original_updated_at = tank.updated_at

        tank_repository.update(tank, TankUpdate())

        tank.refresh_from_db()
        assert tank.updated_at == original_updated_at


class TestSoftDelete:
    def test_sets_deleted_at_and_keeps_readings(
        self, tank_repository, tank, tank_volume_factory
    ):
        tank_volume_factory(tank)
        deleted_at = timezone.now()

        tank_repository.soft_delete(tank, deleted_at=deleted_at)

        tank.refresh_from_db()
        assert tank.deleted_at == deleted_at
        assert tank.volumes.count() == 1
