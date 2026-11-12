from datetime import date

from rest_framework import serializers

from tanks.api.serializers.shared import RejectUnknownFieldsMixin

MAX_DAILY_SALES_RANGE_DAYS = 30
MAX_RECALCULATION_RANGE_DAYS = 366


def validate_date_range(attrs: dict, max_days: int) -> dict:
    """start_date..end_date, both inclusive, at most max_days days."""
    start_date: date = attrs["start_date"]
    end_date: date = attrs["end_date"]
    if end_date < start_date:
        raise serializers.ValidationError(
            {"end_date": ["end_date must be on or after start_date."]}
        )
    if (end_date - start_date).days + 1 > max_days:
        raise serializers.ValidationError(
            {"end_date": [f"The range can be at most {max_days} days, inclusive."]}
        )
    return attrs


class DailySalesQuerySerializer(serializers.Serializer):
    """GET /tanks/sales/daily/ query params."""

    start_date = serializers.DateField(help_text="First date to return (inclusive).")
    end_date = serializers.DateField(
        help_text=f"Last date to return (inclusive). At most {MAX_DAILY_SALES_RANGE_DAYS} days."
    )
    # Repeated query param: ?tank_id=1&tank_id=2. Omitted means all active tanks.
    tank_id = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        help_text=(
            "Repeat to filter by several tanks. Unknown or deleted tank ids are left out of the "
            "results. Omit for all tanks."
        ),
    )

    def validate(self, attrs: dict) -> dict:
        return validate_date_range(attrs, MAX_DAILY_SALES_RANGE_DAYS)


class DailySalesRowResponseSerializer(serializers.Serializer):
    tank_id = serializers.IntegerField()
    date = serializers.DateField()
    day_of_week = serializers.CharField(help_text='e.g. "Monday".')
    daily_total_sales = serializers.DecimalField(max_digits=12, decimal_places=2)
    weekly_running_average = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Sum of daily totals from Monday through this date / days from Monday through this date.",
    )
    fuel_load_received = serializers.BooleanField(
        help_text="True if any reading went up this day (a delivery), so some sales may be hidden."
    )


class DailySalesResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    results = DailySalesRowResponseSerializer(many=True)


class DailySalesRecalculateRequestSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    """POST /tanks/sales/daily/recalculate/ body."""

    start_date = serializers.DateField()
    end_date = serializers.DateField(
        help_text=f"Inclusive. At most {MAX_RECALCULATION_RANGE_DAYS} days after start_date."
    )
    tank_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=False,
        help_text="Omit for all active tanks. Unknown or deleted tank ids are skipped.",
    )

    def validate(self, attrs: dict) -> dict:
        return validate_date_range(attrs, MAX_RECALCULATION_RANGE_DAYS)


class RecalculationSummaryResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    tank_ids = serializers.ListField(
        child=serializers.IntegerField(), help_text="Tanks actually recalculated."
    )
    days_with_sales_rows = serializers.IntegerField(
        help_text="Days that have readings, and so now have a stored daily total."
    )
