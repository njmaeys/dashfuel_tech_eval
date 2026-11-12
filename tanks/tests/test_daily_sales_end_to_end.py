"""End-to-end daily sales tests: real API, services, repositories, and test DB. No mocks.

These pin the spec's example through the whole stack, and check that writes keep the stored
daily totals in sync.
"""

from datetime import UTC, datetime

import pytest

from tanks.models import Tank, TankVolume

pytestmark = pytest.mark.django_db

SPEC_READINGS = [
    {"volume": 30, "created_at": "2023-01-02T10:00:00Z"},
    {"volume": 10, "created_at": "2023-01-02T11:00:00Z"},
    {"volume": 20, "created_at": "2023-01-03T09:00:00Z"},
    {"volume": 45, "created_at": "2023-01-03T15:00:00Z"},
    {"volume": 40, "created_at": "2023-01-04T10:00:00Z"},
    {"volume": 25, "created_at": "2023-01-04T18:00:00Z"},
    {"volume": 35, "created_at": "2023-01-05T11:00:00Z"},
]

DAILY_SALES_URL = "/api/v1/tanks/sales/daily/"


def create_tank(api_client, timezone: str = "UTC") -> int:
    response = api_client.post(
        "/api/v1/tanks/",
        {"name": "Tank 1", "location": "123 Main St", "timezone": timezone},
        format="json",
    )
    assert response.status_code == 201
    return response.json()["tank_id"]


def post_readings(api_client, tank_id: int, readings: list[dict]) -> None:
    response = api_client.post(f"/api/v1/tanks/{tank_id}/volumes/", readings, format="json")
    assert response.status_code == 201, response.json()


def get_daily_sales(api_client, tank_id: int, start_date: str, end_date: str) -> list[tuple]:
    response = api_client.get(
        DAILY_SALES_URL, {"start_date": start_date, "end_date": end_date, "tank_id": tank_id}
    )
    assert response.status_code == 200, response.json()
    return [
        (
            row["date"],
            row["day_of_week"],
            row["daily_total_sales"],
            row["weekly_running_average"],
            row["fuel_load_received"],
        )
        for row in response.json()["results"]
    ]


def test_spec_example_produces_spec_table(api_client):
    tank_id = create_tank(api_client)
    post_readings(api_client, tank_id, SPEC_READINGS)

    assert get_daily_sales(api_client, tank_id, "2023-01-02", "2023-01-05") == [
        ("2023-01-02", "Monday", 20.0, 20.0, False),
        ("2023-01-03", "Tuesday", 0.0, 10.0, True),
        ("2023-01-04", "Wednesday", 20.0, 13.33, False),
        ("2023-01-05", "Thursday", 0.0, 10.0, True),
    ]


def test_backfilled_reading_updates_its_day_and_the_next_day(api_client):
    tank_id = create_tank(api_client)
    post_readings(api_client, tank_id, SPEC_READINGS)

    # Jan 4 23:00 at 40: Jan 4 gets a delivery (25 -> 40), and Jan 5's first sale becomes 40 -> 35.
    post_readings(api_client, tank_id, [{"volume": 40, "created_at": "2023-01-04T23:00:00Z"}])

    assert get_daily_sales(api_client, tank_id, "2023-01-04", "2023-01-05") == [
        ("2023-01-04", "Wednesday", 20.0, 13.33, True),
        ("2023-01-05", "Thursday", 5.0, 11.25, False),  # (20 + 0 + 20 + 5) / 4
    ]


def test_mid_week_request_still_averages_from_monday(api_client):
    tank_id = create_tank(api_client)
    post_readings(api_client, tank_id, SPEC_READINGS)

    assert get_daily_sales(api_client, tank_id, "2023-01-04", "2023-01-04") == [
        ("2023-01-04", "Wednesday", 20.0, 13.33, False),
    ]


