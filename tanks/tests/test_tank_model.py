"""Model validation tests: the rules the admin enforces (it validates with full_clean)."""

import pytest
from django.core.exceptions import ValidationError

from tanks.models import Tank


def build_tank(**overrides) -> Tank:
    fields = {"name": "Test Tank", "location": "123 Main St", "timezone": "UTC"}
    fields.update(overrides)
    return Tank(**fields)


class TestTankTimezone:
    def test_accepts_iana_timezone(self):
        build_tank(timezone="America/Chicago").full_clean()

    def test_rejects_unknown_timezone(self):
        with pytest.raises(ValidationError) as raised:
            build_tank(timezone="banana").full_clean()

        assert "timezone" in raised.value.message_dict
