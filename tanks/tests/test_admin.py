"""Admin configuration tests (no DB)."""

from django.contrib import admin
from django.test import RequestFactory

from tanks.models import Tank, TankDailySales, TankVolume


def test_daily_sales_admin_is_view_only():
    """Daily sales are derived data: fix the readings or use the recalculate endpoint instead."""
    tank_daily_sales_admin = admin.site._registry[TankDailySales]
    request = RequestFactory().get("/admin/")

    assert tank_daily_sales_admin.has_add_permission(request) is False
    assert tank_daily_sales_admin.has_change_permission(request) is False
    assert tank_daily_sales_admin.has_delete_permission(request) is False


def test_tank_volume_admin_is_view_only():
    """Reading changes go through the API so daily sales are recalculated."""
    tank_volume_admin = admin.site._registry[TankVolume]
    request = RequestFactory().get("/admin/")

    assert tank_volume_admin.has_add_permission(request) is False
    assert tank_volume_admin.has_change_permission(request) is False
    assert tank_volume_admin.has_delete_permission(request) is False


def test_tank_timezone_is_editable_on_create_only():
    """A timezone change must rebuild daily sales, which only the API's PATCH does."""
    tank_admin = admin.site._registry[Tank]
    request = RequestFactory().get("/admin/")

    assert tank_admin.get_readonly_fields(request, obj=None) == ()
    assert tank_admin.get_readonly_fields(request, obj=Tank(id=1)) == ("timezone",)
