from abc import ABC, abstractmethod
from datetime import date

from django.db import transaction

from tanks.domain import DailySalesResult
from tanks.models import TankDailySales


class BaseTankDailySalesRepository(ABC):
    """Data access for stored daily sales totals (derived from readings)."""

    @abstractmethod
    def list_for_tanks(
        self, tank_ids: list[int], start_date: date, end_date: date
    ) -> list[TankDailySales]:
        """Stored rows for these tanks with start_date <= date <= end_date."""

    @abstractmethod
    def replace_for_dates(
        self, tank_id: int, dates: set[date], results: dict[date, DailySalesResult]
    ) -> None:
        """Make the stored rows for these dates match results exactly.

        Dates in `dates` without a result end up with no row. Other dates aren't touched.
        """

    @abstractmethod
    def delete_for_tank(self, tank_id: int) -> None:
        """Remove every stored row for the tank (used before a full rebuild)."""


class TankDailySalesRepository(BaseTankDailySalesRepository):
    def list_for_tanks(
        self, tank_ids: list[int], start_date: date, end_date: date
    ) -> list[TankDailySales]:
        return list(
            TankDailySales.objects.filter(
                tank_id__in=tank_ids, date__gte=start_date, date__lte=end_date
            ).order_by("tank_id", "date")
        )

    def replace_for_dates(
        self, tank_id: int, dates: set[date], results: dict[date, DailySalesResult]
    ) -> None:
        # Delete + insert in one transaction: simpler than per-row upserts, and it also removes
        # rows for days that no longer have readings.
        with transaction.atomic():
            TankDailySales.objects.filter(tank_id=tank_id, date__in=dates).delete()
            TankDailySales.objects.bulk_create(
                [
                    TankDailySales(
                        tank_id=tank_id,
                        date=day,
                        daily_total_sales=result.daily_total_sales,
                        fuel_load_received=result.fuel_load_received,
                    )
                    for day, result in sorted(results.items())
                    if day in dates
                ]
            )

    def delete_for_tank(self, tank_id: int) -> None:
        TankDailySales.objects.filter(tank_id=tank_id).delete()
