# DashFuel Tank Analytics API

A Django + Django REST Framework backend for gas station storage tanks and their volume readings.
Built for the DashFuel backend take-home.

## Design decisions

### Business rules followed as written, but worth challenging

- **Gap rule:** a day's first reading only compares to the previous day's last reading. If that day has no readings, the sale is 0 (Mon 20 → no Tue → Wed 10 = 0 sales, not 10).
- **Deliveries hide sales:** an increase counts as 0 sales, so sales between a delivery and the next reading are lost. `fuel_load_received` flags those days.
- **Empty days lower the running average:** they add 0 to the total but 1 to the divisor.

### Technical decisions and tradeoffs

- **API → service → repository layers:** business rules live in services and pure functions, so they're unit tested without a database.
- **Simple queries, logic in Python:** easy to test and reason about; at scale the pairwise calculation would move into SQL (`LAG()`).
- **Daily totals stored, recalculated on write:** POST, PATCH, and DELETE on readings recalculate the reading's day and the next day in the same transaction, so a missing row always means "no readings".
- **Running average calculated on read:** from at most 7 stored totals, so it's never stale and corrections don't need to propagate through the week.
- **Direct service calls, not events:** simple and transactional; at scale this would be an event system that populates a queue.
- **Concurrency:** SQLite serializes writes; on Postgres, lock the tank row (`select_for_update`) so concurrent recalculations can't overwrite each other.
- **Admin can't edit readings or a tank's timezone:** those must go through the API so daily totals are recalculated.
- **Days use the tank's timezone:** changing a tank's timezone rebuilds its daily totals.
- **PATCH corrects volume only:** a wrong timestamp is delete + re-create, so a correction never moves a reading to another day.
- **`Decimal`, not float,** for volumes and sales.
- **No Docker or Make:** not needed to run a SQLite app with a venv in a technical eval project.

## Getting started

Requires Python 3.12+ (Django 6.1).

```bash
python -m venv .venv

# Activate the virtual env per machine type
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
python manage.py migrate           # creates a fresh local SQLite DB
python manage.py createsuperuser   # optional, for the admin
python manage.py runserver
```

## Helpful URLs

| URL | What |
|---|---|
| http://127.0.0.1:8000/api/v1/ | API base |
| http://127.0.0.1:8000/api/docs/ | Swagger UI |
| http://127.0.0.1:8000/api/schema/ | OpenAPI 3 schema |
| http://127.0.0.1:8000/admin/ | Django admin |

## Running tests

```bash
pytest
```

No server needed; pytest-django creates a throwaway test database.

## Importing into Insomnia or Postman

Import [`openapi.yaml`](openapi.yaml), or import from URL `http://127.0.0.1:8000/api/schema/`.

## Example data setup

Loads the spec's example data through the API. Run against a fresh DB (`python manage.py flush` clears one).
Use Swagger UI, Insomnia/Postman, or the `curl` commands below.

### 1. Create a tank

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tanks/ \
  -H "Content-Type: application/json" \
  -d '{"name": "Tank 1", "location": "123 Main St", "timezone": "UTC"}'
```

Returns `201` with `tank_id` (`1` on a fresh DB).

### 2. Add the readings

```bash
curl -X POST http://127.0.0.1:8000/api/v1/tanks/1/volumes/ \
  -H "Content-Type: application/json" \
  -d '[
    {"volume": 30, "created_at": "2023-01-02T10:00:00Z"},
    {"volume": 10, "created_at": "2023-01-02T11:00:00Z"},
    {"volume": 20, "created_at": "2023-01-03T09:00:00Z"},
    {"volume": 45, "created_at": "2023-01-03T15:00:00Z"},
    {"volume": 40, "created_at": "2023-01-04T10:00:00Z"},
    {"volume": 25, "created_at": "2023-01-04T18:00:00Z"},
    {"volume": 35, "created_at": "2023-01-05T11:00:00Z"}
  ]'
```

Returns `201`. Sending it again returns `409` and saves nothing.

### 3. List the readings

```bash
curl http://127.0.0.1:8000/api/v1/tanks/1/volumes/
```

### 4. Get daily sales and the weekly running average

```bash
curl "http://127.0.0.1:8000/api/v1/tanks/sales/daily/?start_date=2023-01-02&end_date=2023-01-05"
```

Matches the spec:

| Date | Daily total | Running average | Fuel load |
|---|---|---|---|
| 2023-01-02 | 20.0 | 20.0 | false |
| 2023-01-03 | 0.0 | 10.0 | true |
| 2023-01-04 | 20.0 | 13.33 | false |
| 2023-01-05 | 0.0 | 10.0 | true |

- Dates are inclusive, max 30 days.
- Filter with `&tank_id=1&tank_id=2`; omit for all tanks.
- To rebuild totals for readings loaded outside the API: `POST /api/v1/tanks/sales/daily/recalculate/` with `{"start_date": "...", "end_date": "..."}`.

### 5. Correct a reading

Change Jan 4 18:00 (`tank_volume_id` 6 on a fresh DB) from 25 to 40:

```bash
curl -X PATCH http://127.0.0.1:8000/api/v1/tanks/1/volumes/6/ \
  -H "Content-Type: application/json" \
  -d '{"volume": 40}'
```

Re-run step 4. Jan 4 and the next day both change:

| Date | Daily total | Running average |
|---|---|---|
| 2023-01-04 | 5.0 | 8.33 |
| 2023-01-05 | 5.0 | 7.5 |
