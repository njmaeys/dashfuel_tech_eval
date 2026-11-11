from collections.abc import Mapping

from rest_framework import serializers


class RejectUnknownFieldsMixin:
    """Return 400 for request fields we don't accept, instead of DRF's default of ignoring them.

    The Pydantic equivalent is model_config = ConfigDict(extra="forbid"). Without it, a client
    sending e.g. created_at on PATCH would get a 200 and think it worked.
    """

    unknown_field_messages: dict[str, str] = {}

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            unknown_field_names = sorted(set(data) - set(self.fields))
            if unknown_field_names:
                raise serializers.ValidationError(
                    {
                        field_name: [
                            self.unknown_field_messages.get(field_name, "Unknown field.")
                        ]
                        for field_name in unknown_field_names
                    }
                )
        return super().to_internal_value(data)
