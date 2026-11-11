from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from tanks.domain import Page, TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume, TankNotFound, TankVolumeNotFound
from tanks.models import TankVolume
from tanks.repositories.tank_repository import BaseTankRepository
from tanks.repositories.tank_volume_repository import BaseTankVolumeRepository


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
        """All or nothing. Raises DuplicateTankVolume if any created_at already exists."""

    @abstractmethod
    def update_tank_volume(
        self, tank_id: int, tank_volume_id: int, volume: Decimal
    ) -> TankVolume: ...

    @abstractmethod
    def delete_tank_volume(self, tank_id: int, tank_volume_id: int) -> None: ...


class TankVolumeService(BaseTankVolumeService):
    def __init__(
        self,
        tank_repository: BaseTankRepository,
        tank_volume_repository: BaseTankVolumeRepository,
    ):
        self._tank_repository = tank_repository
        self._tank_volume_repository = tank_volume_repository

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
        self._require_active_tank(tank_id)

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

        return self._tank_volume_repository.bulk_create(
            tank_id=tank_id, tank_volume_creates=tank_volume_creates
        )

    def update_tank_volume(
        self, tank_id: int, tank_volume_id: int, volume: Decimal
    ) -> TankVolume:
        tank_volume = self._require_tank_volume(tank_id, tank_volume_id)
        return self._tank_volume_repository.update_volume(tank_volume, volume=volume)

    def delete_tank_volume(self, tank_id: int, tank_volume_id: int) -> None:
        tank_volume = self._require_tank_volume(tank_id, tank_volume_id)
        self._tank_volume_repository.delete(tank_volume)

    def _require_active_tank(self, tank_id: int) -> None:
        if self._tank_repository.get_by_id(tank_id) is None:
            raise TankNotFound(tank_id)

    def _require_tank_volume(self, tank_id: int, tank_volume_id: int) -> TankVolume:
        self._require_active_tank(tank_id)
        tank_volume = self._tank_volume_repository.get_for_tank(
            tank_id=tank_id, tank_volume_id=tank_volume_id
        )
        if tank_volume is None:
            raise TankVolumeNotFound(tank_id, tank_volume_id)
        return tank_volume
