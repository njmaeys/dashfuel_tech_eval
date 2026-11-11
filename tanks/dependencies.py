"""Wires concrete implementations together. Views call these; tests patch them."""

from tanks.repositories.tank_repository import TankRepository
from tanks.repositories.tank_volume_repository import TankVolumeRepository
from tanks.services.tank_service import BaseTankService, TankService
from tanks.services.tank_volume_service import BaseTankVolumeService, TankVolumeService


def get_tank_service() -> BaseTankService:
    return TankService(repository=TankRepository())


def get_tank_volume_service() -> BaseTankVolumeService:
    return TankVolumeService(
        tank_repository=TankRepository(),
        tank_volume_repository=TankVolumeRepository(),
    )
