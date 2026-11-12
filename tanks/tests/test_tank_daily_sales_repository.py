"""Tank daily sales repository tests: run against the real test database."""

from datetime import date
from decimal import Decimal

import pytest

from tanks.domain import DailySalesResult
from tanks.models import TankDailySales
from tanks.repositories.tank_daily_sales_repository import TankDailySalesRepository

pytestmark = pytest.mark.django_db

JAN_2, JAN_3, JAN_4, JAN_5 = (date(2023, 1, day) for day in (2, 3, 4, 5))


@pytest.fixture
def tank_daily_sales_repository() -> TankDailySalesRepository:
    return TankDailySalesRepository()


def stored(tank) -> dict[date, tuple[Decimal, bool]]:
    return {
        row.date: (row.daily_total_sales, row.fuel_load_received)
        for row in TankDailySales.objects.filter(tank=tank)
    }


class TestListForTanks:
    def test_filters_by_tanks_and_inclusive_dates(
        self, tank_daily_sales_repository, tank_factory, tank_daily_sales_factory
    ):
        tank = tank_factory(name="Mine")
        other_tank = tank_factory(name="Other")
        excluded_tank = tank_factory(name="Excluded")
        before_range = tank_daily_sales_factory(tank, JAN_2)
        first_day = tank_daily_sales_factory(tank, JAN_3)
        last_day = tank_daily_sales_factory(tank, JAN_4)
        other_tank_row = tank_daily_sales_factory(other_tank, JAN_3)
        tank_daily_sales_factory(excluded_tank, JAN_3)

        rows = tank_daily_sales_repository.list_for_tanks([tank.id, other_tank.id], JAN_3, JAN_4)

        assert rows == [first_day, last_day, other_tank_row]
        assert before_range not in rows


class TestReplaceForDates:
    def test_replaces_rows_removes_dates_without_results_and_leaves_others(
        self, tank_daily_sales_repository, tank, tank_daily_sales_factory
    ):
        tank_daily_sales_factory(tank, JAN_2, daily_total_sales=Decimal("99"))  # outside dates
        tank_daily_sales_factory(tank, JAN_3, daily_total_sales=Decimal("1"))  # replaced
        tank_daily_sales_factory(tank, JAN_4, daily_total_sales=Decimal("2"))  # no longer has readings

        tank_daily_sales_repository.replace_for_dates(
            tank_id=tank.id,
            dates={JAN_3, JAN_4, JAN_5},
            results={
                JAN_3: DailySalesResult(daily_total_sales=Decimal("20"), fuel_load_received=True),
                JAN_5: DailySalesResult(daily_total_sales=Decimal("5"), fuel_load_received=False),
            },
        )

        assert stored(tank) == {
            JAN_2: (Decimal("99.00"), False),
            JAN_3: (Decimal("20.00"), True),
            JAN_5: (Decimal("5.00"), False),
        }

    def test_ignores_results_outside_dates(self, tank_daily_sales_repository, tank):
        tank_daily_sales_repository.replace_for_dates(
            tank_id=tank.id,
            dates={JAN_3},
            results={
                JAN_3: DailySalesResult(daily_total_sales=Decimal("1"), fuel_load_received=False),
                JAN_4: DailySalesResult(daily_total_sales=Decimal("2"), fuel_load_received=False),
            },
        )

        assert list(stored(tank)) == [JAN_3]

    def test_only_touches_the_given_tank(
        self, tank_daily_sales_repository, tank_factory, tank_daily_sales_factory
    ):
        tank = tank_factory(name="Mine")
        other_tank = tank_factory(name="Other")
        tank_daily_sales_factory(other_tank, JAN_3, daily_total_sales=Decimal("7"))

        tank_daily_sales_repository.replace_for_dates(tank_id=tank.id, dates={JAN_3}, results={})

        assert stored(other_tank) == {JAN_3: (Decimal("7.00"), False)}


class TestDeleteForTank:
    def test_removes_only_that_tanks_rows(
        self, tank_daily_sales_repository, tank_factory, tank_daily_sales_factory
    ):
        tank = tank_factory(name="Mine")
        other_tank = tank_factory(name="Other")
        tank_daily_sales_factory(tank, JAN_2)
        tank_daily_sales_factory(other_tank, JAN_2)

        tank_daily_sales_repository.delete_for_tank(tank.id)

        assert stored(tank) == {}
        assert list(stored(other_tank)) == [JAN_2]


class TestUniqueConstraint:
    def test_one_row_per_tank_per_date(self, tank, tank_daily_sales_factory):
        from django.db import IntegrityError, transaction

        tank_daily_sales_factory(tank, JAN_2)

        with pytest.raises(IntegrityError), transaction.atomic():
            tank_daily_sales_factory(tank, JAN_2)
