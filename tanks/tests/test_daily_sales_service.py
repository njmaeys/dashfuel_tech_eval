"""Daily sales service tests: orchestration with mocked repositories (no DB).

The sales math itself is covered in test_sales_calculations.py; these tests check which data
the service asks for, what it stores, and what it returns.
"""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import Mock

import pytest

from tanks.domain import DailySalesResult, DailySalesRow, RecalculationSummary
from tanks.models import Tank, TankDailySales, TankVolume
from tanks.repositories.tank_daily_sales_repository import BaseTankDailySalesRepository
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.repositories.tank_volume_repository import BaseTankVolumeRepository
from tanks.services.daily_sales_service import DailySalesService

JAN_2, JAN_3, JAN_4, JAN_5 = (date(2023, 1, day) for day in (2, 3, 4, 5))  # Monday..Thursday


def reading(created_at: datetime, volume: str) -> TankVolume:
    return TankVolume(tank_id=1, created_at=created_at, volume=Decimal(volume))


def stored_row(tank_id: int, day: date, total: str, fuel_load_received: bool = False) -> TankDailySales:
    return TankDailySales(
        tank_id=tank_id,
        date=day,
        daily_total_sales=Decimal(total),
        fuel_load_received=fuel_load_received,
    )


@pytest.fixture
def mock_tank_repository() -> Mock:
    return Mock(spec=BaseTankRepository)


@pytest.fixture
def mock_tank_volume_repository() -> Mock:
    tank_volume_repository = Mock(spec=BaseTankVolumeRepository)
    tank_volume_repository.list_in_range.return_value = []
    return tank_volume_repository


@pytest.fixture
def mock_tank_daily_sales_repository() -> Mock:
    return Mock(spec=BaseTankDailySalesRepository)


@pytest.fixture
def daily_sales_service(
    mock_tank_repository,
    mock_tank_volume_repository,
    mock_tank_daily_sales_repository,
    recording_atomic,
) -> DailySalesService:
    return DailySalesService(
        tank_repository=mock_tank_repository,
        tank_volume_repository=mock_tank_volume_repository,
        tank_daily_sales_repository=mock_tank_daily_sales_repository,
        atomic=recording_atomic,
    )


