from django.urls import path

from tanks.api.views import (
    TankCollectionView,
    TankItemView,
    TankVolumeCollectionView,
    TankVolumeItemView,
)

urlpatterns = [
    path("tanks/", TankCollectionView.as_view(), name="tank-collection"),
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
