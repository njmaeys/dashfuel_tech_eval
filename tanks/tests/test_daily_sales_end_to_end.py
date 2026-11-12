"""End-to-end daily sales tests: real API, services, repositories, and test DB. No mocks.

These pin the spec's example through the whole stack, and check that writes keep the stored
daily totals in sync.
"""

from datetime import UTC, datetime

import pytest

from tanks.models import Tank, TankDailySales, TankVolume

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


# --- Part 3: corrections keep daily sales fresh ---------------------------------------------


def load_spec_tank(api_client) -> tuple[int, dict[str, int]]:
    """Create a tank with the spec readings. Returns tank_id and {created_at: tank_volume_id}."""
    tank_id = create_tank(api_client)
    response = api_client.post(f"/api/v1/tanks/{tank_id}/volumes/", SPEC_READINGS, format="json")
    assert response.status_code == 201
    return tank_id, {row["created_at"]: row["tank_volume_id"] for row in response.json()}


def patch_volume(api_client, tank_id: int, tank_volume_id: int, volume: int) -> None:
    response = api_client.patch(
        f"/api/v1/tanks/{tank_id}/volumes/{tank_volume_id}/", {"volume": volume}, format="json"
    )
    assert response.status_code == 200, response.json()


def delete_reading(api_client, tank_id: int, tank_volume_id: int) -> None:
    response = api_client.delete(f"/api/v1/tanks/{tank_id}/volumes/{tank_volume_id}/")
    assert response.status_code == 204


def totals_and_averages(api_client, tank_id: int) -> list[tuple[float, float]]:
    return [
        (daily_total_sales, weekly_running_average)
        for _, _, daily_total_sales, weekly_running_average, _ in get_daily_sales(
            api_client, tank_id, "2023-01-02", "2023-01-05"
        )
    ]


def test_patch_correction_updates_day_and_running_averages(api_client):
    tank_id, tank_volume_ids = load_spec_tank(api_client)

    # Jan 4 18:00: 25 -> 30. Jan 4 = 5 + 10 = 15; Jan 5's 30 -> 35 is an increase, so 0.
    patch_volume(api_client, tank_id, tank_volume_ids["2023-01-04T18:00:00Z"], 30)

    assert totals_and_averages(api_client, tank_id) == [
        (20.0, 20.0),
        (0.0, 10.0),
        (15.0, 11.67),
        (0.0, 8.75),
    ]


def test_patch_correction_updates_the_next_day(api_client):
    tank_id, tank_volume_ids = load_spec_tank(api_client)

    # Jan 4 18:00: 25 -> 40. Jan 4 = 5 + 0 = 5; Jan 5's first sale becomes 40 -> 35 = 5.
    patch_volume(api_client, tank_id, tank_volume_ids["2023-01-04T18:00:00Z"], 40)

    assert totals_and_averages(api_client, tank_id) == [
        (20.0, 20.0),
        (0.0, 10.0),
        (5.0, 8.33),
        (5.0, 7.5),
    ]


def test_patch_back_restores_the_spec_table(api_client):
    tank_id, tank_volume_ids = load_spec_tank(api_client)
    tank_volume_id = tank_volume_ids["2023-01-04T18:00:00Z"]

    patch_volume(api_client, tank_id, tank_volume_id, 40)
    patch_volume(api_client, tank_id, tank_volume_id, 25)

    assert totals_and_averages(api_client, tank_id) == [
        (20.0, 20.0),
        (0.0, 10.0),
        (20.0, 13.33),
        (0.0, 10.0),
    ]


def test_delete_days_only_reading_removes_its_row(api_client):
    tank_id, tank_volume_ids = load_spec_tank(api_client)

    delete_reading(api_client, tank_id, tank_volume_ids["2023-01-05T11:00:00Z"])

    rows = get_daily_sales(api_client, tank_id, "2023-01-05", "2023-01-05")
    assert rows == [("2023-01-05", "Thursday", 0.0, 10.0, False)]
    assert not TankDailySales.objects.filter(tank_id=tank_id, date="2023-01-05").exists()


def test_delete_previous_days_readings_applies_gap_rule_to_next_day(api_client):
    tank_id, tank_volume_ids = load_spec_tank(api_client)

    delete_reading(api_client, tank_id, tank_volume_ids["2023-01-03T09:00:00Z"])
    # Jan 3 still has 45, so Jan 4 is unchanged: 45 -> 40 + 40 -> 25 = 20.
    assert totals_and_averages(api_client, tank_id)[2] == (20.0, 13.33)

    delete_reading(api_client, tank_id, tank_volume_ids["2023-01-03T15:00:00Z"])
    # No Jan 3 readings: Jan 4's first sale is 0 (gap rule), so Jan 4 = 15.
    assert totals_and_averages(api_client, tank_id) == [
        (20.0, 20.0),
        (0.0, 10.0),
        (15.0, 11.67),
        (0.0, 8.75),
    ]


def test_rejected_corrections_leave_totals_unchanged(api_client):
    tank_id, tank_volume_ids = load_spec_tank(api_client)
    tank_volume_id = tank_volume_ids["2023-01-04T18:00:00Z"]

    created_at_change = api_client.patch(
        f"/api/v1/tanks/{tank_id}/volumes/{tank_volume_id}/",
        {"volume": 1, "created_at": "2023-01-04T18:00:00Z"},
        format="json",
    )
    wrong_tank = api_client.delete(f"/api/v1/tanks/999/volumes/{tank_volume_id}/")

    assert (created_at_change.status_code, wrong_tank.status_code) == (400, 404)
    assert totals_and_averages(api_client, tank_id) == [
        (20.0, 20.0),
        (0.0, 10.0),
        (20.0, 13.33),
        (0.0, 10.0),
    ]
