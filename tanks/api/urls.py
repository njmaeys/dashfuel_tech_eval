from django.urls import path

from tanks.api.views import (
    DailySalesCollectionView,
    DailySalesRecalculateView,
    TankCollectionView,
    TankItemView,
    TankVolumeCollectionView,
    TankVolumeItemView,
)

urlpatterns = [
    path("tanks/", TankCollectionView.as_view(), name="tank-collection"),
    # "sales" can't match <int:tank_id>, so these never collide with the tank routes.
    path("tanks/sales/daily/", DailySalesCollectionView.as_view(), name="daily-sales-collection"),
    path(
        "tanks/sales/daily/recalculate/",
        DailySalesRecalculateView.as_view(),
        name="daily-sales-recalculate",
    ),
    path("tanks/<int:tank_id>/", TankItemView.as_view(), name="tank-item"),
    path(
        "tanks/<int:tank_id>/volumes/",
        TankVolumeCollectionView.as_view(),
        name="tank-volume-collection",
    ),
    path(
        "tanks/<int:tank_id>/volumes/<int:tank_volume_id>/",
        TankVolumeItemView.as_view(),
        name="tank-volume-item",
    ),
]
