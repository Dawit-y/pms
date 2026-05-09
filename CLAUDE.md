# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

PMS API — a Django 6 / DRF 3.17 REST API for an enterprise project management system used by a governmental bureau (Ethiopian context: tri-lingual lookups in `name_en` / `name_am` / `name_or`, MPTT location hierarchy of Region→Zone→Woreda→Kebele, default `TIME_ZONE = "Africa/Addis_Ababa"`). Scaffolded from cookiecutter-django; dependencies are managed by **uv** (see `pyproject.toml` + `uv.lock`), Python 3.12+.

## Commands

All Python entrypoints go through `uv run` (the venv is `.venv/`). Default settings for `manage.py` is `config.settings.local`; pytest forces `config.settings.test`.

```bash
# Run server / migrations / shell
uv run python manage.py runserver
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py check_security      # custom: audits security config

# Tests (pytest-django; pytest.ini sets --reuse-db --nomigrations)
uv run pytest                                # all tests
uv run pytest pms_api/accounts/tests/test_auth_api.py        # one file
uv run pytest pms_api/accounts/tests/test_auth_api.py::TestLogin::test_ok  # one test
uv run pytest -m "not slow"                  # skip slow markers
uv run pytest --cov=pms_api                  # with coverage

# Lint / format / types (ruff config + mypy plugins are in pyproject.toml)
uv run ruff check .
uv run ruff format .
uv run mypy pms_api
```

