"""Shared OpenAPI (Swagger) definitions used by the @extend_schema decorators in views.py.

Plain APIViews don't tell drf-spectacular which serializers they use, so each view method
declares its request, query params, and responses explicitly. These are the reusable pieces.
"""

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, inline_serializer
from rest_framework import serializers

from tanks.api.serializers.tank_volumes import TankVolumeResponseSerializer
from tanks.api.serializers.tanks import TankResponseSerializer

TANKS_TAG = "Tanks"
TANK_VOLUMES_TAG = "Tank volumes"


class ErrorResponseSerializer(serializers.Serializer):
    """Body of every 404 and 409 response."""

    detail = serializers.CharField()


def _paginated(item_serializer_class: type[serializers.Serializer], component_name: str):
    return inline_serializer(
        name=component_name,
        fields={
            "count": serializers.IntegerField(help_text="Total matching items across all pages."),
            "limit": serializers.IntegerField(),
            "offset": serializers.IntegerField(),
            "results": item_serializer_class(many=True),
        },
    )


PAGINATED_TANKS = _paginated(TankResponseSerializer, "PaginatedTankList")
PAGINATED_TANK_VOLUMES = _paginated(TankVolumeResponseSerializer, "PaginatedTankVolumeList")

VALIDATION_ERROR = OpenApiResponse(
    response=OpenApiTypes.OBJECT,
    description=(
        "Validation error: field names mapped to lists of messages, e.g. "
        '{"volume": ["Ensure this value is greater than or equal to 0."]}. '
        "Unknown fields are rejected. For a batch, item errors are keyed by the failing item's "
        '0-based position ({"1": {...}}) and batch-wide errors are under "non_field_errors".'
    ),
)
TANK_NOT_FOUND = OpenApiResponse(
    response=ErrorResponseSerializer,
    description="Tank not found, or soft-deleted.",
)
TANK_OR_TANK_VOLUME_NOT_FOUND = OpenApiResponse(
    response=ErrorResponseSerializer,
    description=(
        "Tank not found (or soft-deleted), or the reading doesn't exist under this tank."
    ),
)
DUPLICATE_TANK_VOLUME = OpenApiResponse(
    response=ErrorResponseSerializer,
    description=(
        "A reading already exists for this tank at one or more of the given created_at "
        "timestamps. Nothing in the batch was saved."
    ),
)
