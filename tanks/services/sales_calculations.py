"""Pure sales calculations: no ORM, no Django. Inputs in, results out.

Kept separate from the service so the spec's rules can be tested directly against its example.
"""

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime, time, timedelta
from decimal import ROUND_HALF_UP, Decimal
from zoneinfo import ZoneInfo

from tanks.domain import DailySalesResult

ZERO = Decimal("0")
CENT = Decimal("0.01")
ONE_DAY = timedelta(days=1)


# --- Dates and timezones --------------------------------------------------------------------


def local_date(moment: datetime, tank_timezone: ZoneInfo) -> date:
    """The tank-local calendar date of a UTC timestamp."""
    return moment.astimezone(tank_timezone).date()


def local_days_to_utc_range(
    first_day: date, last_day: date, tank_timezone: ZoneInfo
) -> tuple[datetime, datetime]:
    """UTC [start, end) covering local days first_day..last_day inclusive.

    zoneinfo handles daylight saving, so a local day may be 23 or 25 hours long.
    """
    start_at = datetime.combine(first_day, time.min, tzinfo=tank_timezone)
    end_at = datetime.combine(last_day + ONE_DAY, time.min, tzinfo=tank_timezone)
    return start_at.astimezone(UTC), end_at.astimezone(UTC)


def dates_between(first_day: date, last_day: date) -> list[date]:
    """Every date from first_day to last_day, inclusive."""
    return [first_day + timedelta(days=offset) for offset in range((last_day - first_day).days + 1)]


def week_start(day: date) -> date:
    """The Monday of day's week (weeks run Monday to Sunday)."""
    return day - timedelta(days=day.weekday())


def affected_dates(reading_created_ats: Iterable[datetime], tank_timezone: ZoneInfo) -> set[date]:
    """Days whose totals change when readings at these times are added, edited, or removed.

    A reading's own day, and the next day: the next day's first sale is computed against
    this day's last reading.
    """
    dates: set[date] = set()
    for created_at in reading_created_ats:
        reading_date = local_date(created_at, tank_timezone)
        dates.update({reading_date, reading_date + ONE_DAY})
    return dates


def group_volumes_by_local_date(
    readings: Iterable[tuple[datetime, Decimal]], tank_timezone: ZoneInfo
) -> dict[date, list[Decimal]]:
    """Group (created_at, volume) pairs by tank-local date. Input must be in time order."""
    volumes_by_date: dict[date, list[Decimal]] = {}
    for created_at, volume in readings:
        volumes_by_date.setdefault(local_date(created_at, tank_timezone), []).append(volume)
    return volumes_by_date


# --- Sales ----------------------------------------------------------------------------------


def calculate_daily_sales(
    volumes_by_date: Mapping[date, list[Decimal]], dates: Iterable[date]
) -> dict[date, DailySalesResult]:
    """Daily total sales for each requested date that has readings.

    For each pair of consecutive readings, sale = previous - current if the volume went down,
    otherwise 0. A day's first reading is compared to the last reading of the previous day.

    Dates without readings get no result: their total is 0 by definition, and no row is stored.
    """
    results: dict[date, DailySalesResult] = {}
    for day in dates:
        volumes = volumes_by_date.get(day)
        if not volumes:
            continue

        # GAP RULE (spec, kept as written): only the immediately previous day counts. If it has
        # no readings, the first sale is 0, even when an earlier day had a higher reading.
        # e.g. Mon 20, no Tuesday readings, Wed 10: Wednesday's first sale is 0, not 10.
        # We'd challenge this with product (see README); fuel sold across the gap disappears.
        previous_day_volumes = volumes_by_date.get(day - ONE_DAY)
        previous_volume = previous_day_volumes[-1] if previous_day_volumes else None

        daily_total_sales = ZERO
        fuel_load_received = False
        for volume in volumes:
            if previous_volume is not None:
                if volume < previous_volume:
                    daily_total_sales += previous_volume - volume
                elif volume > previous_volume:
                    # An increase means fuel was delivered. The sale for this pair is 0, and any
                    # sales hidden by the delivery can't be measured, so we flag it instead.
                    fuel_load_received = True
            previous_volume = volume

        results[day] = DailySalesResult(
            daily_total_sales=daily_total_sales, fuel_load_received=fuel_load_received
        )
    return results


def calculate_weekly_running_averages(
    daily_totals: Mapping[date, Decimal], dates: Iterable[date]
) -> dict[date, Decimal]:
    """Running average = (sum of daily totals Monday..day) / (number of days Monday..day).

    Dates missing from daily_totals count as 0 and still count in the divisor, per the spec's
    "number of days from Monday up to that day". Rounded to 2 decimal places, half-up.
    """
    averages: dict[date, Decimal] = {}
    for day in dates:
        monday = week_start(day)
        days_since_monday = (day - monday).days + 1
        week_total = sum(
            (daily_totals.get(week_day, ZERO) for week_day in dates_between(monday, day)), ZERO
        )
        averages[day] = (week_total / days_since_monday).quantize(CENT, rounding=ROUND_HALF_UP)
    return averages
