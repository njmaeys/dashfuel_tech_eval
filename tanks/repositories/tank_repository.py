from abc import ABC, abstractmethod
from dataclasses import asdict
from datetime import datetime

from tanks.domain import Page, TankCreate, TankUpdate
from tanks.models import Tank


class BaseTankRepository(ABC):
    """Data access for tanks. The only layer allowed to touch the ORM.

    "Active" means not soft-deleted (deleted_at IS NULL).
    """

    @abstractmethod
    def get_by_id(self, tank_id: int) -> Tank | None:
        """Return the active tank, or None."""

    @abstractmethod
    def list_active(self, limit: int, offset: int) -> Page[Tank]:
        """Return one page of active tanks, ordered by tank_id."""

    @abstractmethod
    def list_active_by_ids(self, tank_ids: list[int] | None) -> list[Tank]:
        """Active tanks with these ids (unknown ids are skipped), or all if None. By tank_id."""

    @abstractmethod
    def create(self, tank_create: TankCreate) -> Tank: ...

    @abstractmethod
    def update(self, tank: Tank, tank_update: TankUpdate) -> Tank:
        """Apply only the provided fields."""

    @abstractmethod
    def soft_delete(self, tank: Tank, deleted_at: datetime) -> None: ...


class TankRepository(BaseTankRepository):
    def get_by_id(self, tank_id: int) -> Tank | None:
        return Tank.objects.filter(id=tank_id, deleted_at__isnull=True).first()

    def list_active(self, limit: int, offset: int) -> Page[Tank]:
        queryset = Tank.objects.filter(deleted_at__isnull=True).order_by("id")
        return Page(
            items=list(queryset[offset : offset + limit]),
            count=queryset.count(),
            limit=limit,
            offset=offset,
        )

    def list_active_by_ids(self, tank_ids: list[int] | None) -> list[Tank]:
        queryset = Tank.objects.filter(deleted_at__isnull=True).order_by("id")
        if tank_ids is not None:
            queryset = queryset.filter(id__in=tank_ids)
        return list(queryset)

    def create(self, tank_create: TankCreate) -> Tank:
        return Tank.objects.create(**asdict(tank_create))

    def update(self, tank: Tank, tank_update: TankUpdate) -> Tank:
        provided_fields = tank_update.provided_fields()
        if not provided_fields:
            return tank
        for field_name, value in provided_fields.items():
            setattr(tank, field_name, value)
        tank.save(update_fields=[*provided_fields, "updated_at"])
        return tank

    def soft_delete(self, tank: Tank, deleted_at: datetime) -> None:
        tank.deleted_at = deleted_at
        tank.save(update_fields=["deleted_at", "updated_at"])