class TestRecalculateDays:
    def test_queries_readings_from_the_day_before_the_first_date(
        self, daily_sales_service, mock_tank_volume_repository, unsaved_tank
    ):
        daily_sales_service.recalculate_days(unsaved_tank, {JAN_3, JAN_4})

        mock_tank_volume_repository.list_in_range.assert_called_once_with(
            tank_id=1,
            start_at=datetime(2023, 1, 2, tzinfo=UTC),
            end_at=datetime(2023, 1, 5, tzinfo=UTC),
        )

    def test_query_window_uses_tank_timezone(
        self, daily_sales_service, mock_tank_volume_repository, unsaved_tank
    ):
        unsaved_tank.timezone = "America/Chicago"  # UTC-6 in January

        daily_sales_service.recalculate_days(unsaved_tank, {JAN_3})

        mock_tank_volume_repository.list_in_range.assert_called_once_with(
            tank_id=1,
            start_at=datetime(2023, 1, 2, 6, tzinfo=UTC),
            end_at=datetime(2023, 1, 4, 6, tzinfo=UTC),
        )

    def test_stores_calculated_results_for_requested_dates(
        self,
        daily_sales_service,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        unsaved_tank,
    ):
        mock_tank_volume_repository.list_in_range.return_value = [
            reading(datetime(2023, 1, 2, 10, tzinfo=UTC), "30"),
            reading(datetime(2023, 1, 2, 11, tzinfo=UTC), "10"),
            reading(datetime(2023, 1, 3, 9, tzinfo=UTC), "20"),
            reading(datetime(2023, 1, 3, 15, tzinfo=UTC), "45"),
        ]

        rows_stored = daily_sales_service.recalculate_days(unsaved_tank, {JAN_2, JAN_3})

        mock_tank_daily_sales_repository.replace_for_dates.assert_called_once_with(
            tank_id=1,
            dates={JAN_2, JAN_3},
            results={
                JAN_2: DailySalesResult(daily_total_sales=Decimal("20"), fuel_load_received=False),
                JAN_3: DailySalesResult(daily_total_sales=Decimal("0"), fuel_load_received=True),
            },
        )
        assert rows_stored == 2

    def test_groups_readings_by_tank_local_date(
        self,
        daily_sales_service,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        unsaved_tank,
    ):
        unsaved_tank.timezone = "America/Chicago"
        mock_tank_volume_repository.list_in_range.return_value = [
            reading(datetime(2023, 1, 3, 2, tzinfo=UTC), "30"),  # Jan 2, 20:00 local
            reading(datetime(2023, 1, 3, 15, tzinfo=UTC), "10"),  # Jan 3, 09:00 local
        ]

        daily_sales_service.recalculate_days(unsaved_tank, {JAN_3})

        # In UTC both readings would be Jan 3. Locally, Jan 3's first reading follows Jan 2's 30.
        results = mock_tank_daily_sales_repository.replace_for_dates.call_args.kwargs["results"]
        assert results == {
            JAN_3: DailySalesResult(daily_total_sales=Decimal("20"), fuel_load_received=False)
        }

    def test_date_without_readings_gets_no_row(
        self,
        daily_sales_service,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        unsaved_tank,
    ):
        mock_tank_volume_repository.list_in_range.return_value = [
            reading(datetime(2023, 1, 4, 10, tzinfo=UTC), "30"),
        ]

        rows_stored = daily_sales_service.recalculate_days(unsaved_tank, {JAN_5})

        mock_tank_daily_sales_repository.replace_for_dates.assert_called_once_with(
            tank_id=1, dates={JAN_5}, results={}
        )
        assert rows_stored == 0

    def test_no_dates_does_nothing(
        self,
        daily_sales_service,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        unsaved_tank,
    ):
        assert daily_sales_service.recalculate_days(unsaved_tank, set()) == 0
        mock_tank_volume_repository.list_in_range.assert_not_called()
        mock_tank_daily_sales_repository.replace_for_dates.assert_not_called()


class TestRecalculateAllDays:
    def test_clears_then_rebuilds_from_first_to_last_reading(
        self,
        daily_sales_service,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        unsaved_tank,
    ):
        mock_tank_volume_repository.date_range_utc.return_value = (
            datetime(2023, 1, 2, 10, tzinfo=UTC),
            datetime(2023, 1, 5, 11, tzinfo=UTC),
        )

        daily_sales_service.recalculate_all_days(unsaved_tank)

        mock_tank_daily_sales_repository.delete_for_tank.assert_called_once_with(1)
        dates = mock_tank_daily_sales_repository.replace_for_dates.call_args.kwargs["dates"]
        assert dates == {JAN_2, JAN_3, JAN_4, JAN_5}

    def test_tank_without_readings_only_clears(
        self,
        daily_sales_service,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        unsaved_tank,
    ):
        mock_tank_volume_repository.date_range_utc.return_value = None

        assert daily_sales_service.recalculate_all_days(unsaved_tank) == 0
        mock_tank_daily_sales_repository.delete_for_tank.assert_called_once_with(1)
        mock_tank_daily_sales_repository.replace_for_dates.assert_not_called()


class TestRecalculateRange:
    def test_recalculates_every_date_for_each_tank_inside_transaction(
        self,
        daily_sales_service,
        mock_tank_repository,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
        recording_atomic,
    ):
        tanks = [Tank(id=1, timezone="UTC"), Tank(id=2, timezone="UTC")]
        mock_tank_repository.list_active_by_ids.return_value = tanks
        mock_tank_volume_repository.list_in_range.side_effect = lambda tank_id, start_at, end_at: (
            [reading(datetime(2023, 1, 2, 10, tzinfo=UTC), "30")] if tank_id == 1 else []
        )
        replaced_inside_transaction = []
        mock_tank_daily_sales_repository.replace_for_dates.side_effect = (
            lambda **kwargs: replaced_inside_transaction.append(recording_atomic.active)
        )

        summary = daily_sales_service.recalculate_range(JAN_2, JAN_3, tank_ids=[1, 2, 99])

        mock_tank_repository.list_active_by_ids.assert_called_once_with([1, 2, 99])
        replaced_dates = [
            call.kwargs["dates"]
            for call in mock_tank_daily_sales_repository.replace_for_dates.call_args_list
        ]
        assert replaced_dates == [{JAN_2, JAN_3}, {JAN_2, JAN_3}]
        assert replaced_inside_transaction == [True, True]
        assert summary == RecalculationSummary(
            start_date=JAN_2, end_date=JAN_3, tank_ids=[1, 2], days_with_sales_rows=1
        )


