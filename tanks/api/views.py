"""HTTP layer: validate the request, call the service, serialize the response.

Django routes each URL to one class, and the HTTP method picks the function inside it:
- *CollectionView: the collection URL (e.g. /tanks/): list it, or add to it.
- *ItemView: one item's URL (e.g. /tanks/{tank_id}/): read, update, or delete it.

Domain errors (not found, duplicates) are mapped to status codes in api/exception_handler.py.
Validation errors raise from is_valid(raise_exception=True) and become 400s.
@extend_schema only feeds the OpenAPI docs (/api/docs/); it doesn't change behavior.
"""

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from tanks.api.openapi import (
    DAILY_SALES_TAG,
    DUPLICATE_TANK_VOLUME,
    PAGINATED_TANK_VOLUMES,
    PAGINATED_TANKS,
    TANK_NOT_FOUND,
    TANK_OR_TANK_VOLUME_NOT_FOUND,
    TANK_VOLUMES_TAG,
    TANKS_TAG,
    VALIDATION_ERROR,
)
from tanks.api.pagination import PaginationQuerySerializer, paginated_response_data
from tanks.api.serializers.daily_sales import (
    DailySalesQuerySerializer,
    DailySalesRecalculateRequestSerializer,
    DailySalesResponseSerializer,
    RecalculationSummaryResponseSerializer,
)
from tanks.api.serializers.tank_volumes import (
    MAX_TANK_VOLUME_BATCH_SIZE,
    TankVolumeCreateRequestSerializer,
    TankVolumeListQuerySerializer,
    TankVolumeResponseSerializer,
    TankVolumeUpdateRequestSerializer,
)
from tanks.api.serializers.tanks import (
    TankCreateRequestSerializer,
    TankResponseSerializer,
    TankUpdateRequestSerializer,
)
from tanks.dependencies import (
    get_daily_sales_service,
    get_tank_service,
    get_tank_volume_service,
)


class TankCollectionView(APIView):
    """/tanks/"""

    @extend_schema(
        operation_id="list_tanks",
        summary="List tanks",
        description="Active (not soft-deleted) tanks, ordered by tank_id.",
        tags=[TANKS_TAG],
        parameters=[PaginationQuerySerializer],
        responses={200: PAGINATED_TANKS, 400: VALIDATION_ERROR},
    )
    def get(self, request: Request) -> Response:
        query = PaginationQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = get_tank_service().list_tanks(
            limit=query.validated_data["limit"], offset=query.validated_data["offset"]
        )
        return Response(paginated_response_data(page, TankResponseSerializer))

    @extend_schema(
        operation_id="create_tank",
        summary="Create a tank",
        tags=[TANKS_TAG],
        request=TankCreateRequestSerializer,
        responses={201: TankResponseSerializer, 400: VALIDATION_ERROR},
    )
    def post(self, request: Request) -> Response:
        body = TankCreateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        tank = get_tank_service().create_tank(body.to_domain())
        return Response(TankResponseSerializer(tank).data, status=status.HTTP_201_CREATED)


class TankItemView(APIView):
    """/tanks/{tank_id}/"""

    @extend_schema(
        operation_id="get_tank",
        summary="Get a tank",
        tags=[TANKS_TAG],
        responses={200: TankResponseSerializer, 404: TANK_NOT_FOUND},
    )
    def get(self, request: Request, tank_id: int) -> Response:
        tank = get_tank_service().get_tank(tank_id)
        return Response(TankResponseSerializer(tank).data)

    @extend_schema(
        operation_id="update_tank",
        summary="Update a tank",
        description="Partial update: send only the fields to change.",
        tags=[TANKS_TAG],
        request=TankUpdateRequestSerializer,
        responses={200: TankResponseSerializer, 400: VALIDATION_ERROR, 404: TANK_NOT_FOUND},
    )
    def patch(self, request: Request, tank_id: int) -> Response:
        body = TankUpdateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        tank = get_tank_service().update_tank(tank_id, body.to_domain())
        return Response(TankResponseSerializer(tank).data)

    @extend_schema(
        operation_id="delete_tank",
        summary="Delete a tank (soft delete)",
        description=(
            "Sets deleted_at. The tank's readings are kept, but every route under the tank "
            "returns 404 afterwards."
        ),
        tags=[TANKS_TAG],
        responses={204: None, 404: TANK_NOT_FOUND},
    )
    def delete(self, request: Request, tank_id: int) -> Response:
        get_tank_service().delete_tank(tank_id)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TankVolumeCollectionView(APIView):
    """/tanks/{tank_id}/volumes/"""

    @extend_schema(
        operation_id="list_tank_volumes",
        summary="List a tank's readings",
        description=(
            "Ordered by created_at, oldest first. Optional start (inclusive) and end "
            "(exclusive) filter by created_at."
        ),
        tags=[TANK_VOLUMES_TAG],
        parameters=[TankVolumeListQuerySerializer],
        responses={200: PAGINATED_TANK_VOLUMES, 400: VALIDATION_ERROR, 404: TANK_NOT_FOUND},
    )
    def get(self, request: Request, tank_id: int) -> Response:
        query = TankVolumeListQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page = get_tank_volume_service().list_tank_volumes(
            tank_id=tank_id,
            limit=query.validated_data["limit"],
            offset=query.validated_data["offset"],
            start=query.validated_data.get("start"),
            end=query.validated_data.get("end"),
        )
        return Response(paginated_response_data(page, TankVolumeResponseSerializer))

    @extend_schema(
        operation_id="create_tank_volumes",
        summary="Add readings (batch)",
        description=(
            f"A JSON array of 1 to {MAX_TANK_VOLUME_BATCH_SIZE} readings, saved all or nothing. "
            "created_at is optional (defaults to now), but at most one reading per batch may "
            "omit it, and timestamps must be unique within the batch and for the tank. "
            "Timestamps without an offset are treated as UTC."
        ),
        tags=[TANK_VOLUMES_TAG],
        request=TankVolumeCreateRequestSerializer(many=True),
        responses={
            201: TankVolumeResponseSerializer(many=True),
            400: VALIDATION_ERROR,
            404: TANK_NOT_FOUND,
            409: DUPLICATE_TANK_VOLUME,
        },
    )
    def post(self, request: Request, tank_id: int) -> Response:
        body = TankVolumeCreateRequestSerializer.build_batch(data=request.data)
        body.is_valid(raise_exception=True)
        tank_volumes = get_tank_volume_service().create_tank_volumes(
            tank_id=tank_id, tank_volume_creates=body.to_domain()
        )
        return Response(
            TankVolumeResponseSerializer(tank_volumes, many=True).data,
            status=status.HTTP_201_CREATED,
        )


