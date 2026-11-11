# Part 1 — Baseline (Claude's spec)

> **Historical:** the baseline sections describe the first slice as it was built.
> [Finishing Part 1](#finishing-part-1-full-createreadupdatedelete) below replaces its names and
> shapes: `tank_id` in JSON, `*CollectionView` / `*ItemView`, and test files per resource and layer.

Source: `nm_part_1.md`, plus the decisions we settled while going through it.

## Scope

This document covers the **baseline slice** of spec Part 1. The goal is a working skeleton
that sets the patterns everything else follows:

- Django project + `tanks` app, DRF, pytest
- `Tank` and `TankVolume` models, migrations, both registered in the Django admin
- One endpoint: `GET /api/v1/tanks/{id}/`
- API → Service → Repository layering, with abstract base classes and concrete implementations
- Dependency wiring through `dependencies.py`
- Test patterns for the API, service, and repository layers

> **Requirement:** spec Part 1 is not done until **full create/read/update/delete for both `Tank` and
> `TankVolume`** exists. That work is specified in
> [Finishing Part 1](#finishing-part-1-full-createreadupdatedelete) below, and the "Part 1"
> commit only happens once it's in place.

### Definition of done (baseline)

1. `pytest` passes.
2. `GET /api/v1/tanks/{id}/` returns 200 with the response shape below for an existing tank. It returns 404
   for a missing or soft-deleted tank. You can check both with curl or Postman/Insomnia.
3. You can log in to `/admin/`, see both tables, and create tanks and readings there.

---

## Decisions

| Area | Decision |
|---|---|
| Layout | `django-admin startproject config .`: `manage.py` at the repo root, project config in `config/`, app in `tanks/` |
| API framework | Django REST Framework, explicit `APIView`s + serializers (no `ModelViewSet`, since it would bypass our layers) |
| URLs | `/api/v1/...`, trailing slash (Django default) |
| Database | SQLite (Django default). No Docker and no Make; both are intentional, see `nm_part_1.md` |
| Time | `USE_TZ = True`, `TIME_ZONE = "UTC"`: everything is stored in UTC and serialized as ISO 8601 with `Z` |
| Volume type | `DecimalField` to avoid float drift when summing in Part 2 |
| Tank names | **Not** unique (talking point for the README) |
| Deletes | Soft delete on `Tank` only (`deleted_at`). Readings are hard-deleted. FK uses `PROTECT` |
| Soft-deleted tank | Returns 404 from the API. Its readings stay in the DB, hidden through the tank |
| Timezone | `Tank.timezone` (IANA name, default `"UTC"`) sets the **day boundary** for Part 2 |
| Mocking | stdlib `unittest.mock` (no `pytest-mock` dependency) |
| Auth | None on the API for this take-home. Admin uses Django's built-in login. (README talking point) |

---

## Project structure (after baseline)

```
dashfuel_tech_eval/
  manage.py
  pytest.ini
  conftest.py                      # shared fixtures
  requirements.txt
  config/
    settings.py
    urls.py                        # /admin/, /api/v1/ -> tanks.api.urls
    wsgi.py
  tanks/
    models.py
    admin.py
    exceptions.py                  # TankNotFound
    dependencies.py                # get_tank_service()
    migrations/
    api/
      __init__.py
      serializers.py               # TankSerializer
      views.py                     # TankDetailView
      urls.py
    services/
      __init__.py
      tank_service.py              # BaseTankService (ABC), TankService
    repositories/
      __init__.py
      tank_repository.py           # BaseTankRepository (ABC), TankRepository
    tests/
      __init__.py
      test_api.py
      test_services.py
      test_repositories.py
  planning_docs/
```

`startapp` generates `tanks/views.py` and `tanks/tests.py`. We delete both, because the `api/` and
`tests/` packages replace them.

---

## Models (`tanks/models.py`)

### `Tank` → table `tank`

| Field | Django field | Notes |
|---|---|---|
| `id` | `BigAutoField` (implicit) | Auto-increment PK |
| `name` | `CharField(max_length=255)` | Required, not unique |
| `location` | `CharField(max_length=255, blank=True, default="")` | Optional free text |
| `timezone` | `CharField(max_length=64, default="UTC")` | IANA name. Validated against `zoneinfo` in the create/update serializer (next slice) |
| `created_at` | `DateTimeField(auto_now_add=True)` | Audit field, set automatically |
| `updated_at` | `DateTimeField(auto_now=True)` | Audit field, set automatically |
| `deleted_at` | `DateTimeField(null=True, blank=True)` | Soft delete marker. `NULL` = active |

`Meta: db_table = "tank"`. `__str__` returns the name, so the admin is readable.

### `TankVolume` → table `tank_volume`

| Field | Django field | Notes |
|---|---|---|
| `id` | `BigAutoField` (implicit) | Auto-increment PK |
| `tank` | `ForeignKey(Tank, on_delete=PROTECT, related_name="volumes")` | Column is `tank_id` |
| `volume` | `DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])` | Required. Can't be negative |
| `created_at` | `DateTimeField(default=django.utils.timezone.now)` | **Time of the reading.** Client can set it, defaults to now. Not `auto_now_add` |
| `updated_at` | `DateTimeField(auto_now=True)` | Audit field, set automatically |

`Meta`:
- `db_table = "tank_volume"`
- `indexes = [Index(fields=["tank", "created_at"])]`: Part 2 reads "readings for tank X ordered by
  time" constantly, so the index goes in now.
- `ordering = ["tank_id", "created_at"]`

**Why the soft-delete filter lives in the repository, not a custom manager:** a default manager that
hides deleted tanks also hides them from the admin and from related lookups, which is surprising.
Doing the filter in the repository keeps it explicit and in one place. The admin shows every tank
and lets you filter on `deleted_at`.

## Admin (`tanks/admin.py`)

- `TankAdmin`: `list_display = (id, name, location, timezone, created_at, deleted_at)`,
  `list_filter = (deleted_at)`, `search_fields = (name, location)`
- `TankVolumeAdmin`: `list_display = (id, tank, volume, created_at, updated_at)`,
  `list_filter = (tank)`, `date_hierarchy = "created_at"`

---

## Layers

```
HTTP request
  → TankDetailView (api/views.py)          parse input, call service, map exceptions to HTTP status, serialize
  → BaseTankService / TankService          business rules; raises domain exceptions
  → BaseTankRepository / TankRepository    the only layer that touches the ORM
```

Rules:
- Views never import models or the ORM. They get a service from `dependencies.py`.
- Services never touch the ORM directly. They talk to a repository passed into the constructor.
- Repositories return model instances, or `None` when nothing is found. They don't raise "not found".
- Services translate `None` into a domain exception (`TankNotFound`). Views turn that into 404.

### Repository (`tanks/repositories/tank_repository.py`)

```python
class BaseTankRepository(ABC):
    @abstractmethod
    def get_by_id(self, tank_id: int) -> Tank | None: ...

class TankRepository(BaseTankRepository):
    def get_by_id(self, tank_id: int) -> Tank | None:
        return Tank.objects.filter(id=tank_id, deleted_at__isnull=True).first()
```

### Service (`tanks/services/tank_service.py`)

```python
class BaseTankService(ABC):
    @abstractmethod
    def get_tank(self, tank_id: int) -> Tank: ...

class TankService(BaseTankService):
    def __init__(self, repository: BaseTankRepository):
        self._repository = repository

    def get_tank(self, tank_id: int) -> Tank:
        tank = self._repository.get_by_id(tank_id)
        if tank is None:
            raise TankNotFound(tank_id)
        return tank
```

### Exceptions (`tanks/exceptions.py`)

`TankNotFound(Exception)` stores the `tank_id`. In later slices, a shared base (`DomainError`) lets
views map whole groups of errors to status codes.

### Dependencies (`tanks/dependencies.py`)

```python
def get_tank_service() -> BaseTankService:
    return TankService(repository=TankRepository())
```

This is the one place where concrete classes get wired together. Views call it, and API tests patch it.

### API

**Serializer** (`api/serializers.py`): `TankSerializer(ModelSerializer)`, output only, with fields
`id, name, location, timezone, created_at, updated_at`. `deleted_at` is never exposed.

**View** (`api/views.py`):

```python
class TankDetailView(APIView):
    def get(self, request, tank_id: int):
        service = get_tank_service()
        try:
            tank = service.get_tank(tank_id)
        except TankNotFound:
            return Response({"detail": "Tank not found."}, status=404)
        return Response(TankSerializer(tank).data)
```

**URLs**:
- `tanks/api/urls.py`: `path("tanks/<int:tank_id>/", TankDetailView.as_view(), name="tank-detail")`
- `config/urls.py`: `path("api/v1/", include("tanks.api.urls"))` alongside `admin/`

`<int:tank_id>` means a non-integer id gets Django's normal 404 before it reaches our view.

### Response contract

```
GET /api/v1/tanks/1/

200
{
  "id": 1,
  "name": "North Station Tank A",
  "location": "123 Main St",
  "timezone": "UTC",
  "created_at": "2026-11-11T18:30:00.123456Z",
  "updated_at": "2026-11-11T18:30:00.123456Z"
}

404  (missing or soft-deleted)
{ "detail": "Tank not found." }
```

---

## Settings changes (`config/settings.py`)

- `INSTALLED_APPS += ["rest_framework", "tanks"]`
- Confirm `TIME_ZONE = "UTC"`, `USE_TZ = True`
- `REST_FRAMEWORK = {"COERCE_DECIMAL_TO_STRING": False}`: DRF normally serializes Decimals as
  strings. This makes `volume` a JSON number. It doesn't matter yet, but setting it now avoids
  changing the contract later.
- Leave `SECRET_KEY`/`DEBUG` as generated. They're for local development only (README note).

## Trimming Django's defaults

Done **before the first `migrate`**, so no unused app ever creates tables. Most of Django's
default setup exists to support the admin, and we want the admin, so those parts stay.

**Kept:**
- The admin and the apps it depends on: `admin`, `auth`, `contenttypes`, `sessions`, `messages`,
  `staticfiles`
- Their middleware and template context processors (the admin's startup checks require them)
- Security, CSRF, and clickjacking middleware
- `CommonMiddleware` (trailing-slash redirects)
- `apps.py` (where Part 3 will likely register signals)

**Removed or trimmed:**
- `config/asgi.py`: `runserver` uses WSGI
- `MAILERS` and `AUTH_PASSWORD_VALIDATORS`
- `USE_I18N` (now `False`)
- The generated docstrings and comment blocks
- `tanks/views.py` and `tanks/tests.py`
- DRF defaults: the browsable HTML API and form/multipart parsers are gone, and API
  authentication is disabled. The API is **JSON in, JSON out**.

## `.gitignore` additions

```
__pycache__/
*.pyc
db.sqlite3
.pytest_cache/
```

---

## Tests

**Tooling:** `pytest` + `pytest-django`. `pytest.ini`:

```ini
[pytest]
DJANGO_SETTINGS_MODULE = config.settings
python_files = test_*.py
```

**Fixtures (root `conftest.py`):**
- `api_client`: DRF `APIClient()`
- `tank_factory`: a function fixture that creates and returns a saved `Tank`, with overridable kwargs
  (`tank_factory(name="X", deleted_at=now)`). Needs the `db` fixture.
- `tank`: one active tank built with `tank_factory`
- `unsaved_tank`: a `Tank(...)` instance that is **never saved**, with fixed id and timestamps. Used for
  API tests that must not touch the DB.

On copy/deepcopy: pytest fixtures are function-scoped by default, so every test gets its own fresh
object, and pytest-django rolls back the DB after each test. Copying is only needed if we
deliberately add module- or session-scoped fixtures later. We'll use the factory pattern instead
of copying whenever a test needs a variation.

### `test_api.py`: response contract, no DB

Patch `tanks.api.views.get_tank_service` with a `Mock`. These tests are **not** marked
`django_db`, so pytest-django will **fail the test if anything reaches the DB**. That checks the
layer isolation for free.

- `test_get_tank_returns_200_and_expected_shape`: mock returns `unsaved_tank`. Check status 200, the
  exact key set, the values, and that timestamps are ISO 8601 with `Z`.
- `test_get_tank_not_found_returns_404`: mock's `get_tank` raises `TankNotFound`. Check status 404 and
  `{"detail": "Tank not found."}`.
- `test_get_tank_does_not_expose_deleted_at`: key is missing from the response. Could be folded into
  the shape test.

### `test_services.py`: business rules, mocked repository

The service isn't a pure passthrough, because it turns `None` into `TankNotFound`, so it gets two small tests:

- `test_get_tank_returns_tank_from_repository`
- `test_get_tank_raises_when_repository_returns_none`

The repository is a `Mock(spec=BaseTankRepository)`. No DB.

### `test_repositories.py`: real test DB (`@pytest.mark.django_db`)

- `test_get_by_id_returns_active_tank`
- `test_get_by_id_returns_none_for_missing_id`
- `test_get_by_id_returns_none_for_soft_deleted_tank`

---

## Steps (you run commands, I write code)

All commands run from the repo root with the venv activated (`.venv\Scripts\Activate.ps1`).

| # | Who | Step |
|---|---|---|
| 1 | You | `pip install djangorestframework pytest pytest-django` then `pip freeze > requirements.txt` |
| 2 | You | `django-admin startproject config .` |
| 3 | You | `python manage.py startapp tanks` |
| 4 | Me | Update `.gitignore`, settings, and URLs. Write models, admin, layers, serializer, view, `pytest.ini`, `conftest.py`, tests. Delete the generated `tanks/views.py` and `tanks/tests.py` |
| 5 | You | `python manage.py makemigrations tanks`. Check the generated migration together |
| 6 | You | `python manage.py migrate` |
| 7 | You | `pytest -v` |
| 8 | You | `python manage.py createsuperuser` |
| 9 | You | `python manage.py runserver`. Create a tank in `/admin/`, then `curl http://127.0.0.1:8000/api/v1/tanks/1/`, then `/tanks/999/` for the 404 |
| 10 | You | Commit the baseline. Suggested message: `Part 1 baseline: project setup, models, tank detail endpoint, test patterns` |

---

---

# Finishing Part 1: full create/read/update/delete

Source: the "Finishing out part 1" section of `nm_part_1.md`, plus the decisions we settled while going through it.
The **Part 1 commit** happens when this section is done.

## Decisions

| Area | Decision |
|---|---|
| Naming | Explicit everywhere: `tank_id`, `tank_volume_id` in URLs, code, **and JSON**. No bare `id`/`pk` |
| Readings URL | Nested under the tank: `/api/v1/tanks/{tank_id}/volumes/` |
| Readings scope | These endpoints serve **raw readings**. Sales, daily totals, and averages are Part 2, with their own endpoints |
| Single-reading GET | Not built (deliberate; README note). Read = the paginated list |
| Reading `created_at` | Accepted on **POST only** (optional, defaults to now). PATCH corrects `volume` only. A wrong timestamp is fixed by delete + re-POST. This keeps Part 3 simpler: a correction never moves a reading to another day |
| Duplicate timestamps | `UniqueConstraint(tank, created_at)`. "Consecutive" is always well defined for Part 2 |
| Batch POST | Array of 1–1,000 readings, **all or nothing** (one transaction) |
| Tank list | `GET /api/v1/tanks/`, active tanks only, paginated |
| Pagination | `?limit=` (default 100, max 1,000) and `?offset=` (default 0). Envelope: `{count, limit, offset, results}` |
| Unknown fields | Request bodies with fields we don't accept get **400**. DRF normally ignores them silently, so a client sending `created_at` on PATCH would think it worked |
| DELETE | `204 No Content`. Tank = soft delete (`deleted_at = now` in UTC). Reading = hard delete |
| Status codes | 200 read/update, 201 create, 204 delete, 400 validation, 404 not found, 409 conflict with existing data |

## Endpoints

All paths are under `/api/v1/`. Every route with `{tank_id}` returns **404 `Tank not found.`** first if
the tank doesn't exist or is soft-deleted. That's the "bail early" check, done in the service layer.

### Tanks

| Method | Path | Body | Success |
|---|---|---|---|
| GET | `tanks/` | n/a | 200 paginated list of tanks |
| POST | `tanks/` | `name`, `location`, `timezone`: **all required** | 201 tank |
| GET | `tanks/{tank_id}/` | n/a | 200 tank (done; response changes `id` → `tank_id`) |
| PATCH | `tanks/{tank_id}/` | any of `name`, `location`, `timezone` | 200 updated tank |
| DELETE | `tanks/{tank_id}/` | n/a | 204, soft delete. Already-deleted tank = 404 |

Validation:
- `name`: non-blank, at most 255 characters
- `location`: non-blank, at most 255 characters (the API requires it even though the model allows `""`)
- `timezone`: must be in `zoneinfo.available_timezones()`, e.g. `"America/Chicago"`, `"UTC"`

Tank response:

```json
{
  "tank_id": 1,
  "name": "North Station Tank A",
  "location": "123 Main St",
  "timezone": "UTC",
  "created_at": "2026-11-11T15:17:52.621240Z",
  "updated_at": "2026-11-11T15:17:52.621240Z"
}
```

### Tank volumes

| Method | Path | Body | Success |
|---|---|---|---|
| GET | `tanks/{tank_id}/volumes/` | n/a | 200 paginated list, oldest first. Optional `?start=` / `?end=` (ISO 8601; start inclusive, end exclusive) |
| POST | `tanks/{tank_id}/volumes/` | array of `{volume, created_at?}` | 201 array of created readings, in request order |
| PATCH | `tanks/{tank_id}/volumes/{tank_volume_id}/` | `{volume}` | 200 updated reading (single object) |
| DELETE | `tanks/{tank_id}/volumes/{tank_volume_id}/` | n/a | 204, hard delete |

A reading that exists but belongs to a **different tank** returns **404 `Tank volume not found.`**.
The repository always looks readings up by `(tank_volume_id, tank_id)` together.

Validation:
- `volume`: required number, at least 0, at most 12 digits with 2 decimal places
- `created_at` (POST only): ISO 8601. A timestamp without an offset is treated as UTC (`USE_TZ`).
  Omitted means server time.
- Batch:
  - Must be a non-empty JSON array of at most 1,000 items.
  - No two items may share a `created_at` (→ 400).
  - At most one item may omit `created_at`. Several readings stamped "now" in one request would
    collide on the unique constraint.
- Any `created_at` that already exists for this tank → **409**, and the whole batch is rejected.

Reading response:

```json
{
  "tank_volume_id": 57,
  "tank_id": 1,
  "volume": 30.0,
  "created_at": "2023-01-02T10:00:00Z",
  "updated_at": "2026-11-11T15:20:00.000000Z"
}
```

Paginated list response (same shape for tanks):

```json
{
  "count": 7,
  "limit": 100,
  "offset": 0,
  "results": [ { ...reading... } ]
}
```

### Error bodies

- Domain errors (404, 409): `{"detail": "Tank not found."}`
- Validation (400): DRF's default, `{"field": ["message"]}`. For a batch, item errors are keyed by
  the failing item's 0-based position, and only failing items are listed. For example,
  `{"1": {"volume": ["Ensure this value is greater than or equal to 0."]}}` means the second item failed.
  Rules about the whole batch (size, duplicate timestamps) come back as `{"non_field_errors": [...]}`.

## Model change (one migration)

- Add `UniqueConstraint(fields=["tank", "created_at"], name="uniq_tank_volume_tank_created_at")`.
- **Remove** the existing `Index(fields=["tank", "created_at"])`. A unique constraint creates its own
  index on the same columns, so keeping both would just be a duplicate index.

## Code layout changes

```
tanks/
  domain.py                        # NEW: input dataclasses + Page (our "Pydantic models")
  exceptions.py                    # + TankVolumeNotFound, DuplicateTankVolume
  dependencies.py                  # + get_tank_volume_service()
  api/
    exception_handler.py           # NEW: maps DomainError subclasses -> HTTP status
    pagination.py                  # NEW: parse/validate ?limit & ?offset
    serializers/                   # our "Pydantic models": request validation + response shapes
      shared.py                    # RejectUnknownFieldsMixin, validate_timezone_name
      tanks.py
      tank_volumes.py
    views.py                       # TankCollectionView, TankItemView, TankVolumeCollectionView, TankVolumeItemView
    urls.py
  repositories/
    tank_repository.py             # + list_active, create, update, soft_delete
    tank_volume_repository.py      # NEW
  services/
    tank_service.py                # + list/create/update/delete
    tank_volume_service.py         # NEW
```

### Domain types (`tanks/domain.py`)

Plain frozen dataclasses that cross layer boundaries, so the service never receives a raw dict or
a DRF object:

- `TankCreate(name, location, timezone)`
- `TankUpdate(name=None, location=None, timezone=None)`: `None` = not provided
- `TankVolumeCreate(volume: Decimal, created_at: datetime | None)`
- `Page[T](items: list[T], count: int, limit: int, offset: int)`

### Central exception handler

`REST_FRAMEWORK["EXCEPTION_HANDLER"] = "tanks.api.exception_handler.domain_exception_handler"`.
It maps `TankNotFound` / `TankVolumeNotFound` to 404 and `DuplicateTankVolume` to 409, and passes
everything else to DRF's default handler. The views stop needing try/except, and the baseline
`TankDetailView` is simplified to match.

### Layer responsibilities

| Layer | Does |
|---|---|
| API | Parse and validate the request (types, required fields, ranges, timezone name, batch size, duplicates *within* the payload, unknown fields). Build domain dataclasses. Call the service. Serialize the response |
| Service | Check the tank is active (bail early). Check the reading belongs to the tank. Check for duplicates *against the DB*. Open the transaction for the batch insert. Set `deleted_at` |
| Repository | ORM queries only, always filtered by `tank_id` and active status. Returns models, `None`, or `Page` |

### Service interfaces

```python
class BaseTankService(ABC):
    def list_tanks(self, limit: int, offset: int) -> Page[Tank]: ...
    def get_tank(self, tank_id: int) -> Tank: ...
    def create_tank(self, tank_create: TankCreate) -> Tank: ...
    def update_tank(self, tank_id: int, tank_update: TankUpdate) -> Tank: ...
    def delete_tank(self, tank_id: int) -> None: ...

class BaseTankVolumeService(ABC):
    def list_tank_volumes(self, tank_id: int, limit: int, offset: int,
                          start: datetime | None, end: datetime | None) -> Page[TankVolume]: ...
    def create_tank_volumes(self, tank_id: int,
                            tank_volume_creates: list[TankVolumeCreate]) -> list[TankVolume]: ...
    def update_tank_volume(self, tank_id: int, tank_volume_id: int, volume: Decimal) -> TankVolume: ...
    def delete_tank_volume(self, tank_id: int, tank_volume_id: int) -> None: ...
```

`TankVolumeService` takes **both** repositories (the tank repository for the active-tank check).
The service pre-checks for duplicates, which gives a clear 409 listing the clashing timestamps.
The repository runs `bulk_create` inside `transaction.atomic()` and converts an `IntegrityError`
(the pre-check lost a race) to `DuplicateTankVolume`. The transaction lives in the repository,
not the service, so service tests stay database-free.

**View naming:** Django routes each URL to one class, so views are named after the URL's role,
not the operation. `*CollectionView` is `/tanks/` (list, create) and `*ItemView` is
`/tanks/{tank_id}/` (get, update, delete). DRF's usual "List/Detail" names read oddly next to POST.

> Part 3 note: `bulk_create` and `QuerySet.update()` skip `save()` signals. Recalculation should be
> triggered from these service methods, not from signals.

## Tests

Same three-layer pattern as the baseline. API tests mock the service and never touch the DB.

- **API:** for every endpoint, the status code and exact response shape for success; 404 / 409
  mapping; 400 for each validation rule (blank name, bad timezone, negative volume, empty array, 1,001
  items, duplicate `created_at` in the payload, two items without `created_at`, `created_at` on PATCH,
  unknown field); pagination params (invalid / over max limit → 400); `tank_id` / `tank_volume_id`
  key names.
- **Service:** bail early when the tank is missing or soft-deleted (repository write never called);
  reading on a different tank → `TankVolumeNotFound`; duplicate against existing →
  `DuplicateTankVolume`; delete sets `deleted_at`.
- **Repository (DB):** list excludes soft-deleted tanks; `count` / `limit` / `offset` are correct;
  readings are ordered by `created_at`; start/end filter bounds; ownership filter; the unique constraint
  raises; soft delete keeps readings.

New `conftest.py` fixtures: `tank_volume_factory`, `unsaved_tank_volume`.

## API docs (OpenAPI / Swagger)

Added with **drf-spectacular**:

| URL / file | What |
|---|---|
| `/api/docs/` | Swagger UI: every endpoint, request/response shapes, status codes, try-it-out |
| `/api/schema/` | OpenAPI 3 YAML. Insomnia/Postman can import it from this URL |
| `openapi.yaml` (repo root, committed) | The same schema as a file, so a reviewer can import it without running the server |

- Plain `APIView`s don't tell spectacular which serializers they use, so every view method has
  an `@extend_schema(...)` decorator (operation id, summary, tag, request, query params,
  responses, including 400/404/409). Shared pieces live in `tanks/api/openapi.py`.
- `test_openapi_schema.py`:
  - Fails if schema generation emits any warning or the output isn't valid OpenAPI 3.
  - Fails if the committed `openapi.yaml` differs from what the code generates.
- Regenerate after any API change: `python manage.py spectacular --file openapi.yaml`

## Steps

| # | Who | Step |
|---|---|---|
| 1 | Me | Model constraint, domain types, exception handler, pagination, serializers, views, repositories, services, tests. Update the baseline to `tank_id` naming |
| 1b | Me + you | API docs: you install drf-spectacular, I wire it up, you generate `openapi.yaml` |
| 2 | You | `python manage.py makemigrations tanks`. Check it together (adds the constraint, removes the index) |
| 3 | You | `python manage.py migrate` then `pytest -v` |
| 4 | You | Manual pass in Insomnia: create tank → batch POST the spec's example readings → list → PATCH → DELETE → soft delete the tank → confirm 404s |
| 5 | You | **Part 1 commit**, e.g. `Part 1: CRUD endpoints for tanks and tank volumes` |

## Out of scope for Part 1

Sales calculation, daily totals, running averages (Part 2), and recalculation on update (Part 3).
The `(tank, created_at)` index and the `timezone` field are the only Part 2 preparation we do now.
