from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from tanks.validators import validate_timezone_name


class Tank(models.Model):
    name = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, default="")
    # IANA timezone name. Sets the "day" boundary for sales calculations (Part 2).
    # The validator runs in the admin and full_clean(); the API runs it via the serializer.
    timezone = models.CharField(max_length=64, default="UTC", validators=[validate_timezone_name])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # Soft delete marker: NULL means the tank is active.
    deleted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "tank"

    def __str__(self) -> str:
        return self.name


class TankVolume(models.Model):
    tank = models.ForeignKey(Tank, on_delete=models.PROTECT, related_name="volumes")
    volume = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    # Time the reading was taken. Supplied by the client (defaults to now), not an audit field.
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tank_volume"
        ordering = ["tank_id", "created_at"]
        # One reading per tank per instant, so "consecutive readings" is always well defined.
        # The unique constraint's index also serves (tank, created_at) lookups.
        constraints = [
            models.UniqueConstraint(
                fields=["tank", "created_at"], name="uniq_tank_volume_tank_created_at"
            )
        ]

    def __str__(self) -> str:
        return f"{self.tank_id} @ {self.created_at:%Y-%m-%d %H:%M}: {self.volume}"


class TankDailySales(models.Model):
    """Derived data: one row per tank per local day that has readings.

    Written only by DailySalesService.recalculate_days whenever readings change. A missing row
    means the day has no readings (0 sales), never "not calculated yet". The weekly running
    average isn't stored; it's computed on read from these rows.
    """

    tank = models.ForeignKey(Tank, on_delete=models.PROTECT, related_name="daily_sales")
    # The tank's local date (Tank.timezone), not the UTC date.
    date = models.DateField()
    daily_total_sales = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    # True if any counted pair of consecutive readings went up (e.g. a delivery).
    fuel_load_received = models.BooleanField(default=False)
    # Rows are replaced on recalculation, so this is the only meaningful timestamp.
    calculated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tank_daily_sales"
        ordering = ["tank_id", "date"]
        verbose_name_plural = "tank daily sales"
        constraints = [
            models.UniqueConstraint(fields=["tank", "date"], name="uniq_tank_daily_sales_tank_date")
        ]

    def __str__(self) -> str:
        return f"{self.tank_id} on {self.date}: {self.daily_total_sales}"
