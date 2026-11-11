"""Shared fixtures.

Fixtures are function-scoped (pytest's default), so each test gets a fresh object and the
test DB is rolled back after each test. When a test needs a variation, use a factory
fixture with overrides instead of copying a shared object.
"""

import itertools
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from tanks.models import Tank, TankVolume


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


# --- Saved to the DB (tests using these need the db) ----------------------------------------


@pytest.fixture
def tank_factory(db):
    """Create and save a Tank. Override any field with kwargs."""

    def make_tank(**overrides) -> Tank:
        fields = {"name": "Test Tank", "location": "123 Main St", "timezone": "UTC"}
        fields.update(overrides)
        return Tank.objects.create(**fields)

    return make_tank


@pytest.fixture
def tank(tank_factory) -> Tank:
    return tank_factory()


@pytest.fixture
def tank_volume_factory(db):
    """Create and save a TankVolume for the given tank. Override any field with kwargs.

    Default created_at values are one hour apart starting 2023-01-02T00:00Z, so default
    readings never collide on the unique (tank, created_at) constraint.
    """
    start = datetime(2023, 1, 2, tzinfo=UTC)
    default_created_ats = (start + timedelta(hours=hour) for hour in itertools.count())

    def make_tank_volume(tank: Tank, **overrides) -> TankVolume:
        fields = {
            "tank": tank,
            "volume": Decimal("30.00"),
            "created_at": next(default_created_ats),
        }
        fields.update(overrides)
        return TankVolume.objects.create(**fields)

    return make_tank_volume


# --- Never saved (for tests that must not touch the DB) -------------------------------------


@pytest.fixture
def unsaved_tank() -> Tank:
    timestamp = datetime(2026, 1, 2, 10, 0, tzinfo=UTC)
    return Tank(
        id=1,
        name="Test Tank",
        location="123 Main St",
        timezone="UTC",
        created_at=timestamp,
        updated_at=timestamp,
    )


@pytest.fixture
def unsaved_tank_volume() -> TankVolume:
    return TankVolume(
        id=57,
        tank_id=1,
        volume=Decimal("30.00"),
        created_at=datetime(2023, 1, 2, 10, 0, tzinfo=UTC),
        updated_at=datetime(2026, 1, 2, 10, 0, tzinfo=UTC),
    )
