"""Business-rule errors. The API layer maps them to HTTP status codes (api/exception_handler.py).

str(error) is the client-facing message.
"""

from datetime import UTC, datetime


class DomainError(Exception):
    """Base class for business-rule errors raised by the service layer."""


class TankNotFound(DomainError):
    def __init__(self, tank_id: int):
        self.tank_id = tank_id
        super().__init__("Tank not found.")


class TankVolumeNotFound(DomainError):
    def __init__(self, tank_id: int, tank_volume_id: int):
        self.tank_id = tank_id
        self.tank_volume_id = tank_volume_id
        super().__init__("Tank volume not found.")


class DuplicateTankVolume(DomainError):
    """A reading already exists for this tank at one or more of the given timestamps."""

    def __init__(self, tank_id: int, created_ats: list[datetime] | None = None):
        self.tank_id = tank_id
        self.created_ats = created_ats or []
        if self.created_ats:
            timestamps = ", ".join(_format_utc(created_at) for created_at in self.created_ats)
            message = f"Tank volume readings already exist at: {timestamps}."
        else:
            message = "One or more tank volume readings already exist at these timestamps."
        super().__init__(message)


def _format_utc(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
