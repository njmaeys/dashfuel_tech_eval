"""Pure calculation tests: the spec's rules and example, no DB, no mocks."""

from datetime import UTC, date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from tanks.domain import DailySalesResult
from tanks.services.sales_calculations import (
    affected_dates,
    calculate_daily_sales,
    calculate_weekly_running_averages,
    dates_between,
    group_volumes_by_local_date,
    local_days_to_utc_range,
    week_start,
)

# 2023-01-02 is a Monday.
MON, TUE, WED, THU, FRI, SAT, SUN = dates_between(date(2023, 1, 2), date(2023, 1, 8))
NEXT_MON = date(2023, 1, 9)
PREVIOUS_SUN = date(2023, 1, 1)


def volumes(*values) -> list[Decimal]:
    return [Decimal(value) for value in values]


# The spec's example data, already grouped by day.
SPEC_VOLUMES_BY_DATE = {
    MON: volumes(30, 10),
    TUE: volumes(20, 45),
    WED: volumes(40, 25),
    THU: volumes(35),
}


class TestSpecExample:
    def test_daily_totals_match_spec(self):
        results = calculate_daily_sales(SPEC_VOLUMES_BY_DATE, [MON, TUE, WED, THU])

        assert {day: result.daily_total_sales for day, result in results.items()} == {
            MON: Decimal("20"),
            TUE: Decimal("0"),
            WED: Decimal("20"),
            THU: Decimal("0"),
        }

    def test_running_averages_match_spec(self):
        daily_totals = {MON: Decimal("20"), TUE: Decimal("0"), WED: Decimal("20"), THU: Decimal("0")}

        assert calculate_weekly_running_averages(daily_totals, [MON, TUE, WED, THU]) == {
            MON: Decimal("20.00"),
            TUE: Decimal("10.00"),
            WED: Decimal("13.33"),
            THU: Decimal("10.00"),
        }


class TestCalculateDailySales:
    def test_first_reading_ever_has_no_sale(self):
        results = calculate_daily_sales({MON: volumes(30)}, [MON])

        assert results[MON] == DailySalesResult(daily_total_sales=Decimal("0"), fuel_load_received=False)

    def test_first_reading_uses_previous_days_last_reading(self):
        results = calculate_daily_sales({MON: volumes(50, 45), TUE: volumes(30)}, [TUE])

        assert results[TUE].daily_total_sales == Decimal("15")  # 45 -> 30, not 50 -> 30

    def test_gap_rule_previous_day_without_readings_means_no_sale(self):
        # Spec rule we'd challenge: Monday 20, no Tuesday readings, Wednesday 10 -> 0, not 10.
        results = calculate_daily_sales({MON: volumes(20), WED: volumes(10)}, [WED])

        assert results[WED].daily_total_sales == Decimal("0")

    def test_sunday_to_monday_crosses_the_week_boundary(self):
        results = calculate_daily_sales({SUN: volumes(40), NEXT_MON: volumes(30)}, [NEXT_MON])

        assert results[NEXT_MON].daily_total_sales == Decimal("10")

    def test_increase_sets_fuel_load_received_and_is_not_a_sale(self):
        results = calculate_daily_sales({MON: volumes(30, 50, 45)}, [MON])

        assert results[MON] == DailySalesResult(daily_total_sales=Decimal("5"), fuel_load_received=True)

    def test_cross_day_increase_sets_fuel_load_received(self):
        results = calculate_daily_sales({MON: volumes(10), TUE: volumes(20)}, [TUE])

        assert results[TUE].fuel_load_received is True

    def test_unchanged_volume_is_neither_sale_nor_fuel_load(self):
        results = calculate_daily_sales({MON: volumes(30, 30)}, [MON])

        assert results[MON] == DailySalesResult(daily_total_sales=Decimal("0"), fuel_load_received=False)

    def test_day_without_readings_has_no_result(self):
        results = calculate_daily_sales({MON: volumes(30)}, [MON, TUE])

        assert TUE not in results

    def test_only_requested_dates_are_calculated(self):
        results = calculate_daily_sales(SPEC_VOLUMES_BY_DATE, [WED])

        assert list(results) == [WED]

    def test_decimal_volumes_stay_exact(self):
        results = calculate_daily_sales({MON: volumes("10.10", "0.30")}, [MON])

        assert results[MON].daily_total_sales == Decimal("9.80")