class TankVolumeItemView(APIView):
    """/tanks/{tank_id}/volumes/{tank_volume_id}/"""

    @extend_schema(
        operation_id="update_tank_volume",
        summary="Correct a reading's volume",
        description=(
            "Only volume can change. To fix a wrong created_at, delete the reading and create "
            "it again."
        ),
        tags=[TANK_VOLUMES_TAG],
        request=TankVolumeUpdateRequestSerializer,
        responses={
            200: TankVolumeResponseSerializer,
            400: VALIDATION_ERROR,
            404: TANK_OR_TANK_VOLUME_NOT_FOUND,
        },
    )
    def patch(self, request: Request, tank_id: int, tank_volume_id: int) -> Response:
        body = TankVolumeUpdateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        tank_volume = get_tank_volume_service().update_tank_volume(
            tank_id=tank_id,
            tank_volume_id=tank_volume_id,
            volume=body.validated_data["volume"],
        )
        return Response(TankVolumeResponseSerializer(tank_volume).data)

    @extend_schema(
        operation_id="delete_tank_volume",
        summary="Delete a reading",
        tags=[TANK_VOLUMES_TAG],
        responses={204: None, 404: TANK_OR_TANK_VOLUME_NOT_FOUND},
    )
    def delete(self, request: Request, tank_id: int, tank_volume_id: int) -> Response:
        get_tank_volume_service().delete_tank_volume(
            tank_id=tank_id, tank_volume_id=tank_volume_id
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DailySalesCollectionView(APIView):
    """/tanks/sales/daily/ (read only: never recalculates or writes)."""

    @extend_schema(
        operation_id="list_daily_sales",
        summary="Daily total sales and weekly running average",
        description=(
            "One row per active tank per date in the range (inclusive, at most 30 days). Dates "
            "use the tank's timezone. A date without readings has 0 sales and still counts in "
            "the running average, which is (sum of daily totals from Monday through the date) / "
            "(days from Monday through the date)."
        ),
        tags=[DAILY_SALES_TAG],
        parameters=[DailySalesQuerySerializer],
        responses={200: DailySalesResponseSerializer, 400: VALIDATION_ERROR},
    )
    def get(self, request: Request) -> Response:
        query = DailySalesQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        start_date = query.validated_data["start_date"]
        end_date = query.validated_data["end_date"]
        daily_sales_rows = get_daily_sales_service().get_daily_sales(
            start_date=start_date,
            end_date=end_date,
            tank_ids=query.validated_data.get("tank_id"),
        )
        return Response(
            DailySalesResponseSerializer(
                {"start_date": start_date, "end_date": end_date, "results": daily_sales_rows}
            ).data
        )


class DailySalesRecalculateView(APIView):
    """/tanks/sales/daily/recalculate/"""

    @extend_schema(
        operation_id="recalculate_daily_sales",
        summary="Recalculate stored daily totals (backfill / repair)",
        description=(
            "Recomputes every date in the range (inclusive, at most 366 days) from the readings. "
            "Not needed in normal use: adding readings already recalculates the affected days."
        ),
        tags=[DAILY_SALES_TAG],
        request=DailySalesRecalculateRequestSerializer,
        responses={200: RecalculationSummaryResponseSerializer, 400: VALIDATION_ERROR},
    )
    def post(self, request: Request) -> Response:
        body = DailySalesRecalculateRequestSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        recalculation_summary = get_daily_sales_service().recalculate_range(
            start_date=body.validated_data["start_date"],
            end_date=body.validated_data["end_date"],
            tank_ids=body.validated_data.get("tank_ids"),
        )
        return Response(RecalculationSummaryResponseSerializer(recalculation_summary).data)
