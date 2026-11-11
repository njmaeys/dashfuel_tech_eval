from abc import ABC, abstractmethod

from django.utils import timezone

from tanks.domain import Page, TankCreate, TankUpdate
from tanks.exceptions import TankNotFound
from tanks.models import Tank
from tanks.repositories.tank_repository import BaseTankRepository


class BaseTankService(ABC):
    """Business rules for tanks. Soft-deleted tanks behave as if they don't exist."""

    @abstractmethod
    def list_tanks(self, limit: int, offset: int) -> Page[Tank]: ...

    @abstractmethod
    def get_tank(self, tank_id: int) -> Tank:
        """Return the active tank or raise TankNotFound."""

    @abstractmethod
    def create_tank(self, tank_create: TankCreate) -> Tank: ...

    @abstractmethod
    def update_tank(self, tank_id: int, tank_update: TankUpdate) -> Tank: ...

    @abstractmethod
    def delete_tank(self, tank_id: int) -> None:
        """Soft delete: sets deleted_at, keeps the tank's readings."""


class TankService(BaseTankService):
    def __init__(self, repository: BaseTankRepository):
        self._repository = repository

    def list_tanks(self, limit: int, offset: int) -> Page[Tank]:
        return self._repository.list_active(limit=limit, offset=offset)

    def get_tank(self, tank_id: int) -> Tank:
        tank = self._repository.get_by_id(tank_id)
        if tank is None:
            raise TankNotFound(tank_id)
        return tank

    def create_tank(self, tank_create: TankCreate) -> Tank:
        return self._repository.create(tank_create)

    def update_tank(self, tank_id: int, tank_update: TankUpdate) -> Tank:
        tank = self.get_tank(tank_id)
        return self._repository.update(tank, tank_update)

    def delete_tank(self, tank_id: int) -> None:
        tank = self.get_tank(tank_id)
        self._repository.soft_delete(tank, deleted_at=timezone.now())
