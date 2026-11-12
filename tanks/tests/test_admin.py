"""Admin configuration tests (no DB)."""

from django.contrib import admin
from django.test import RequestFactory

from tanks.models import TankDailySales


def test_daily_sales_admin_is_view_only():
    """Daily sales are derived data: fix the readings or use the recalculate endpoint instead."""
    tank_daily_sales_admin = admin.site._registry[TankDailySales]
    request = RequestFactory().get("/admin/")

    assert tank_daily_sales_admin.has_add_permission(request) is False
    assert tank_daily_sales_admin.has_change_permission(request) is False
    assert tank_daily_sales_admin.has_delete_permission(request) is False
