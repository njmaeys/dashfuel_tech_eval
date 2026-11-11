"""Typed objects passed between layers, so services never receive raw dicts or DRF objects."""

from dataclasses import asdict, dataclass
from datetime import datetime
from decimal import Decimal


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
