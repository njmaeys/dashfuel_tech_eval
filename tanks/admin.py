from django.contrib import admin

from tanks.models import Tank, TankDailySales, TankVolume


@admin.register(Tank)
class TankAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "location", "timezone", "created_at", "deleted_at")
    list_filter = ("deleted_at",)
    search_fields = ("name", "location")


@admin.register(TankVolume)
class TankVolumeAdmin(admin.ModelAdmin):
    list_display = ("id", "tank", "volume", "created_at", "updated_at")
    list_filter = ("tank",)
    date_hierarchy = "created_at"


@admin.register(TankDailySales)
class TankDailySalesAdmin(admin.ModelAdmin):
    """View only: this is derived data. Fix the readings or use the recalculate endpoint."""

    list_display = ("id", "tank", "date", "daily_total_sales", "fuel_load_received", "calculated_at")
    list_filter = ("tank", "fuel_load_received")
    date_hierarchy = "date"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False