class TestGetDailySales:
    def test_fetches_stored_rows_from_monday_of_start_week(
        self, daily_sales_service, mock_tank_repository, mock_tank_daily_sales_repository
    ):
        mock_tank_repository.list_active_by_ids.return_value = [Tank(id=1, timezone="UTC")]
        mock_tank_daily_sales_repository.list_for_tanks.return_value = []

        daily_sales_service.get_daily_sales(JAN_4, JAN_5, tank_ids=None)  # Wednesday..Thursday

        mock_tank_repository.list_active_by_ids.assert_called_once_with(None)
        mock_tank_daily_sales_repository.list_for_tanks.assert_called_once_with(
            tank_ids=[1], start_date=JAN_2, end_date=JAN_5
        )

    def test_returns_only_requested_dates_with_zeros_and_averages(
        self, daily_sales_service, mock_tank_repository, mock_tank_daily_sales_repository
    ):
        mock_tank_repository.list_active_by_ids.return_value = [Tank(id=1, timezone="UTC")]
        mock_tank_daily_sales_repository.list_for_tanks.return_value = [
            stored_row(1, JAN_2, "20"),
            # No Jan 3 row: no readings that day.
            stored_row(1, JAN_4, "20", fuel_load_received=True),
        ]

        daily_sales_rows = daily_sales_service.get_daily_sales(JAN_3, JAN_5, tank_ids=[1])

        assert daily_sales_rows == [
            DailySalesRow(1, JAN_3, Decimal("0"), Decimal("10.00"), False),
            DailySalesRow(1, JAN_4, Decimal("20"), Decimal("13.33"), True),
            DailySalesRow(1, JAN_5, Decimal("0"), Decimal("10.00"), False),
        ]

    def test_returns_every_date_for_each_tank_in_tank_order(
        self, daily_sales_service, mock_tank_repository, mock_tank_daily_sales_repository
    ):
        mock_tank_repository.list_active_by_ids.return_value = [
            Tank(id=1, timezone="UTC"),
            Tank(id=2, timezone="UTC"),
        ]
        mock_tank_daily_sales_repository.list_for_tanks.return_value = [stored_row(2, JAN_2, "8")]

        daily_sales_rows = daily_sales_service.get_daily_sales(JAN_2, JAN_3, tank_ids=None)

        assert [(row.tank_id, row.date, row.daily_total_sales) for row in daily_sales_rows] == [
            (1, JAN_2, Decimal("0")),
            (1, JAN_3, Decimal("0")),
            (2, JAN_2, Decimal("8")),
            (2, JAN_3, Decimal("0")),
        ]

    def test_no_matching_tanks_returns_empty_without_querying_sales(
        self, daily_sales_service, mock_tank_repository, mock_tank_daily_sales_repository
    ):
        mock_tank_repository.list_active_by_ids.return_value = []

        assert daily_sales_service.get_daily_sales(JAN_2, JAN_3, tank_ids=[99]) == []
        mock_tank_daily_sales_repository.list_for_tanks.assert_not_called()

    def test_never_reads_readings(
        self,
        daily_sales_service,
        mock_tank_repository,
        mock_tank_volume_repository,
        mock_tank_daily_sales_repository,
    ):
        mock_tank_repository.list_active_by_ids.return_value = [Tank(id=1, timezone="UTC")]
        mock_tank_daily_sales_repository.list_for_tanks.return_value = []

        daily_sales_service.get_daily_sales(JAN_2, JAN_3, tank_ids=None)

        mock_tank_volume_repository.list_in_range.assert_not_called()
        mock_tank_daily_sales_repository.replace_for_dates.assert_not_called()
