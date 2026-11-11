"""Tank volume API tests: request validation and response contract.

The service is mocked and these tests are NOT marked django_db, so pytest-django fails any
test here that reaches the database.
"""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from tanks.domain import Page, TankVolumeCreate
from tanks.exceptions import DuplicateTankVolume, TankNotFound, TankVolumeNotFound
from tanks.services.tank_volume_service import BaseTankVolumeService

TANK_VOLUME_COLLECTION_URL = "/api/v1/tanks/1/volumes/"
TANK_VOLUME_ITEM_URL = "/api/v1/tanks/1/volumes/57/"

EXPECTED_TANK_VOLUME_JSON = {
    "tank_volume_id": 57,
    "tank_id": 1,
    "volume": 30.0,
    "created_at": "2023-01-02T10:00:00Z",
    "updated_at": "2026-01-02T10:00:00Z",
}


@pytest.fixture
def mock_tank_volume_service():
    tank_volume_service = Mock(spec=BaseTankVolumeService)
    with patch("tanks.api.views.get_tank_volume_service", return_value=tank_volume_service):
        yield tank_volume_service


class TestListTankVolumes:
    def test_returns_200_and_paginated_envelope(
        self, api_client, mock_tank_volume_service, unsaved_tank_volume
    ):
        mock_tank_volume_service.list_tank_volumes.return_value = Page(
            items=[unsaved_tank_volume], count=1, limit=100, offset=0
        )

        response = api_client.get(TANK_VOLUME_COLLECTION_URL)

        assert response.status_code == 200
        assert response.json() == {
            "count": 1,
            "limit": 100,
            "offset": 0,
            "results": [EXPECTED_TANK_VOLUME_JSON],
        }
        mock_tank_volume_service.list_tank_volumes.assert_called_once_with(
            tank_id=1, limit=100, offset=0, start=None, end=None
        )

    def test_passes_start_and_end_as_utc_datetimes(self, api_client, mock_tank_volume_service):
        mock_tank_volume_service.list_tank_volumes.return_value = Page(
            items=[], count=0, limit=100, offset=0
        )

        response = api_client.get(
            TANK_VOLUME_COLLECTION_URL,
            {"start": "2023-01-02T00:00:00Z", "end": "2023-01-03T00:00:00Z"},
        )

        assert response.status_code == 200
        mock_tank_volume_service.list_tank_volumes.assert_called_once_with(
            tank_id=1,
            limit=100,
            offset=0,
            start=datetime(2023, 1, 2, tzinfo=UTC),
            end=datetime(2023, 1, 3, tzinfo=UTC),
        )

    @pytest.mark.parametrize(
        "query_params, invalid_field_name",
        [
            ({"start": "not-a-date"}, "start"),
            ({"start": "2023-01-03T00:00:00Z", "end": "2023-01-02T00:00:00Z"}, "end"),
            ({"start": "2023-01-02T00:00:00Z", "end": "2023-01-02T00:00:00Z"}, "end"),
            ({"limit": 1001}, "limit"),
        ],
    )
    def test_invalid_query_returns_400(
        self, api_client, mock_tank_volume_service, query_params, invalid_field_name
    ):
        response = api_client.get(TANK_VOLUME_COLLECTION_URL, query_params)

        assert response.status_code == 400
        assert invalid_field_name in response.json()
        mock_tank_volume_service.list_tank_volumes.assert_not_called()

    def test_tank_not_found_returns_404(self, api_client, mock_tank_volume_service):
        mock_tank_volume_service.list_tank_volumes.side_effect = TankNotFound(1)

        response = api_client.get(TANK_VOLUME_COLLECTION_URL)

        assert response.status_code == 404
        assert response.json() == {"detail": "Tank not found."}


