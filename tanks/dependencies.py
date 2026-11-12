"""Wires concrete implementations together. Views call these; tests patch them."""

from django.db import transaction

from tanks.repositories.tank_daily_sales_repository import TankDailySalesRepository
from tanks.repositories.tank_repository import TankRepository
from tanks.repositories.tank_volume_repository import TankVolumeRepository
from tanks.services.daily_sales_service import BaseDailySalesService, DailySalesService
from tanks.services.tank_service import BaseTankService, TankService
from tanks.services.tank_volume_service import BaseTankVolumeService, TankVolumeService


def get_daily_sales_service() -> BaseDailySalesService:
    return DailySalesService(
        tank_repository=TankRepository(),
        tank_volume_repository=TankVolumeRepository(),
        tank_daily_sales_repository=TankDailySalesRepository(),
        atomic=transaction.atomic,
    )


def get_tank_service() -> BaseTankService:
    return TankService(
        repository=TankRepository(),
        daily_sales_service=get_daily_sales_service(),
        atomic=transaction.atomic,
    )


def get_tank_volume_service() -> BaseTankVolumeService:
    return TankVolumeService(
        tank_repository=TankRepository(),
        tank_volume_repository=TankVolumeRepository(),
        daily_sales_service=get_daily_sales_service(),
        atomic=transaction.atomic,
    )
