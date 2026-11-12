# Part 2 — Daily sales and weekly running average (Claude's spec)

Source: `nm_part_2.md`, plus the decisions we settled while going through it. Where `nm_part_2.md`
still has an older wording (datetimes, UTC-only, "calculate everything on the fly"), this doc
records what we agreed.

## Scope

- New table `tank_daily_sales`: one row per tank per **local** day that has readings.
- Daily totals are recalculated **on write**: the readings batch POST (Part 2) and PATCH/DELETE
  (Part 3) all call the same service method.
- `POST /api/v1/tanks/sales/daily/recalculate/`: on-demand backfill and repair.
- `GET /api/v1/tanks/sales/daily/`: **read only**. Stored totals plus the weekly running average,
  calculated when read.
- README: example data step for the new endpoint, and a decisions section (see [README](#readme)).

### Definition of done

1. `pytest` passes, including an end-to-end test that POSTs the spec's example readings and gets
   back the spec's table: totals **20 / 0 / 20 / 0**, averages **20 / 10 / 13.33 / 10**.
2. The same is visible manually with the README's example data steps.
3. `openapi.yaml` is regenerated, and the schema tests pass.

---

## Decisions

| Area | Decision |
|---|---|
| Storage | Daily totals are **stored** (spec: "store this daily total in a new table"). The running average is **calculated when read** from at most 7 stored totals, so it's never stale |
| When totals are written | On **every** write to readings, for the affected days only. A missing row therefore always means "no readings that day" (= 0), never "not calculated yet" |
| Recalculate endpoint | `POST` (it writes). Synchronous. For backfill/repair, e.g. data written before this feature existed. No management command |
| GET side effects | None. It never reads `tank_volume` and never writes |
| Day boundary | The tank's **local date** (`Tank.timezone`, via `zoneinfo`). The spec example data is in UTC, so its results don't change |
| Week | Monday–Sunday in the tank's local calendar. Only the **running average** resets on Monday |
| Cross-day sale | A day's first reading is compared to the **last reading of the previous local day**, including Sunday → Monday |
| Gap rule (spec, kept as written) | If the previous day has **no** readings, the day's first sale is 0. We don't look further back. A code comment and the README flag it as a rule we'd challenge |
| Days without readings | No stored row. In the GET they appear with total 0 and `fuel_load_received: false`, and they **count in the divisor** ("number of days from Monday") |
| Week starts before the first reading | Same rule: Monday and Tuesday count as 0 days even if the first reading ever is on Wednesday |
| `fuel_load_received` | `true` if any counted pair of consecutive readings for that day (including the cross-day pair) went **up**. Equal volumes don't count. It's a signal only; it doesn't affect sales |
| Rounding | Stored totals are exact (sums of 2-decimal values). The average is rounded to 2 decimal places, half-up, on output |
| Date params | `start_date` / `end_date` are dates, **both inclusive**. GET allows at most 30 days |
| `tank_id` filter | Optional, repeated (`?tank_id=1&tank_id=2`). Unknown or soft-deleted ids are **left out silently**, like a SQL `IN` filter. Non-integer → 400. If omitted: all active tanks |
| Pagination | None on this endpoint (deliberate; README note) |
| Response | Envelope `{start_date, end_date, results}`. Rows sorted by `tank_id`, then `date` |
| `day_of_week` | Derived from `date` in the response (`"Monday"`), not stored |
| Tank timezone change | Changing `Tank.timezone` moves every day boundary, so `update_tank` **rebuilds all of that tank's daily rows** in the same transaction |

## Data model

### `TankDailySales` → table `tank_daily_sales`

| Field | Django field | Notes |
|---|---|---|
| `id` | `BigAutoField` (implicit) | |
| `tank` | `ForeignKey(Tank, on_delete=PROTECT, related_name="daily_sales")` | Column `tank_id` |
| `date` | `DateField` | The tank's **local** date |
| `daily_total_sales` | `DecimalField(max_digits=12, decimal_places=2)` | ≥ 0 |
| `fuel_load_received` | `BooleanField(default=False)` | |
| `calculated_at` | `DateTimeField(auto_now=True)` | When this row was last recalculated |

`Meta`: `db_table = "tank_daily_sales"`, `UniqueConstraint(tank, date)`, `ordering = ["tank_id", "date"]`.

- **No `created_at` / `updated_at`:** recalculation replaces rows (delete + insert), so a creation
  time wouldn't mean anything. `calculated_at` is the one timestamp that does.
- **No `weekly_running_average` or `day_of_week` columns:** both are derived on read (see Decisions).

**Admin:** registered **read-only** (no add, change, or delete), because this is derived data.
Fix it by fixing the readings or running the recalculate endpoint.

---

## Endpoints

### `GET /api/v1/tanks/sales/daily/`

| Query param | Required | Rules |
|---|---|---|
| `start_date` | yes | `YYYY-MM-DD` |
| `end_date` | yes | `YYYY-MM-DD`, ≥ `start_date`, at most 30 days inclusive |
| `tank_id` | no, repeatable | integer |

```json
200
{
  "start_date": "2023-01-02",
  "end_date": "2023-01-05",
  "results": [
    {
      "tank_id": 1,
      "date": "2023-01-02",
      "day_of_week": "Monday",
      "daily_total_sales": 20.0,
      "weekly_running_average": 20.0,
      "fuel_load_received": false
    },
    {
      "tank_id": 1,
      "date": "2023-01-03",
      "day_of_week": "Tuesday",
      "daily_total_sales": 0.0,
      "weekly_running_average": 10.0,
      "fuel_load_received": true
    }
  ]
}
```

400 for validation errors, using the same error format as Part 1. One row is returned per
**active tank × date in the range**, so 2 tanks × 30 days = 60 rows.

### `POST /api/v1/tanks/sales/daily/recalculate/`

```json
Request
{
  "start_date": "2023-01-02",
  "end_date": "2023-01-08",
  "tank_ids": [1, 2]
}

200
{
  "start_date": "2023-01-02",
  "end_date": "2023-01-08",
  "tank_ids": [1],
  "days_with_sales_rows": 4
}
```

- `tank_ids` is optional (JSON array, unlike the GET's repeated query param). Omitted means all
  active tanks.
- The response's `tank_ids` lists the tanks **actually** recalculated. Unknown or soft-deleted ids
  are left out, as in the GET.
- The range is limited to **366 days**, so a single request can't scan unlimited history.
- Unknown request fields return 400, the same rule as Part 1.

---

## Calculation

### Pure functions (`tanks/services/sales_calculations.py`)

No ORM, no Django, just inputs to outputs, so the spec's example is tested directly.

```python
@dataclass(frozen=True)
class DailySalesResult:
    daily_total_sales: Decimal
    fuel_load_received: bool

def calculate_daily_sales(
    volumes_by_date: dict[date, list[Decimal]],   # each day's volumes, in time order
    dates: Iterable[date],                         # the days to calculate
) -> dict[date, DailySalesResult]:                 # only days that have readings

def calculate_weekly_running_averages(
    daily_totals: dict[date, Decimal],             # missing date = 0
    dates: Iterable[date],
) -> dict[date, Decimal]:                          # rounded to 2 dp, half-up
```

`calculate_daily_sales` for day `d`:
1. `d` has no readings → no result (no row).
2. `previous_volume` = the **last** volume of `d - 1` if that day has readings, otherwise `None`.
   *Gap rule (spec): we don't look further back than one day. Code comment flags it.*
3. Walk `d`'s volumes in order. For each one with a previous value:
   `sale = max(previous - current, 0)`. If `current > previous`, mark `fuel_load_received`.
4. Total = sum of the sales.

`calculate_weekly_running_averages` for day `d`: `monday = d - d.weekday()`.
`sum(totals[monday..d]) / ((d - monday).days + 1)`.

### Service (`tanks/services/daily_sales_service.py`)

```python
class BaseDailySalesService(ABC):
    def recalculate_days(self, tank: Tank, dates: set[date]) -> None: ...
    def recalculate_all_days(self, tank: Tank) -> None: ...          # timezone change
    def recalculate_range(self, start_date: date, end_date: date,
                          tank_ids: list[int] | None) -> RecalculationSummary: ...
    def get_daily_sales(self, start_date: date, end_date: date,
                        tank_ids: list[int] | None) -> list[DailySalesRow]: ...
```

**`recalculate_days(tank, dates)`**: the single write path that every trigger calls.
1. Fetch readings from the start of `min(dates) - 1 day` to the end of `max(dates)`, in the tank's
   timezone, converted to UTC for the query. That's one query, ordered by `created_at`.
2. Group them by local date, then call `calculate_daily_sales(...)`.
3. `repository.replace_for_dates(tank_id, dates, results)`: inside a transaction, delete the
   existing rows for those dates, then insert a row for each date that has a result. A date
   that no longer has readings ends up with no row.

**What each trigger recalculates:**

| Trigger | Dates passed to `recalculate_days` |
|---|---|
| Readings batch POST (Part 2) | For each new reading's local date `d`: `{d, d + 1}`. `d + 1`'s first sale compares against `d`'s last reading |
| PATCH / DELETE reading (Part 3) | Same: `{d, d + 1}` for the reading's date |
| Recalculate endpoint | Every date in `[start_date, end_date]`, for each tank in scope |
| Tank timezone change | All of that tank's history (`recalculate_all_days`) |

Running averages aren't stored, so no trigger touches them.

**`get_daily_sales(start_date, end_date, tank_ids)`**:
1. Active tanks in scope (`TankRepository.list_active_by_ids`; `None` = all).
2. Stored rows for those tanks from **the Monday of `start_date`'s week** through `end_date`.
   That's earlier than `start_date`, because the running average needs the days since Monday.
3. Per tank: fill dates without a row as 0/false, calculate the averages, then keep only
   `start_date..end_date`.

### Transactions

The readings batch insert and its daily recalculation must commit **together**; otherwise a failure
leaves new readings with stale totals. The service gets an `atomic` context manager injected
(`django.db.transaction.atomic` in `dependencies.py`, `contextlib.nullcontext` in unit tests), so
service tests stay database-free:

```python
with self._atomic():
    tank_volumes = self._tank_volume_repository.bulk_create(...)
    self._daily_sales_service.recalculate_days(tank, affected_dates)
```

`TankService.update_tank` does the same around the update + `recalculate_all_days` when
`timezone` changes.

### Repositories

| Repository | New methods |
|---|---|
| `TankRepository` | `list_active_by_ids(tank_ids: list[int] \| None) -> list[Tank]` |
| `TankVolumeRepository` | `list_in_range(tank_id, start_at_utc, end_at_utc) -> list[TankVolume]` (ordered); `date_range_utc(tank_id) -> tuple[datetime, datetime] \| None` (first and last reading, for `recalculate_all_days`) |
| `TankDailySalesRepository` (new) | `list_for_tanks(tank_ids, start_date, end_date) -> list[TankDailySales]`; `replace_for_dates(tank_id, dates, results)` |

All of these are simple filters. The business rules stay in the service and the pure functions.

### Domain types (`tanks/domain.py`)

- `DailySalesRow(tank_id, date, daily_total_sales, weekly_running_average, fuel_load_received)`.
  `day_of_week` is added by the serializer.
- `RecalculationSummary(start_date, end_date, tank_ids, days_with_sales_rows)`

---

## Code layout changes

```
tanks/
  models.py                          # + TankDailySales
  admin.py                           # + read-only TankDailySalesAdmin
  domain.py                          # + DailySalesRow, RecalculationSummary
  dependencies.py                    # + get_daily_sales_service(); services get atomic + daily sales service
  repositories/
    tank_repository.py               # + list_active_by_ids
    tank_volume_repository.py        # + list_in_range, date_range_utc
    tank_daily_sales_repository.py   # NEW
  services/
    sales_calculations.py            # NEW: pure functions
    daily_sales_service.py           # NEW
    tank_volume_service.py           # batch create → recalculate_days, inside atomic
    tank_service.py                  # timezone change → recalculate_all_days, inside atomic
  api/
    serializers/daily_sales.py       # NEW: query/body/response serializers
    openapi.py                       # + shared pieces for the new endpoints if needed
    views.py                         # + DailySalesCollectionView (GET), DailySalesRecalculateView (POST)
    urls.py                          # + tanks/sales/daily/, tanks/sales/daily/recalculate/
```

## Tests

| File | Database? | Covers |
|---|---|---|
| `test_sales_calculations.py` | No | Spec example (20/0/20/0 and 20/10/13.33/10). Gap rule. Sunday → Monday crosses the week. Week starting mid-data counts from Monday. Empty days count in the divisor. `fuel_load_received` true on an increase and false when unchanged. Single-reading day. First reading ever = 0. Half-up rounding |
| `test_daily_sales_service.py` | No | Local-date grouping (e.g. `2023-01-03T02:00Z` is Jan 2 in `America/Chicago`). `recalculate_days` asks the repository for the right window and writes the right rows. A day with no readings gets no row. `get_daily_sales` fetches from Monday but returns only the requested range, fills zeros, and leaves out missing tanks |
| `test_tank_volume_service.py` | No | Batch create calls `recalculate_days` with `{d, d+1}` per reading, inside `atomic`. No recalculation if the insert fails |
| `test_tank_service.py` | No | Timezone change triggers `recalculate_all_days`; other changes don't |
| `test_tank_daily_sales_repository.py` | Yes | `replace_for_dates` replaces existing rows, deletes days with no result, and leaves other dates alone. `list_for_tanks` filters by tanks and dates |
| `test_tank_volume_repository.py` | Yes | `list_in_range` bounds and ordering. `date_range_utc` |
| `test_daily_sales_api.py` | No | GET: shape, envelope, `day_of_week`, repeated `tank_id`, 400s (missing dates, end < start, 31 days, bad `tank_id`). POST recalculate: shape and 400s (range > 366 days, unknown field) |
| `test_daily_sales_end_to_end.py` | Yes, **no mocks** | POST the spec's tank and readings through the API, GET daily sales, assert the spec's table. Then a backfill that changes the next day's total |
| `test_tank_daily_sales_model.py` or admin check | n/a | Admin is read-only |

## README

1. **Example data setup:** add step 4, `GET /api/v1/tanks/sales/daily/?start_date=2023-01-02&end_date=2023-01-05`,
   with the expected table (20/20, 0/10, 20/13.33, 0/10).
2. **New "Design decisions" section near the top, right after the intro.** Two parts:
   - **Business rules we follow but would challenge:**
     - The gap rule (Mon 20 → no Tuesday readings → Wed 10 counts as 0 sales).
     - Refills hiding sales, which is why `fuel_load_received` exists.
     - Empty days counting in the running average divisor.
   - **Technical decisions and tradeoffs:**
     - Simple queries with the rules in the service layer (easy to test; costs memory once data is large).
     - Totals stored and recalculated on write; averages calculated on read.
     - Direct service calls instead of events or a queue (simple and transactional; at scale you'd use an outbox or queue).
     - No pagination on daily sales.
     - Tank-local day boundaries.
     - A timezone change rebuilds that tank's history.
     - Plus the Part 1 decisions from my README notes.

## Steps

| # | Who | Step |
|---|---|---|
| 1 | Me | Model, admin, repositories, pure calculations, services, serializers, views, URLs, OpenAPI decorators, tests |
| 2 | You | `python manage.py makemigrations tanks`. Review together (new table + constraint) |
| 3 | You | `python manage.py migrate`, `python manage.py spectacular --file openapi.yaml`, `pytest -q` |
| 4 | You | `python manage.py flush`, then the README example data (tank + 7 readings + GET daily sales) |
| 5 | Me | README updates (example data step + Design decisions) |
| 6 | You | **Part 2 commit**, e.g. `Part 2: daily sales table, recalculation on write, weekly running average endpoint` |

## Out of scope (Part 3)

- Recalculating on reading PATCH/DELETE. The method already exists; Part 3 calls it from those paths.
- Admin edits to readings bypassing the service layer (Part 3 decision: recalculate from the admin,
  or make readings read-only there).
