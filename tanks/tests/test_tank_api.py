"""Tank API tests: request validation and response contract.

The service is mocked and these tests are NOT marked django_db, so pytest-django fails any
test here that reaches the database. That keeps the API layer honest about its boundaries.
"""

from unittest.mock import Mock, patch

import pytest

from tanks.domain import Page, TankCreate, TankUpdate
from tanks.exceptions import TankNotFound
from tanks.services.tank_service import BaseTankService

TANK_COLLECTION_URL = "/api/v1/tanks/"
TANK_ITEM_URL = "/api/v1/tanks/1/"

EXPECTED_TANK_JSON = {
    "tank_id": 1,
    "name": "Test Tank",
    "location": "123 Main St",
    "timezone": "UTC",
    "created_at": "2026-01-02T10:00:00Z",
    "updated_at": "2026-01-02T10:00:00Z",
}

VALID_TANK_BODY = {"name": "Test Tank", "location": "123 Main St", "timezone": "America/Chicago"}


@pytest.fixture
def mock_tank_service():
    tank_service = Mock(spec=BaseTankService)
    with patch("tanks.api.views.get_tank_service", return_value=tank_service):
        yield tank_service


class TestListTanks:
    def test_returns_200_and_paginated_envelope(self, api_client, mock_tank_service, unsaved_tank):
        mock_tank_service.list_tanks.return_value = Page(
            items=[unsaved_tank], count=1, limit=100, offset=0
        )

        response = api_client.get(TANK_COLLECTION_URL)

        assert response.status_code == 200
        assert response.json() == {
            "count": 1,
            "limit": 100,
            "offset": 0,
            "results": [EXPECTED_TANK_JSON],
        }
        mock_tank_service.list_tanks.assert_called_once_with(limit=100, offset=0)

    def test_passes_limit_and_offset(self, api_client, mock_tank_service):
        mock_tank_service.list_tanks.return_value = Page(items=[], count=0, limit=10, offset=20)

        response = api_client.get(TANK_COLLECTION_URL, {"limit": 10, "offset": 20})

        assert response.status_code == 200
        mock_tank_service.list_tanks.assert_called_once_with(limit=10, offset=20)

    @pytest.mark.parametrize(
        "query_params, invalid_field_name",
        [
            ({"limit": 0}, "limit"),
            ({"limit": 1001}, "limit"),
            ({"limit": "abc"}, "limit"),
            ({"offset": -1}, "offset"),
        ],
    )
    def test_invalid_pagination_returns_400(
        self, api_client, mock_tank_service, query_params, invalid_field_name
    ):
        response = api_client.get(TANK_COLLECTION_URL, query_params)

        assert response.status_code == 400
        assert invalid_field_name in response.json()
        mock_tank_service.list_tanks.assert_not_called()


class TestCreateTank:
    def test_returns_201_and_created_tank(self, api_client, mock_tank_service, unsaved_tank):
        mock_tank_service.create_tank.return_value = unsaved_tank

        response = api_client.post(TANK_COLLECTION_URL, VALID_TANK_BODY, format="json")

        assert response.status_code == 201
        assert response.json() == EXPECTED_TANK_JSON
        mock_tank_service.create_tank.assert_called_once_with(
            TankCreate(name="Test Tank", location="123 Main St", timezone="America/Chicago")
        )

    @pytest.mark.parametrize(
        "body_overrides, invalid_field_name",
        [
            ({"name": None}, "name"),
            ({"name": ""}, "name"),
            ({"name": "   "}, "name"),
            ({"name": "x" * 256}, "name"),
            ({"location": ""}, "location"),
            ({"timezone": "Mars/Olympus_Mons"}, "timezone"),
            ({"deleted_at": "2026-01-01T00:00:00Z"}, "deleted_at"),
        ],
    )
    def test_invalid_body_returns_400(
        self, api_client, mock_tank_service, body_overrides, invalid_field_name
    ):
        body = {**VALID_TANK_BODY, **body_overrides}

        response = api_client.post(TANK_COLLECTION_URL, body, format="json")

        assert response.status_code == 400
        assert invalid_field_name in response.json()
        mock_tank_service.create_tank.assert_not_called()

    @pytest.mark.parametrize("missing_field_name", ["name", "location", "timezone"])
    def test_missing_required_field_returns_400(
        self, api_client, mock_tank_service, missing_field_name
    ):
        body = {
            field_name: value
            for field_name, value in VALID_TANK_BODY.items()
            if field_name != missing_field_name
        }

        response = api_client.post(TANK_COLLECTION_URL, body, format="json")

        assert response.status_code == 400
        assert missing_field_name in response.json()
        mock_tank_service.create_tank.assert_not_called()


class TestGetTank:
    def test_returns_200_and_expected_shape(self, api_client, mock_tank_service, unsaved_tank):
        mock_tank_service.get_tank.return_value = unsaved_tank

        response = api_client.get(TANK_ITEM_URL)

        assert response.status_code == 200
        assert response.json() == EXPECTED_TANK_JSON
        assert "deleted_at" not in response.json()
        mock_tank_service.get_tank.assert_called_once_with(1)

    def test_not_found_returns_404(self, api_client, mock_tank_service):
        mock_tank_service.get_tank.side_effect = TankNotFound(1)

        response = api_client.get(TANK_ITEM_URL)

        assert response.status_code == 404
        assert response.json() == {"detail": "Tank not found."}


class TestUpdateTank:
    def test_returns_200_and_updated_tank(self, api_client, mock_tank_service, unsaved_tank):
        mock_tank_service.update_tank.return_value = unsaved_tank

        response = api_client.patch(TANK_ITEM_URL, {"name": "Renamed"}, format="json")

        assert response.status_code == 200
        assert response.json() == EXPECTED_TANK_JSON
        mock_tank_service.update_tank.assert_called_once_with(1, TankUpdate(name="Renamed"))

    @pytest.mark.parametrize(
        "body, invalid_field_name",
        [
            ({"name": None}, "name"),
            ({"name": ""}, "name"),
            ({"timezone": "Not/A_Zone"}, "timezone"),
            ({"tank_id": 2}, "tank_id"),
        ],
    )
    def test_invalid_body_returns_400(
        self, api_client, mock_tank_service, body, invalid_field_name
    ):
        response = api_client.patch(TANK_ITEM_URL, body, format="json")

        assert response.status_code == 400
        assert invalid_field_name in response.json()
        mock_tank_service.update_tank.assert_not_called()

    def test_not_found_returns_404(self, api_client, mock_tank_service):
        mock_tank_service.update_tank.side_effect = TankNotFound(1)

        response = api_client.patch(TANK_ITEM_URL, {"name": "Renamed"}, format="json")

        assert response.status_code == 404
        assert response.json() == {"detail": "Tank not found."}


class TestDeleteTank:
    def test_returns_204_with_no_body(self, api_client, mock_tank_service):
        response = api_client.delete(TANK_ITEM_URL)

        assert response.status_code == 204
        assert response.content == b""
        mock_tank_service.delete_tank.assert_called_once_with(1)

    def test_not_found_returns_404(self, api_client, mock_tank_service):
        mock_tank_service.delete_tank.side_effect = TankNotFound(1)

        response = api_client.delete(TANK_ITEM_URL)

        assert response.status_code == 404
        assert response.json() == {"detail": "Tank not found."}