class TestCreateTankVolumes:
    def test_returns_201_and_created_readings(
        self, api_client, mock_tank_volume_service, unsaved_tank_volume
    ):
        mock_tank_volume_service.create_tank_volumes.return_value = [unsaved_tank_volume]

        response = api_client.post(
            TANK_VOLUME_COLLECTION_URL,
            [{"volume": 30, "created_at": "2023-01-02T10:00:00Z"}],
            format="json",
        )

        assert response.status_code == 201
        assert response.json() == [EXPECTED_TANK_VOLUME_JSON]
        mock_tank_volume_service.create_tank_volumes.assert_called_once_with(
            tank_id=1,
            tank_volume_creates=[
                TankVolumeCreate(
                    volume=Decimal("30.00"), created_at=datetime(2023, 1, 2, 10, tzinfo=UTC)
                )
            ],
        )

    def test_omitted_created_at_is_passed_as_none(
        self, api_client, mock_tank_volume_service, unsaved_tank_volume
    ):
        mock_tank_volume_service.create_tank_volumes.return_value = [unsaved_tank_volume]

        response = api_client.post(TANK_VOLUME_COLLECTION_URL, [{"volume": 30}], format="json")

        assert response.status_code == 201
        mock_tank_volume_service.create_tank_volumes.assert_called_once_with(
            tank_id=1,
            tank_volume_creates=[TankVolumeCreate(volume=Decimal("30.00"), created_at=None)],
        )

    def test_naive_created_at_is_treated_as_utc(
        self, api_client, mock_tank_volume_service, unsaved_tank_volume
    ):
        mock_tank_volume_service.create_tank_volumes.return_value = [unsaved_tank_volume]

        api_client.post(
            TANK_VOLUME_COLLECTION_URL,
            [{"volume": 30, "created_at": "2023-01-02T10:00:00"}],
            format="json",
        )

        tank_volume_creates = mock_tank_volume_service.create_tank_volumes.call_args.kwargs[
            "tank_volume_creates"
        ]
        assert tank_volume_creates[0].created_at == datetime(2023, 1, 2, 10, tzinfo=UTC)

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param([], id="empty array"),
            pytest.param({"volume": 30}, id="object instead of array"),
            pytest.param([{"created_at": "2023-01-02T10:00:00Z"}], id="missing volume"),
            pytest.param([{"volume": -1}], id="negative volume"),
            pytest.param([{"volume": "12.345"}], id="three decimal places"),
            pytest.param([{"volume": "abc"}], id="non-numeric volume"),
            pytest.param([{"volume": 30, "created_at": "nope"}], id="bad created_at"),
            pytest.param([{"volume": 30, "tank_id": 2}], id="unknown field"),
            pytest.param(
                [
                    {"volume": 30, "created_at": "2023-01-02T10:00:00Z"},
                    {"volume": 20, "created_at": "2023-01-02T10:00:00Z"},
                ],
                id="duplicate created_at in batch",
            ),
            pytest.param([{"volume": 30}, {"volume": 20}], id="two readings without created_at"),
        ],
    )
    def test_invalid_body_returns_400(self, api_client, mock_tank_volume_service, body):
        response = api_client.post(TANK_VOLUME_COLLECTION_URL, body, format="json")

        assert response.status_code == 400
        mock_tank_volume_service.create_tank_volumes.assert_not_called()

    def test_item_errors_are_keyed_by_position_of_failing_items_only(
        self, api_client, mock_tank_volume_service
    ):
        body = [
            {"volume": 30, "created_at": "2023-01-02T10:00:00Z"},
            {"volume": -1, "created_at": "2023-01-02T11:00:00Z"},
        ]

        response = api_client.post(TANK_VOLUME_COLLECTION_URL, body, format="json")

        assert response.status_code == 400
        assert response.json() == {
            "1": {"volume": ["Ensure this value is greater than or equal to 0."]}
        }

    def test_batch_over_max_size_returns_400(self, api_client, mock_tank_volume_service):
        body = [
            {"volume": 1, "created_at": f"2023-01-02T00:00:{second:02d}Z"}
            for second in range(60)
        ] * 17  # 1,020 items; size is checked before the duplicate rule

        response = api_client.post(TANK_VOLUME_COLLECTION_URL, body, format="json")

        assert response.status_code == 400
        assert "1000" in str(response.json())
        mock_tank_volume_service.create_tank_volumes.assert_not_called()

    def test_duplicate_against_existing_returns_409(self, api_client, mock_tank_volume_service):
        mock_tank_volume_service.create_tank_volumes.side_effect = DuplicateTankVolume(
            1, [datetime(2023, 1, 2, 10, tzinfo=UTC)]
        )

        response = api_client.post(
            TANK_VOLUME_COLLECTION_URL,
            [{"volume": 30, "created_at": "2023-01-02T10:00:00Z"}],
            format="json",
        )

        assert response.status_code == 409
        assert response.json() == {
            "detail": "Tank volume readings already exist at: 2023-01-02T10:00:00Z."
        }

    def test_tank_not_found_returns_404(self, api_client, mock_tank_volume_service):
        mock_tank_volume_service.create_tank_volumes.side_effect = TankNotFound(1)

        response = api_client.post(TANK_VOLUME_COLLECTION_URL, [{"volume": 30}], format="json")

        assert response.status_code == 404
        assert response.json() == {"detail": "Tank not found."}


