from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import date
from zoneinfo import ZoneInfo

from tanks.domain import DailySalesRow, RecalculationSummary
from tanks.models import Tank, TankDailySales
from tanks.repositories.tank_daily_sales_repository import BaseTankDailySalesRepository
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.repositories.tank_volume_repository import BaseTankVolumeRepository
from tanks.services.sales_calculations import (
    ONE_DAY,
    ZERO,
    calculate_daily_sales,
    calculate_weekly_running_averages,
    dates_between,
    group_volumes_by_local_date,
    local_date,
    local_days_to_utc_range,
    week_start,
)


class BaseDailySalesService(ABC):
    """Daily sales totals (stored, recalculated on write) and weekly running averages (on read)."""

    @abstractmethod
    def recalculate_days(self, tank: Tank, dates: set[date]) -> int:
        """Recompute and store the totals for these local dates. Returns rows stored.

        The single write path: readings create/update/delete and the recalculate endpoint all
        come through here.
        """

    @abstractmethod
    def recalculate_all_days(self, tank: Tank) -> int:
        """Rebuild all of the tank's stored totals (e.g. after its timezone changed)."""

    @abstractmethod
    def recalculate_range(
        self, start_date: date, end_date: date, tank_ids: list[int] | None
    ) -> RecalculationSummary:
        """Backfill/repair: recompute every date in the range for the active tanks in scope."""

    @abstractmethod
    def get_daily_sales(
        self, start_date: date, end_date: date, tank_ids: list[int] | None
    ) -> list[DailySalesRow]:
        """One row per active tank per date in the range. Read only."""


class DailySalesService(BaseDailySalesService):
    def __init__(
        self,
        tank_repository: BaseTankRepository,
        tank_volume_repository: BaseTankVolumeRepository,
        tank_daily_sales_repository: BaseTankDailySalesRepository,
        atomic: Callable[[], AbstractContextManager],
    ):
        self._tank_repository = tank_repository
        self._tank_volume_repository = tank_volume_repository
        self._tank_daily_sales_repository = tank_daily_sales_repository
        # django.db.transaction.atomic in production, contextlib.nullcontext in unit tests.
        self._atomic = atomic

    def recalculate_days(self, tank: Tank, dates: set[date]) -> int:
        if not dates:
            return 0
        tank_timezone = ZoneInfo(tank.timezone)

        # One query: the requested days plus the day before the first one, because each day's
        # first sale compares against the previous day's last reading.
        start_at, end_at = local_days_to_utc_range(min(dates) - ONE_DAY, max(dates), tank_timezone)
        readings = self._tank_volume_repository.list_in_range(
            tank_id=tank.id, start_at=start_at, end_at=end_at
        )
        volumes_by_date = group_volumes_by_local_date(
            ((reading.created_at, reading.volume) for reading in readings), tank_timezone
        )

        results = calculate_daily_sales(volumes_by_date, dates)
        self._tank_daily_sales_repository.replace_for_dates(
            tank_id=tank.id, dates=dates, results=results
        )
        return len(results)

    def recalculate_all_days(self, tank: Tank) -> int:
        # Clear first: under a new timezone, old rows can sit on dates the rebuild won't cover.
        self._tank_daily_sales_repository.delete_for_tank(tank.id)
        reading_range = self._tank_volume_repository.date_range_utc(tank.id)
        if reading_range is None:
            return 0
        tank_timezone = ZoneInfo(tank.timezone)
        first_created_at, last_created_at = reading_range
        dates = dates_between(
            local_date(first_created_at, tank_timezone), local_date(last_created_at, tank_timezone)
        )
        return self.recalculate_days(tank, set(dates))

    def recalculate_range(
        self, start_date: date, end_date: date, tank_ids: list[int] | None
    ) -> RecalculationSummary:
        tanks = self._tank_repository.list_active_by_ids(tank_ids)
        dates = set(dates_between(start_date, end_date))
        days_with_sales_rows = 0
        with self._atomic():
            for tank in tanks:
                days_with_sales_rows += self.recalculate_days(tank, dates)
        return RecalculationSummary(
            start_date=start_date,
            end_date=end_date,
            tank_ids=[tank.id for tank in tanks],
            days_with_sales_rows=days_with_sales_rows,
        )

    def get_daily_sales(
        self, start_date: date, end_date: date, tank_ids: list[int] | None
    ) -> list[DailySalesRow]:
        tanks = self._tank_repository.list_active_by_ids(tank_ids)
        if not tanks:
            return []

        # Fetch from the Monday of start_date's week: the running average needs every day since
        # Monday, even the ones before start_date that we don't return.
        stored_rows = self._tank_daily_sales_repository.list_for_tanks(
            tank_ids=[tank.id for tank in tanks],
            start_date=week_start(start_date),
            end_date=end_date,
        )
        stored_rows_by_tank_id: dict[int, dict[date, TankDailySales]] = {}
        for stored_row in stored_rows:
            stored_rows_by_tank_id.setdefault(stored_row.tank_id, {})[stored_row.date] = stored_row

        requested_dates = dates_between(start_date, end_date)
        daily_sales_rows: list[DailySalesRow] = []
        for tank in tanks:
            # A missing row means no readings that day: 0 sales, no fuel load.
            stored_rows_by_date = stored_rows_by_tank_id.get(tank.id, {})
            daily_totals = {
                day: stored_row.daily_total_sales for day, stored_row in stored_rows_by_date.items()
            }
            averages = calculate_weekly_running_averages(daily_totals, requested_dates)
            for day in requested_dates:
                stored_row = stored_rows_by_date.get(day)
                daily_sales_rows.append(
                    DailySalesRow(
                        tank_id=tank.id,
                        date=day,
                        daily_total_sales=stored_row.daily_total_sales if stored_row else ZERO,
                        weekly_running_average=averages[day],
                        fuel_load_received=stored_row.fuel_load_received if stored_row else False,
                    )
                )
        return daily_sales_rows
