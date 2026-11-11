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
