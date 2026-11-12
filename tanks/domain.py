"""Typed objects passed between layers, so services never receive raw dicts or DRF objects."""

from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal

# Fixed English names (strftime("%A") depends on the server's locale).
DAY_OF_WEEK_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


@dataclass(frozen=True)
class TankCreate:
    name: str
    location: str
    timezone: str


@dataclass(frozen=True)
class TankUpdate:
    """Partial update. None means "not provided", not "set to null"."""

    name: str | None = None
    location: str | None = None
    timezone: str | None = None

    def provided_fields(self) -> dict[str, str]:
        return {
            field_name: value for field_name, value in asdict(self).items() if value is not None
        }


@dataclass(frozen=True)
class TankVolumeCreate:
    volume: Decimal
    # None means "use the server's current time".
    created_at: datetime | None = None


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    count: int
    limit: int
    offset: int


@dataclass(frozen=True)
class DailySalesResult:
    """One day's calculated sales for one tank (what gets stored in tank_daily_sales)."""

    daily_total_sales: Decimal
    fuel_load_received: bool


@dataclass(frozen=True)
class DailySalesRow:
    """One row of the daily sales report: a tank on a date, with its weekly running average."""

    tank_id: int
    date: date
    daily_total_sales: Decimal
    weekly_running_average: Decimal
    fuel_load_received: bool

    @property
    def day_of_week(self) -> str:
        return DAY_OF_WEEK_NAMES[self.date.weekday()]


@dataclass(frozen=True)
class RecalculationSummary:
    start_date: date
    end_date: date
    # Tanks actually recalculated (unknown or soft-deleted ids are left out).
    tank_ids: list[int]
    # Days that ended up with a stored row (days with readings).
    days_with_sales_rows: int
