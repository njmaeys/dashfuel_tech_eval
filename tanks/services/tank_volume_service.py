from abc import ABC, abstractmethod
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from tanks.domain import Page, TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume, TankNotFound, TankVolumeNotFound
from tanks.models import Tank, TankVolume
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.repositories.tank_volume_repository import BaseTankVolumeRepository
from tanks.services.daily_sales_service import BaseDailySalesService
from tanks.services.sales_calculations import affected_dates


class BaseTankVolumeService(ABC):
    """Business rules for readings. Every operation first requires an active tank."""

    @abstractmethod
    def list_tank_volumes(
        self,
        tank_id: int,
        limit: int,
        offset: int,
        start: datetime | None,
        end: datetime | None,
    ) -> Page[TankVolume]: ...

    @abstractmethod
    def create_tank_volumes(
        self, tank_id: int, tank_volume_creates: list[TankVolumeCreate]
    ) -> list[TankVolume]:
        """All or nothing. Raises DuplicateTankVolume if any created_at already exists.

        Recalculates the affected days' daily sales in the same transaction.
        """

    @abstractmethod
    def update_tank_volume(
        self, tank_id: int, tank_volume_id: int, volume: Decimal
    ) -> TankVolume:
        """Corrects volume. Recalculates the affected days' daily sales in the same transaction."""

    @abstractmethod
    def delete_tank_volume(self, tank_id: int, tank_volume_id: int) -> None:
        """Hard delete. Recalculates the affected days' daily sales in the same transaction."""


class TankVolumeService(BaseTankVolumeService):
    def __init__(
        self,
        tank_repository: BaseTankRepository,
        tank_volume_repository: BaseTankVolumeRepository,
        daily_sales_service: BaseDailySalesService,
        atomic: Callable[[], AbstractContextManager],
    ):
        self._tank_repository = tank_repository
        self._tank_volume_repository = tank_volume_repository
        self._daily_sales_service = daily_sales_service
        # django.db.transaction.atomic in production, contextlib.nullcontext in unit tests.
        self._atomic = atomic

    def list_tank_volumes(
        self,
        tank_id: int,
        limit: int,
        offset: int,
        start: datetime | None,
        end: datetime | None,
    ) -> Page[TankVolume]:
        self._require_active_tank(tank_id)
        return self._tank_volume_repository.list_for_tank(
            tank_id=tank_id, limit=limit, offset=offset, start=start, end=end
        )

    def create_tank_volumes(
        self, tank_id: int, tank_volume_creates: list[TankVolumeCreate]
    ) -> list[TankVolume]:
        tank = self._require_active_tank(tank_id)

        provided_created_ats = [
            tank_volume_create.created_at
            for tank_volume_create in tank_volume_creates
            if tank_volume_create.created_at is not None
        ]
        if provided_created_ats:
            existing_created_ats = self._tank_volume_repository.existing_created_ats(
                tank_id=tank_id, created_ats=provided_created_ats
            )
            if existing_created_ats:
                raise DuplicateTankVolume(tank_id, existing_created_ats)

        with self._atomic():
            tank_volumes = self._tank_volume_repository.bulk_create(
                tank_id=tank_id, tank_volume_creates=tank_volume_creates
            )
            self._recalculate_daily_sales(
                tank, [tank_volume.created_at for tank_volume in tank_volumes]
            )
        return tank_volumes

    def update_tank_volume(
        self, tank_id: int, tank_volume_id: int, volume: Decimal
    ) -> TankVolume:
        tank, tank_volume = self._require_tank_volume(tank_id, tank_volume_id)
        # PATCH can only change volume, so the reading stays on the same day.
        with self._atomic():
            updated_tank_volume = self._tank_volume_repository.update_volume(
                tank_volume, volume=volume
            )
            self._recalculate_daily_sales(tank, [updated_tank_volume.created_at])
        return updated_tank_volume

    def delete_tank_volume(self, tank_id: int, tank_volume_id: int) -> None:
        tank, tank_volume = self._require_tank_volume(tank_id, tank_volume_id)
        # Capture the timestamp before the row is gone.
        deleted_created_at = tank_volume.created_at
        with self._atomic():
            self._tank_volume_repository.delete(tank_volume)
            self._recalculate_daily_sales(tank, [deleted_created_at])

    def _recalculate_daily_sales(self, tank: Tank, reading_created_ats: list[datetime]) -> None:
        """Refresh the stored daily totals affected by readings at these times.

        Must be called inside the same transaction as the reading change, so the change and its
        totals commit (or roll back) together. Affected days are each reading's local day and
        the next day (whose first sale compares against this day's last reading). Weekly running
        averages aren't stored, so nothing else needs to propagate.

        PRODUCTION PATTERN (not built for the take-home): a transactional outbox.
          1. In this same transaction, insert an outbox row (tank_id + affected dates) instead of
             recalculating inline.
          2. A relay (poller or change data capture) publishes outbox rows to SQS/EventBridge.
          3. A worker consumes them and calls DailySalesService.recalculate_days.
        Publishing straight to a queue from the API is a dual write: the commit can succeed while
        the publish fails (a lost update), or the publish can happen before the commit (a worker
        reads uncommitted data). recalculate_days rebuilds days from the readings rather than
        applying deltas, so the worker is idempotent: duplicate or out-of-order events are
        harmless and retries are safe. The tradeoff is eventual consistency: totals are briefly
        stale after a write, instead of being correct when the API returns, as they are here.
        """
        self._daily_sales_service.recalculate_days(
            tank, affected_dates(reading_created_ats, ZoneInfo(tank.timezone))
        )

    def _require_active_tank(self, tank_id: int) -> Tank:
        tank = self._tank_repository.get_by_id(tank_id)
        if tank is None:
            raise TankNotFound(tank_id)
        return tank

    def _require_tank_volume(self, tank_id: int, tank_volume_id: int) -> tuple[Tank, TankVolume]:
        tank = self._require_active_tank(tank_id)
        tank_volume = self._tank_volume_repository.get_for_tank(
            tank_id=tank_id, tank_volume_id=tank_volume_id
        )
        if tank_volume is None:
            raise TankVolumeNotFound(tank_id, tank_volume_id)
        return tank, tank_volume