class TestUpdateTankVolume:
    def test_returns_200_and_single_reading(
        self, api_client, mock_tank_volume_service, unsaved_tank_volume
    ):
        mock_tank_volume_service.update_tank_volume.return_value = unsaved_tank_volume

        response = api_client.patch(TANK_VOLUME_ITEM_URL, {"volume": 12.5}, format="json")

        assert response.status_code == 200
        assert response.json() == EXPECTED_TANK_VOLUME_JSON
        mock_tank_volume_service.update_tank_volume.assert_called_once_with(
            tank_id=1, tank_volume_id=57, volume=Decimal("12.50")
        )

    def test_created_at_is_rejected_with_explanation(self, api_client, mock_tank_volume_service):
        response = api_client.patch(
            TANK_VOLUME_ITEM_URL,
            {"volume": 12.5, "created_at": "2023-01-02T10:00:00Z"},
            format="json",
        )

        assert response.status_code == 400
        assert "Delete the reading" in response.json()["created_at"][0]
        mock_tank_volume_service.update_tank_volume.assert_not_called()

    @pytest.mark.parametrize(
        "body",
        [
            pytest.param({}, id="missing volume"),
            pytest.param({"volume": None}, id="null volume"),
            pytest.param({"volume": -5}, id="negative volume"),
        ],
    )
    def test_invalid_body_returns_400(self, api_client, mock_tank_volume_service, body):
        response = api_client.patch(TANK_VOLUME_ITEM_URL, body, format="json")

        assert response.status_code == 400
        assert "volume" in response.json()
        mock_tank_volume_service.update_tank_volume.assert_not_called()

    @pytest.mark.parametrize(
        "domain_error, expected_detail",
        [
            (TankNotFound(1), "Tank not found."),
            (TankVolumeNotFound(1, 57), "Tank volume not found."),
        ],
    )
    def test_not_found_returns_404(
        self, api_client, mock_tank_volume_service, domain_error, expected_detail
    ):
        mock_tank_volume_service.update_tank_volume.side_effect = domain_error

        response = api_client.patch(TANK_VOLUME_ITEM_URL, {"volume": 12.5}, format="json")

        assert response.status_code == 404
        assert response.json() == {"detail": expected_detail}


class TestDeleteTankVolume:
    def test_returns_204_with_no_body(self, api_client, mock_tank_volume_service):
        response = api_client.delete(TANK_VOLUME_ITEM_URL)

        assert response.status_code == 204
        assert response.content == b""
        mock_tank_volume_service.delete_tank_volume.assert_called_once_with(
            tank_id=1, tank_volume_id=57
        )

    def test_not_found_returns_404(self, api_client, mock_tank_volume_service):
        mock_tank_volume_service.delete_tank_volume.side_effect = TankVolumeNotFound(1, 57)

        response = api_client.delete(TANK_VOLUME_ITEM_URL)

        assert response.status_code == 404
        assert response.json() == {"detail": "Tank volume not found."}
