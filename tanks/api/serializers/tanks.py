from rest_framework import serializers

from tanks.api.serializers.shared import RejectUnknownFieldsMixin
from tanks.domain import TankCreate, TankUpdate
from tanks.validators import validate_timezone_name


class TankResponseSerializer(serializers.Serializer):
    tank_id = serializers.IntegerField(source="id")
    name = serializers.CharField()
    location = serializers.CharField()
    timezone = serializers.CharField()
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TankCreateRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    """POST /tanks/: every field required."""

    name = serializers.CharField(max_length=255)
    location = serializers.CharField(max_length=255)
    timezone = serializers.CharField(max_length=64, validators=[validate_timezone_name])

    def to_domain(self) -> TankCreate:
        return TankCreate(**self.validated_data)


class TankUpdateRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    """PATCH /tanks/{tank_id}/: every field optional, but none may be null or blank."""

    name = serializers.CharField(max_length=255, required=False)
    location = serializers.CharField(max_length=255, required=False)
    timezone = serializers.CharField(
        max_length=64, required=False, validators=[validate_timezone_name]
    )

    def to_domain(self) -> TankUpdate:
        return TankUpdate(**self.validated_data)
