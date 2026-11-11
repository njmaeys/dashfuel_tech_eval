"""Validators shared by the model (admin, full_clean) and the API serializers.

They raise Django's ValidationError, which DRF also converts into a 400.
"""

from functools import cache
from zoneinfo import available_timezones

from django.core.exceptions import ValidationError


@cache
def _timezone_names() -> frozenset[str]:
    return frozenset(available_timezones())


def validate_timezone_name(value: str) -> None:
    """Part 2 uses the tank's timezone to split readings into days, so it must be a real zone."""
    if value not in _timezone_names():
        raise ValidationError(
            "Unknown timezone. Use an IANA name such as 'UTC' or 'America/Chicago'."
        )