def test_days_without_readings_are_returned_as_zero(api_client):
    tank_id = create_tank(api_client)
    post_readings(api_client, tank_id, SPEC_READINGS)

    rows = get_daily_sales(api_client, tank_id, "2023-01-06", "2023-01-08")

    assert rows == [
        ("2023-01-06", "Friday", 0.0, 8.0, False),  # 40 / 5
        ("2023-01-07", "Saturday", 0.0, 6.67, False),  # 40 / 6
        ("2023-01-08", "Sunday", 0.0, 5.71, False),  # 40 / 7
    ]


def test_timezone_change_rebuilds_daily_totals(api_client):
    tank_id = create_tank(api_client, timezone="UTC")
    # 23:30 and 00:30 UTC: different UTC days, but both Jan 2 evening in Chicago (UTC-6).
    post_readings(
        api_client,
        tank_id,
        [
            {"volume": 30, "created_at": "2023-01-02T23:30:00Z"},
            {"volume": 10, "created_at": "2023-01-03T00:30:00Z"},
        ],
    )
    assert [row[2] for row in get_daily_sales(api_client, tank_id, "2023-01-02", "2023-01-03")] == [
        0.0,
        20.0,
    ]

    response = api_client.patch(
        f"/api/v1/tanks/{tank_id}/", {"timezone": "America/Chicago"}, format="json"
    )
    assert response.status_code == 200

    assert [row[2] for row in get_daily_sales(api_client, tank_id, "2023-01-02", "2023-01-03")] == [
        20.0,
        0.0,
    ]


def test_recalculate_endpoint_backfills_readings_written_outside_the_api(api_client):
    tank_id = create_tank(api_client)
    # Written straight to the DB (e.g. imported before this feature), so no daily totals yet.
    TankVolume.objects.bulk_create(
        [
            TankVolume(tank_id=tank_id, volume=30, created_at=datetime(2023, 1, 2, 10, tzinfo=UTC)),
            TankVolume(tank_id=tank_id, volume=10, created_at=datetime(2023, 1, 2, 11, tzinfo=UTC)),
        ]
    )
    assert get_daily_sales(api_client, tank_id, "2023-01-02", "2023-01-02")[0][2] == 0.0

    response = api_client.post(
        "/api/v1/tanks/sales/daily/recalculate/",
        {"start_date": "2023-01-02", "end_date": "2023-01-08"},
        format="json",
    )

    assert response.status_code == 200
    assert response.json()["tank_ids"] == [tank_id]
    assert response.json()["days_with_sales_rows"] == 1
    assert get_daily_sales(api_client, tank_id, "2023-01-02", "2023-01-02")[0][2] == 20.0


def test_failed_batch_saves_neither_readings_nor_totals(api_client):
    tank_id = create_tank(api_client)
    post_readings(api_client, tank_id, SPEC_READINGS[:2])

    # Second item duplicates an existing reading, so the whole batch is rejected.
    response = api_client.post(
        f"/api/v1/tanks/{tank_id}/volumes/",
        [
            {"volume": 5, "created_at": "2023-01-03T10:00:00Z"},
            {"volume": 10, "created_at": "2023-01-02T11:00:00Z"},
        ],
        format="json",
    )

    assert response.status_code == 409
    assert TankVolume.objects.filter(tank_id=tank_id).count() == 2
    assert [row[2] for row in get_daily_sales(api_client, tank_id, "2023-01-02", "2023-01-03")] == [
        20.0,
        0.0,
    ]


def test_soft_deleted_and_unknown_tanks_are_left_out(api_client):
    kept_tank_id = create_tank(api_client)
    deleted_tank_id = create_tank(api_client)
    Tank.objects.filter(id=deleted_tank_id).update(deleted_at=datetime(2023, 1, 1, tzinfo=UTC))

    response = api_client.get(
        f"{DAILY_SALES_URL}?start_date=2023-01-02&end_date=2023-01-02"
        f"&tank_id={kept_tank_id}&tank_id={deleted_tank_id}&tank_id=999"
    )

    assert response.status_code == 200
    assert [row["tank_id"] for row in response.json()["results"]] == [kept_tank_id]
