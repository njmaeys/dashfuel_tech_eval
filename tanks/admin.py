from django.contrib import admin

from tanks.models import Tank, TankVolume


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