class TestCalculateWeeklyRunningAverages:
    def test_days_without_totals_count_as_zero_in_the_divisor(self):
        averages = calculate_weekly_running_averages({MON: Decimal("30")}, [WED])

        assert averages[WED] == Decimal("10.00")  # 30 / 3 days (Mon, Tue, Wed)

    def test_divisor_counts_from_monday_even_if_data_starts_mid_week(self):
        averages = calculate_weekly_running_averages({WED: Decimal("30")}, [WED])

        assert averages[WED] == Decimal("10.00")  # Mon and Tue have no data but still count

    def test_average_resets_on_monday(self):
        daily_totals = {SUN: Decimal("70"), NEXT_MON: Decimal("10")}

        averages = calculate_weekly_running_averages(daily_totals, [SUN, NEXT_MON])

        assert averages == {SUN: Decimal("10.00"), NEXT_MON: Decimal("10.00")}

    @pytest.mark.parametrize(
        "monday_total, expected_tuesday_average",
        [
            ("0.01", Decimal("0.01")),  # 0.005 rounds half-up to 0.01
            ("0.03", Decimal("0.02")),  # 0.015 rounds half-up to 0.02
        ],
    )
    def test_rounds_half_up_to_two_decimals(self, monday_total, expected_tuesday_average):
        averages = calculate_weekly_running_averages({MON: Decimal(monday_total)}, [TUE])

        assert averages[TUE] == expected_tuesday_average


class TestDateHelpers:
    @pytest.mark.parametrize("day", [MON, WED, SUN])
    def test_week_start_is_monday(self, day):
        assert week_start(day) == MON

    def test_dates_between_is_inclusive(self):
        assert dates_between(MON, WED) == [MON, TUE, WED]

    def test_utc_range_for_utc_tank(self):
        assert local_days_to_utc_range(MON, TUE, ZoneInfo("UTC")) == (
            datetime(2023, 1, 2, tzinfo=UTC),
            datetime(2023, 1, 4, tzinfo=UTC),
        )

    def test_utc_range_for_chicago_tank(self):
        # Chicago is UTC-6 in January, so local midnight is 06:00 UTC.
        assert local_days_to_utc_range(MON, MON, ZoneInfo("America/Chicago")) == (
            datetime(2023, 1, 2, 6, tzinfo=UTC),
            datetime(2023, 1, 3, 6, tzinfo=UTC),
        )

    def test_group_volumes_uses_tank_local_date(self):
        readings = [
            (datetime(2023, 1, 3, 2, tzinfo=UTC), Decimal("30")),  # Jan 2, 20:00 in Chicago
            (datetime(2023, 1, 3, 15, tzinfo=UTC), Decimal("10")),  # Jan 3, 09:00 in Chicago
        ]

        assert group_volumes_by_local_date(readings, ZoneInfo("America/Chicago")) == {
            MON: volumes(30),
            TUE: volumes(10),
        }

    def test_affected_dates_are_reading_day_and_next_day(self):
        created_ats = [datetime(2023, 1, 2, 10, tzinfo=UTC), datetime(2023, 1, 4, 10, tzinfo=UTC)]

        assert affected_dates(created_ats, ZoneInfo("UTC")) == {MON, TUE, WED, THU}

    def test_affected_dates_use_tank_local_date(self):
        created_ats = [datetime(2023, 1, 3, 2, tzinfo=UTC)]  # Jan 2 in Chicago

        assert affected_dates(created_ats, ZoneInfo("America/Chicago")) == {MON, TUE}

    def test_previous_sunday_constant_is_a_sunday(self):
        # Guards the date constants above.
        assert PREVIOUS_SUN.weekday() == 6 and MON.weekday() == 0
