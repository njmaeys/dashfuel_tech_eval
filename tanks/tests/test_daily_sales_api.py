"""Daily sales API tests: request validation and response contract.

The service is mocked and these tests are NOT marked django_db, so pytest-django fails any
test here that reaches the database.
"""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from tanks.domain import DailySalesRow, RecalculationSummary
from tanks.services.daily_sales_service import BaseDailySalesService

DAILY_SALES_URL = "/api/v1/tanks/sales/daily/"
RECALCULATE_URL = "/api/v1/tanks/sales/daily/recalculate/"

VALID_QUERY = {"start_date": "2023-01-02", "end_date": "2023-01-05"}


@pytest.fixture
def mock_daily_sales_service():
    daily_sales_service = Mock(spec=BaseDailySalesService)
    with patch("tanks.api.views.get_daily_sales_service", return_value=daily_sales_service):
        yield daily_sales_service


class TestGetDailySales:
    def test_returns_200_with_envelope_and_rows(self, api_client, mock_daily_sales_service):
        mock_daily_sales_service.get_daily_sales.return_value = [
            DailySalesRow(1, date(2023, 1, 2), Decimal("20"), Decimal("20.00"), False),
            DailySalesRow(1, date(2023, 1, 3), Decimal("0"), Decimal("10.00"), True),
        ]

        response = api_client.get(DAILY_SALES_URL, VALID_QUERY)

        assert response.status_code == 200
        assert response.json() == {
            "start_date": "2023-01-02",
            "end_date": "2023-01-05",
            "results": [
                {
                    "tank_id": 1,
                    "date": "2023-01-02",
                    "day_of_week": "Monday",
                    "daily_total_sales": 20.0,
                    "weekly_running_average": 20.0,
                    "fuel_load_received": False,
                },
                {
                    "tank_id": 1,
                    "date": "2023-01-03",
                    "day_of_week": "Tuesday",
                    "daily_total_sales": 0.0,
                    "weekly_running_average": 10.0,
                    "fuel_load_received": True,
                },
            ],
        }
        mock_daily_sales_service.get_daily_sales.assert_called_once_with(
            start_date=date(2023, 1, 2), end_date=date(2023, 1, 5), tank_ids=None
        )

    def test_repeated_tank_id_is_passed_as_list(self, api_client, mock_daily_sales_service):
        mock_daily_sales_service.get_daily_sales.return_value = []

        response = api_client.get(f"{DAILY_SALES_URL}?start_date=2023-01-02&end_date=2023-01-05&tank_id=1&tank_id=2")

        assert response.status_code == 200
        mock_daily_sales_service.get_daily_sales.assert_called_once_with(
            start_date=date(2023, 1, 2), end_date=date(2023, 1, 5), tank_ids=[1, 2]
        )

    def test_thirty_day_range_is_allowed(self, api_client, mock_daily_sales_service):
        mock_daily_sales_service.get_daily_sales.return_value = []

        response = api_client.get(
            DAILY_SALES_URL, {"start_date": "2023-01-01", "end_date": "2023-01-30"}
        )

        assert response.status_code == 200

    @pytest.mark.parametrize(
        "query, invalid_field_name",
        [
            pytest.param({"end_date": "2023-01-05"}, "start_date", id="missing start_date"),
            pytest.param({"start_date": "2023-01-02"}, "end_date", id="missing end_date"),
            pytest.param(
                {"start_date": "2023-01-05", "end_date": "2023-01-02"}, "end_date", id="end before start"
            ),
            pytest.param(
                {"start_date": "2023-01-01", "end_date": "2023-01-31"}, "end_date", id="31 days"
            ),
            pytest.param(
                {"start_date": "2023-01-02T00:00:00Z", "end_date": "2023-01-05"},
                "start_date",
                id="datetime instead of date",
            ),
            pytest.param({**VALID_QUERY, "tank_id": "abc"}, "tank_id", id="non-integer tank_id"),
        ],
    )
    def test_invalid_query_returns_400(
        self, api_client, mock_daily_sales_service, query, invalid_field_name
    ):
        response = api_client.get(DAILY_SALES_URL, query)

        assert response.status_code == 400
        assert invalid_field_name in response.json()
        mock_daily_sales_service.get_daily_sales.assert_not_called()


class TestRecalculateDailySales:
    def test_returns_200_and_summary(self, api_client, mock_daily_sales_service):
        mock_daily_sales_service.recalculate_range.return_value = RecalculationSummary(
            start_date=date(2023, 1, 2), end_date=date(2023, 1, 8), tank_ids=[1], days_with_sales_rows=4
        )

        response = api_client.post(
            RECALCULATE_URL,
            {"start_date": "2023-01-02", "end_date": "2023-01-08", "tank_ids": [1, 99]},
            format="json",
        )

        assert response.status_code == 200
        assert response.json() == {
            "start_date": "2023-01-02",
            "end_date": "2023-01-08",
            "tank_ids": [1],
            "days_with_sales_rows": 4,
        }
        mock_daily_sales_service.recalculate_range.assert_called_once_with(
            start_date=date(2023, 1, 2), end_date=date(2023, 1, 8), tank_ids=[1, 99]
        )

    def test_omitted_tank_ids_means_all_tanks(self, api_client, mock_daily_sales_service):
        mock_daily_sales_service.recalculate_range.return_value = RecalculationSummary(
            start_date=date(2023, 1, 2), end_date=date(2023, 1, 2), tank_ids=[], days_with_sales_rows=0
        )

        api_client.post(
            RECALCULATE_URL, {"start_date": "2023-01-02", "end_date": "2023-01-02"}, format="json"
        )

        assert mock_daily_sales_service.recalculate_range.call_args.kwargs["tank_ids"] is None

    @pytest.mark.parametrize(
        "body, invalid_field_name",
        [
            pytest.param({"end_date": "2023-01-02"}, "start_date", id="missing start_date"),
            pytest.param(
                {"start_date": "2023-01-05", "end_date": "2023-01-02"}, "end_date", id="end before start"
            ),
            pytest.param(
                {"start_date": "2023-01-01", "end_date": "2024-01-02"}, "end_date", id="367 days"
            ),
            pytest.param(
                {"start_date": "2023-01-01", "end_date": "2023-01-02", "tank_ids": []},
                "tank_ids",
                id="empty tank_ids",
            ),
            pytest.param(
                {"start_date": "2023-01-01", "end_date": "2023-01-02", "tank_id": [1]},
                "tank_id",
                id="unknown field",
            ),
        ],
    )
    def test_invalid_body_returns_400(
        self, api_client, mock_daily_sales_service, body, invalid_field_name
    ):
        response = api_client.post(RECALCULATE_URL, body, format="json")

        assert response.status_code == 400
        assert invalid_field_name in response.json()
        mock_daily_sales_service.recalculate_range.assert_not_called()
