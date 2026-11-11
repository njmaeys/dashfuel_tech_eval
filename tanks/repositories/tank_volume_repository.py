from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction

from tanks.domain import Page, TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume
from tanks.models import TankVolume


class BaseTankVolumeRepository(ABC):
    """Data access for tank volume readings. Every query is scoped to a tank_id."""

    @abstractmethod
    def get_for_tank(self, tank_id: int, tank_volume_id: int) -> TankVolume | None:
        """Return the reading only if it belongs to this tank, otherwise None."""

    @abstractmethod
    def list_for_tank(
        self,
        tank_id: int,
        limit: int,
        offset: int,
        start: datetime | None,
        end: datetime | None,
    ) -> Page[TankVolume]:
        """One page of readings ordered by created_at. start is inclusive, end is exclusive."""

    @abstractmethod
    def existing_created_ats(self, tank_id: int, created_ats: list[datetime]) -> list[datetime]:
        """Return which of the given timestamps already have a reading for this tank."""

    @abstractmethod
    def bulk_create(
        self, tank_id: int, tank_volume_creates: list[TankVolumeCreate]
    ) -> list[TankVolume]:
        """Insert all readings or none. Raises DuplicateTankVolume on a (tank, created_at) clash."""

    @abstractmethod
    def update_volume(self, tank_volume: TankVolume, volume: Decimal) -> TankVolume: ...

    @abstractmethod
    def delete(self, tank_volume: TankVolume) -> None: ...


class TankVolumeRepository(BaseTankVolumeRepository):
    def get_for_tank(self, tank_id: int, tank_volume_id: int) -> TankVolume | None:
        return TankVolume.objects.filter(id=tank_volume_id, tank_id=tank_id).first()

    def list_for_tank(
        self,
        tank_id: int,
        limit: int,
        offset: int,
        start: datetime | None,
        end: datetime | None,
    ) -> Page[TankVolume]:
        queryset = TankVolume.objects.filter(tank_id=tank_id).order_by("created_at")
        if start is not None:
            queryset = queryset.filter(created_at__gte=start)
        if end is not None:
            queryset = queryset.filter(created_at__lt=end)
        return Page(
            items=list(queryset[offset : offset + limit]),
            count=queryset.count(),
            limit=limit,
            offset=offset,
        )

    def existing_created_ats(self, tank_id: int, created_ats: list[datetime]) -> list[datetime]:
        return list(
            TankVolume.objects.filter(tank_id=tank_id, created_at__in=created_ats)
            .order_by("created_at")
            .values_list("created_at", flat=True)
        )

    def bulk_create(
        self, tank_id: int, tank_volume_creates: list[TankVolumeCreate]
    ) -> list[TankVolume]:
        tank_volumes = [
            _build_tank_volume(tank_id, tank_volume_create)
            for tank_volume_create in tank_volume_creates
        ]
        # The atomic block is a savepoint, so a failed insert rolls back cleanly even inside an
        # outer transaction. IntegrityError here means the unique (tank, created_at) constraint
        # caught a duplicate the service's pre-check missed (e.g. a concurrent request).
        try:
            with transaction.atomic():
                return TankVolume.objects.bulk_create(tank_volumes)
        except IntegrityError as error:
            raise DuplicateTankVolume(tank_id) from error

    def update_volume(self, tank_volume: TankVolume, volume: Decimal) -> TankVolume:
        tank_volume.volume = volume
        tank_volume.save(update_fields=["volume", "updated_at"])
        return tank_volume

    def delete(self, tank_volume: TankVolume) -> None:
        tank_volume.delete()


def _build_tank_volume(tank_id: int, tank_volume_create: TankVolumeCreate) -> TankVolume:
    fields = {"tank_id": tank_id, "volume": tank_volume_create.volume}
    # Leaving created_at out lets the model default (timezone.now) apply.
    if tank_volume_create.created_at is not None:
        fields["created_at"] = tank_volume_create.created_at
    return TankVolume(**fields)
