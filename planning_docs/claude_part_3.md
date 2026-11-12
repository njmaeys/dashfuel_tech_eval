# Part 3 — Keeping daily sales fresh on corrections (Claude's spec)

Source: `nm_part_3.md`, plus the decisions we settled while going through it.

## Scope

- **POST is already done** (Part 2): a batch insert recalculates its affected days in the same
  transaction.
- **Part 3 = PATCH and DELETE on readings** call the same `recalculate_days`, in the same transaction
  as the change.
- Close the admin bypass: readings become read-only in the admin, and a tank's `timezone` can't be
  edited there after creation.
- Document the production pattern (transactional outbox) in a code comment and the README.

### Definition of done

1. `pytest` passes, including end-to-end tests for a PATCH correction and a DELETE.
2. Manually: PATCH a spec reading and see that day's total, the next day's total, and the week's
   running averages change in `GET /tanks/sales/daily/`.
3. `openapi.yaml` is regenerated.

## Decisions

| Area | Decision |
|---|---|
| Transaction | Change the reading, then recalculate the affected days, then **commit together**. If recalculation fails, the change rolls back and the API returns an error |
| Affected days | `{d, d+1}` for the reading's local date `d`. The next day's first sale compares against `d`'s last reading |
| PATCH | Volume only (Part 1), so a reading never moves days. Recalculate `{d, d+1}` |
| DELETE | Read `created_at` **before** deleting, then recalculate `{d, d+1}`. If it was the day's only reading, the day's row is removed and the gap rule applies to `d+1` |
| Running averages | Nothing to do: calculated on read, never stale |
| "Efficiently propagates" | One readings query and at most 2 day rows rewritten per correction. Averages need no propagation |
| Admin: readings | **Read-only** (no add, change, or delete). All reading writes go through the API |
| Admin: tank timezone | **Read-only after creation** (editable on add). A timezone change through the admin would skip the rebuild that the API's PATCH does |
| Production pattern | **Transactional outbox** (below). Comment in code plus one README bullet. Not implemented |
| Concurrency | README bullet only: on Postgres, lock the tank row (`select_for_update`) in write transactions. SQLite already runs writes one at a time |

## Production pattern (comment + README)

What we'd build instead of calling the service directly:

1. In the **same DB transaction** as the reading change, insert an `outbox` row: `tank_id` plus the
   affected dates.
2. A relay (a poller, or change data capture) publishes outbox rows to SQS/EventBridge.
3. A worker consumes them and calls `recalculate_days(tank, dates)`.

Why:
- **No dual write.** Publishing to a queue straight from the API can lose events: the commit succeeds
  and the publish fails, or a crash happens in between. Publishing before the commit lets workers
  read uncommitted data.
- **Idempotent consumer.** `recalculate_days` rebuilds days from the readings rather than applying
  deltas, so duplicate or out-of-order events are harmless and retries are safe.
- **Tradeoff:** totals become eventually consistent (briefly stale after a write). Today they're
  consistent when the API returns.

## Code changes

| File | Change |
|---|---|
| `services/tank_volume_service.py` | `update_tank_volume` and `delete_tank_volume` run the change plus `recalculate_days(tank, affected_dates(...))` inside `self._atomic()`. `_require_tank_volume` returns the tank as well. Add the outbox comment block next to the recalculation helper, and point to it from the POST path |
| `admin.py` | `TankVolumeAdmin` becomes read-only. `TankAdmin.get_readonly_fields` makes `timezone` read-only when editing an existing tank |
| `api/views.py` | The PATCH/DELETE OpenAPI descriptions mention that daily totals are recalculated |
| `openapi.yaml` | Regenerated |
| `README.md` | 2–3 one-line bullets (outbox, concurrency, maybe corrections) and an example step: PATCH a reading and re-check daily sales |

No model changes, so no migration.

## Tests

| File | Database? | Covers |
|---|---|---|
| `test_tank_volume_service.py` | No | PATCH and DELETE recalculate `{d, d+1}` inside the transaction, using the tank's local date. DELETE uses the date captured before deleting. No recalculation when the tank or reading isn't found. No recalculation if the write raises |
| `test_daily_sales_end_to_end.py` | Yes | PATCH Jan 4 18:00 from 25 to 30: Jan 4 = 15, Jan 5 = 0 (30 → 35 is an increase), averages 11.67 / 8.75. PATCH Jan 4 18:00 from 25 to 40: Jan 4 = 5, Jan 5 = 5 (next day changes). DELETE Jan 5's only reading: no Jan 5 row, returns 0. DELETE both Jan 3 readings: Jan 3 = 0, and Jan 4's first sale drops from 5 to 0 under the gap rule (Jan 4 = 15) |
| `test_admin.py` | No | Readings admin is read-only. Tank `timezone` is read-only on change and editable on add |

## Steps

| # | Who | Step |
|---|---|---|
| 1 | Me | Service changes, admin, OpenAPI descriptions, tests. I write and run the tests until green (auto mode), and regenerate `openapi.yaml` |
| 2 | Me | **API check (auto mode, I'll say when):** start the server, create a new tank (so your existing data doesn't need a flush), load the README readings into it, then PATCH and DELETE readings and GET daily sales after each change, reporting the results against the expected values in the end-to-end tests |
| 3 | Me | README bullets and example step |
| 4 | You | **Part 3 commit** |
