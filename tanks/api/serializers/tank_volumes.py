from decimal import Decimal

from rest_framework import serializers

from tanks.api.pagination import PaginationQuerySerializer
from tanks.api.serializers.shared import RejectUnknownFieldsMixin
from tanks.domain import TankVolumeCreate

MAX_TANK_VOLUME_BATCH_SIZE = 1000


class TankVolumeResponseSerializer(serializers.Serializer):
    tank_volume_id = serializers.IntegerField(source="id")
    tank_id = serializers.IntegerField()
    volume = serializers.DecimalField(max_digits=12, decimal_places=2)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()


class TankVolumeCreateListSerializer(serializers.ListSerializer):
    """Rules about the whole POST batch, checked after every item passes its own validation."""

    def validate(self, attrs: list[dict]) -> list[dict]:
        provided_created_ats = [item["created_at"] for item in attrs if "created_at" in item]
        if len(provided_created_ats) != len(set(provided_created_ats)):
            raise serializers.ValidationError(
                "Each reading in a batch must have a unique created_at."
            )
        if len(attrs) - len(provided_created_ats) > 1:
            # Readings without created_at are stamped "now" and would collide with each other.
            raise serializers.ValidationError(
                "At most one reading per batch may omit created_at."
            )
        return attrs

    def to_domain(self) -> list[TankVolumeCreate]:
        return [TankVolumeCreate(**item) for item in self.validated_data]


class TankVolumeCreateRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    """One item of POST /tanks/{tank_id}/volumes/. Build the whole batch with build_batch()."""

    volume = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))
    created_at = serializers.DateTimeField(required=False)

    class Meta:
        list_serializer_class = TankVolumeCreateListSerializer

    @classmethod
    def build_batch(cls, data) -> TankVolumeCreateListSerializer:
        """A non-empty array of at most MAX_TANK_VOLUME_BATCH_SIZE items."""
        return cls(
            data=data, many=True, allow_empty=False, max_length=MAX_TANK_VOLUME_BATCH_SIZE
        )


class TankVolumeUpdateRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    """PATCH /tanks/{tank_id}/volumes/{tank_volume_id}/: corrects volume only."""

    volume = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))

    unknown_field_messages = {
        "created_at": (
            "created_at can't be changed. Delete the reading and create it again with the "
            "correct timestamp."
        ),
    }


class TankVolumeListQuerySerializer(PaginationQuerySerializer):
    """GET /tanks/{tank_id}/volumes/: pagination plus optional start (inclusive) / end (exclusive)."""

    start = serializers.DateTimeField(required=False)
    end = serializers.DateTimeField(required=False)

    def validate(self, attrs: dict) -> dict:
        start, end = attrs.get("start"), attrs.get("end")
        if start is not None and end is not None and start >= end:
            raise serializers.ValidationError({"end": ["end must be after start."]})
        return attrs