`justfile` wraps the Docker compose flow (`just up`, `just manage <cmd>`, etc.) and uses `docker-compose.local.yml`. Local dev without Docker is the common path — `.env` at repo root supplies `DATABASE_URL`, `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `REDIS_URL`.

Settings selection: `DJANGO_SETTINGS_MODULE` ∈ `config.settings.{local,production,test}`. All inherit from `config/settings/base.py`.

## Architecture

### The `BaseModel` + `BaseModelViewSet` contract

Almost every domain model and ViewSet inherits from a centralized base. Understanding these two classes is essential before touching any app — features below are implemented **once** and inherited.

**`pms_api/core/models/base.py` → `BaseModel`** composes these mixins (in `core/models/mixins.py`):

- `UUIDMixin` — every record has a public `uuid` (used as the URL lookup, not the integer PK).
- `TimestampMixin` — `created_at`, `updated_at`.
- `AuditMixin` — `created_by` / `updated_by` FKs to `accounts.User` (auto-populated by `AuditSerializerMixin` from `request.user`).
- `SoftDeleteMixin` — `is_deleted` / `deleted_at` / `deleted_by`. Overrides `delete()` to soft-delete; `hard_delete()` is the escape hatch. Provides `objects` (filtered) and `all_objects` (everything) managers.
- `RowLevelSecurityMixin` — optional `owner` FK, used by `IsOwnerOrAdmin` and `SecureQuerySetMixin`.
- `SignalMixin` — emits the custom `model_changed` / `model_deleted` signals from `core/signals.py` on save/delete. Subclasses **must call `Model.connect_signals()`** at module level (see `accounts/models.py:101`).

**`HistoryMixin`** (django-simple-history) is **opt-in**, not part of `BaseModel`. Add it to a model that needs change tracking: `class Project(HistoryMixin, BaseModel)`. Note: `simple_history.middleware.HistoryRequestMiddleware` is currently commented out in `base.py` — history records won't capture the request user until it's re-enabled.

The `User` model is a special case: it defines its own `UserManager` to reconcile MRO between Django's `BaseUserManager` and `SoftDeleteManager`.

**`pms_api/core/views.py` → `BaseModelViewSet`** is what every resource ViewSet should inherit from. It bundles:

- `lookup_field = "uuid"` — URLs use UUIDs, never integer PKs.
- `SecureQuerySetMixin.get_queryset()` filters by soft-delete and applies row-level security: non-staff see only records they own OR records whose `department` is in their department subtree (uses MPTT `get_descendants`). Set `row_security_enabled = False` on lookup-style ViewSets. Admins/staff can pass `?include_deleted=true` to see soft-deleted rows.
- `get_object()` returns **HTTP 410 Gone** (not 404) when a UUID exists but is soft-deleted, by raising `SoftDeletedResourceError`.
- Built-in extra actions: `POST /restore/`, `DELETE /hard-delete/` (superuser only), `POST /bulk-delete/`, `POST /bulk-restore/`.
- All CRUD methods are wrapped in `@transaction.atomic` and emit standardized info/warning logs.
- `serializer_classes: dict` — set this to dispatch different serializers per action (e.g. `{"list": ListSer, "create": CreateSer}`); falls back to `serializer_class`.
- `action_permissions: dict` (from `ActionPermissionMixin`) — per-action permission overrides on top of `permission_classes`. Use this for custom business actions (e.g. `"approve": [permission_required("projects.approve_project")]`).

Use `BaseReadOnlyViewSet` for lookup-style endpoints (no row security, list+retrieve only).

### Response envelope and exception handler

Every successful response is wrapped:

```json
{ "success": true, "data": ..., "meta": { "count", "page", "pages", "per_page", "next", "previous" } }
```

- List responses come from `core/pagination.py::StandardPagination` (default 25, max 200, `?per_page=` to override, `?page=` to navigate).
- Single-object responses use the `success_response()` helper.

Errors are normalized by `core/exceptions.py::custom_exception_handler` (registered as `REST_FRAMEWORK["EXCEPTION_HANDLER"]`):

```json
{ "success": false, "error": { "code": "RESOURCE_NOT_FOUND", "message": "...", "detail": {...} } }
```

Custom exception classes live in the same file: `ResourceNotFound` (404), `PermissionDenied` (403), `BusinessRuleViolation` (422), `ConflictError` (409), `SoftDeletedResourceError` (410). Raise these instead of returning ad-hoc error responses.

### Permissions

`core/permissions.py` defines the permission vocabulary:

- `StrictDjangoModelPermissions` — DRF's `DjangoModelPermissions` plus `view_<model>` enforcement on GET (the default lacks this). This is `BaseModelViewSet.permission_classes` by default.
- `permission_required("app.codename", ...)` — factory for custom Django permission codenames; declare them in the model's `Meta.permissions`.
- `IsOwnerOrAdmin`, `IsDepartmentMemberOrAdmin`, `IsSuperAdmin`, `IsStaffOrReadOnly`.
- `ActionPermissionMixin` (already on `BaseModelViewSet`) — wires `action_permissions` dict.

So the standard pattern is: keep `permission_classes = [StrictDjangoModelPermissions]` for CRUD, and override per-action via `action_permissions`.

### URLs and versioning

- All API URLs are mounted at `/api/v1/` (URL-path versioning, `DEFAULT_VERSION = "v1"`).
- `config/api_router.py` is the single inclusion point — it includes each app's `urls.py`.
- Each app's `urls.py` builds its own `DefaultRouter() if settings.DEBUG else SimpleRouter()` (the browsable API root is hidden in prod).
- Schema/docs: `/api/v1/schema/`, `/api/v1/docs/`, `/api/v1/redoc/` — served via drf-spectacular, restricted to `IsAdminUser` outside DEBUG.

### Apps

- `core` — base classes, mixins, permissions, throttling, pagination, exception handler, custom `AccessLogMiddleware` (logs authenticated POST/PUT/PATCH/DELETE), notifications ViewSet, management commands (`check_security`, `archive_history`).
- `accounts` — custom `User` (email-as-username, soft-delete-aware manager), JWT views (`CustomTokenObtainPairView`, refresh, logout), `MeView`, `ChangePasswordView`, plus `Group` / `Permission` / `ContentType` ViewSets for RBAC admin. URL prefixes are flat (`/login/`, `/me/`, `/users/`, …).
- `lookups` — `LookupType` / `Lookup` (admin-defined dropdown values, tri-lingual), `Location` and `Department` (both **MPTT** trees — use `get_descendants(include_self=True)` when querying subtrees).
- `projects` — `Project` (uses `HistoryMixin`), `ProjectStatus`.
- `budget` — `BudgetRequest` and approval workflow.
- `project_data` — child entities of a project: contractors, payments, milestones, issues, monitoring visits, evaluations, risks, procurements, employees, documents.

### Tests

- `pytest.ini` runs with `--reuse-db --nomigrations`; the test settings module uses `MD5PasswordHasher` for speed.
- Shared fixtures live in `pms_api/conftest.py`: `api_client`, `user`, `staff_user`, `superuser`, `authenticated_client`, `staff_client`, `admin_client`, plus `project_type`, `location`, `department`.
- Markers: `slow`, `integration`, `unit`, `api` (declared in `pytest.ini`; `pyproject.toml` adds `pytest-django`'s `--ds=config.settings.test --reuse-db`).
- Per-file ruff ignores in `pyproject.toml` allow asserts, magic numbers, and hardcoded test passwords inside `**/tests/**`.

### Conventions worth knowing

- **UUIDs in URLs.** When writing a new ViewSet, don't override `lookup_field`; the base sets it to `uuid`.
- **Soft delete first.** `model.delete()` sets flags; `model.hard_delete()` is the only way to truly remove a row. Querysets via `.objects` already exclude deleted; use `.all_objects` to see everything.
- **Audit fields are auto-set.** Subclass `BaseModelSerializer` (or include `AuditSerializerMixin`) so `created_by`/`updated_by` get filled from `self.context["request"].user`.
- **Don't bypass the envelope.** Return through `success_response()` / `StandardPagination` or raise one of the custom `APIException` subclasses — clients depend on the shape.
- **Throttle scopes** are defined in `REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]`: `anon`, `user`, `burst`, `sustained`, `auth`, `password_reset`, `admin`. Apply stricter scopes to sensitive views via `throttle_classes = [AuthRateThrottle]` etc.
- **Imports are single-line** (`ruff` config: `lint.isort.force-single-line = true`); line length is 100.
