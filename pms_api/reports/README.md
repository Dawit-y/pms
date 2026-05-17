# Report Generation & Download System

A deep tour of `pms_api/reports/` — what every file does, how the pieces fit together at runtime, and how to add a new report from scratch.

---

## Table of contents

1. [Mental model](#1-mental-model)
2. [File layout](#2-file-layout)
3. [The full lifecycle — step by step through the code](#3-the-full-lifecycle--step-by-step-through-the-code)
   - [3.1 App startup: how reports get discovered](#31-app-startup-how-reports-get-discovered)
   - [3.2 Frontend asks "what reports can I run?"](#32-frontend-asks-what-reports-can-i-run)
   - [3.3 Frontend renders the table: `GET /data/`](#33-frontend-renders-the-table-get-data)
   - [3.4 User clicks Export: `POST /export/`](#34-user-clicks-export-post-export)
   - [3.5 The Celery worker picks up the task](#35-the-celery-worker-picks-up-the-task)
   - [3.6 Frontend polls for status](#36-frontend-polls-for-status)
   - [3.7 User downloads the file (signed URL)](#37-user-downloads-the-file-signed-url)
   - [3.8 Daily cleanup](#38-daily-cleanup)
4. [Permissions model](#4-permissions-model)
5. [Configuration reference](#5-configuration-reference)
6. [Creating a new report — step by step](#6-creating-a-new-report--step-by-step)
7. [Running it locally](#7-running-it-locally)
8. [Troubleshooting](#8-troubleshooting)

---

## 1. Mental model

There are **two distinct flows** sharing the same underlying definition:

```
┌─────────────────────────────────────────────────────────────────────────┐
│   FLOW A: render the table on the frontend (synchronous, paginated)     │
│   React  ─GET /reports/{code}/data/?filters─▶  build_queryset  ─▶  DB   │
│                                                                         │
│   FLOW B: export to a file (asynchronous, background, full dataset)     │
│   React  ─POST /reports/{code}/export/──▶  ReportJob row  ─enqueue─▶    │
│   ┌──────────────────────────────────────────────────────────┐          │
│   │  Celery worker:                                          │          │
│   │    build_queryset → exporter (xlsx/pdf) → save FileField │          │
│   │    update progress → notify on completion                │          │
│   └──────────────────────────────────────────────────────────┘          │
│   React  ─GET /reports/jobs/{uuid}/───▶ poll until status=success       │
│   React  ─GET …/jobs/{uuid}/download/?t=<signed>──▶ FileResponse        │
└─────────────────────────────────────────────────────────────────────────┘
```

Both flows call the same `ReportDefinition.build_queryset()` method — that's the contract that keeps the "20+ reports" maintainable: **one class per report, two ways to consume it.**

The core insight: every report is a Python class. A central `ReportRegistry` holds those classes keyed by a string `code`. The API ViewSet looks up the report by code at request time; the Celery task looks up the report by code at task time. Nothing about the JSON or the file is hard-coded — the column list, filters, queryset, and summary all come from the definition.

---

## 2. File layout

```
pms_api/reports/
├── apps.py                  # ReportsConfig: ready() autodiscovers reports.py files,
│                            #   wires post_migrate signal that creates permissions
├── base.py                  # ReportDefinition abstract base, ColumnSpec dataclass
├── registry.py              # ReportRegistry singleton + @registry.register decorator
├── models.py                # ReportJob model (status, progress, file, etc.)
├── admin.py                 # Django admin for ReportJob (read-only)
├── signing.py               # make_download_token / verify_download_token
├── permissions.py           # IsReportJobOwner + sync_report_permissions helper
├── serializers.py           # ReportDefinitionSerializer, ReportJobSerializer,
│                            #   ExportRequestSerializer
├── views.py                 # ReportViewSet (metadata + data + export action),
│                            #   ReportJobViewSet (list/retrieve/cancel/download)
├── urls.py                  # DRF router → /api/v1/reports/...
├── tasks.py                 # @shared_task generate_report + cleanup_expired_reports
├── exporters/
│   ├── base.py              # Exporter ABC (begin/write_chunk/write_summary/finalize)
│   ├── excel.py             # ExcelExporter — openpyxl write_only Workbook
│   └── pdf.py               # PdfExporter — ReportLab Platypus
├── migrations/
│   ├── 0001_initial.py      # creates report_reportjob table
│   └── 0002_periodic_cleanup.py   # registers daily cleanup PeriodicTask
├── management/commands/
│   └── sync_report_permissions.py # manual fallback for the post_migrate hook
└── tests/                   # registry, signing, exporters, tasks, api
```

Per-app contribution lives **outside** this directory:

```
pms_api/projects/reports.py   # ProjectsByStatusReport, ProjectsByCategoryWithBudgetReport,
                              #   ProjectsByZoneWithBudgetReport
pms_api/budget/reports.py     # BudgetByFiscalYearReport, BudgetByDepartmentReport
```

That's the per-app contribution pattern — each app owning its domain reports, autodiscovered by the central registry.

---

## 3. The full lifecycle — step by step through the code

### 3.1 App startup: how reports get discovered

**`pms_api/reports/apps.py`** is loaded when Django boots:

```python
class ReportsConfig(AppConfig):
    name = "pms_api.reports"

    def ready(self):
        autodiscover_modules("reports")
        post_migrate.connect(sync_report_permissions_signal, sender=self)
```

`autodiscover_modules("reports")` is a Django utility that walks `INSTALLED_APPS` and imports `<app>.reports` if it exists. For us that means:

1. Loads `pms_api.projects.reports` — its module-level code runs, which triggers `@registry.register` on each `ReportDefinition` subclass, mutating the singleton.
2. Loads `pms_api.budget.reports` — same.
3. Any other app you add can just drop a `reports.py` at its root and reports inside will register themselves.

**`pms_api/reports/registry.py`** is where they end up:

```python
class ReportRegistry:
    def __init__(self):
        self._reports: dict[str, ReportDefinition] = {}

    def register(self, cls):
        if cls.code in self._reports:
            raise ImproperlyConfigured(...)
        self._reports[cls.code] = cls()
        return cls

registry = ReportRegistry()  # module-level singleton
```

The decorator instantiates the class once (so column lists are computed once) and stores it by `cls.code`. Duplicates raise `ImproperlyConfigured` to surface name collisions at startup, not at request time.

The `post_migrate` hook ensures a Django `Permission` row exists for every report's `permission_codename`. This is how admins can later assign the permission to a group or user via the Django admin UI without having to write a migration.

---

### 3.2 Frontend asks "what reports can I run?"

**`GET /api/v1/reports/`**

URL dispatch lives in **`pms_api/reports/urls.py`**:

```python
router.register("reports/jobs", ReportJobViewSet, basename="reportjob")
router.register("reports", ReportViewSet, basename="report")
```

Note: `reports/jobs` is registered **before** `reports` so DRF's URL resolver doesn't treat `jobs` as a report `<code>`.

The view is **`ReportViewSet.list`** in **`pms_api/reports/views.py`**:

```python
def list(self, request, *args, **kwargs):
    definitions = registry.allowed_for(request.user)
    ser = ReportDefinitionSerializer(definitions, many=True, context={"request": request})
    return Response(success_response(ser.data))
```

`registry.allowed_for(user)`:

```python
def allowed_for(self, user):
    return [d for d in self._reports.values()
            if not d.permission_codename or user.has_perm(d.permission_codename)]
```

Filtering happens here so a user without `reports.export_projects_by_status` never even sees that report in the list — they can't try to invoke it accidentally.

**`ReportDefinitionSerializer`** (in `serializers.py`) returns a JSON payload for each definition: `code`, tri-lingual names, `description`, the column list (via `definition.get_column_dicts()`), and a `filter_schema` (introspected from the report's filter serializer in `ReportDefinition.get_filter_schema()`).

That `filter_schema` is what the React UI uses to render filter inputs. For each field on the report's filter serializer, it returns:

```json
{
  "location":     {"type": "uuid",   "required": false},
  "start_after":  {"type": "date",   "required": false},
  "is_active":    {"type": "boolean","required": false}
}
```

So the frontend can build the filter form generically without hard-coding each report's filters.

---

### 3.3 Frontend renders the table: `GET /data/`

**`GET /api/v1/reports/projects_by_status/data/?location=...&page=1`**

In **`pms_api/reports/views.py`**:

```python
@action(detail=True, methods=["get"], url_path="data")
def data(self, request, *args, **kwargs):
    definition = registry.get(self.kwargs[self.lookup_field])
    _require_report_perm(request.user, definition)
    params = self._validate_filters(definition, request.query_params)
    qs = definition.build_queryset(params, user=request.user)
    page = self.paginate_queryset(list(definition.iter_rows(qs, params)))
    if page is not None:
        return self.get_paginated_response(page)
    return Response(success_response(list(definition.iter_rows(qs, params))))
```

Notice four things:

1. **Lookup by code, not by PK.** `self.kwargs[self.lookup_field]` resolves the report from the registry. If the code is unknown, `registry.get()` raises `ResourceNotFound` (which the project's exception handler maps to a clean 404 envelope).
2. **Permission check second.** Even if the user could craft the URL, `_require_report_perm` raises `PermissionDenied` if they don't hold `definition.permission_codename`.
3. **Filter validation third.** `_validate_filters` passes the query params through `definition.filter_serializer_class` so we never trust raw input. UUIDs are validated, dates parsed, choices enforced.
4. **Same `build_queryset` as the export.** The /data/ endpoint paginates rows on the way out via the project's `StandardPagination`; the export task streams them all into a file.

---

### 3.4 User clicks Export: `POST /export/`

**`POST /api/v1/reports/projects_by_status/export/`** with body:

```json
{ "format": "xlsx", "filters": {"start_after": "2026-01-01"}, "include_summary": true }
```

In **`pms_api/reports/views.py`**:

```python
@action(detail=True, methods=["post"], url_path="export")
def export(self, request, *args, **kwargs):
    definition = registry.get(self.kwargs[self.lookup_field])
    _require_report_perm(request.user, definition)

    ser = ExportRequestSerializer(data=request.data)
    ser.is_valid(raise_exception=True)

    # 1. concurrency cap
    cap = settings.REPORT_MAX_CONCURRENT_PER_USER  # default 3
    active = ReportJob.objects.filter(
        created_by=request.user, status__in=ReportJob.ACTIVE_STATUSES,
    ).count()
    if active >= cap:
        raise BusinessRuleViolation(...)

    # 2. filter validation (so errors surface synchronously)
    validated_filters = self._validate_filters_dict(
        definition, ser.validated_data.get("filters", {}),
    )

    # 3. persist the job row
    job = ReportJob.objects.create(
        report_code=definition.code,
        format=ser.validated_data["format"],
        params={"filters": validated_filters,
                "include_summary": ser.validated_data.get("include_summary", False)},
        created_by=request.user,
        updated_by=request.user,
    )

    # 4. enqueue the Celery task
    from .tasks import generate_report
    async_result = generate_report.delay(str(job.uuid))
    if async_result and async_result.id:
        ReportJob.objects.filter(pk=job.pk).update(celery_task_id=async_result.id)
        job.celery_task_id = async_result.id

    # 5. respond 202 with status URL
    return Response(
        success_response(ReportJobSerializer(job, context={"request": request}).data),
        status=status.HTTP_202_ACCEPTED,
    )
```

Step-by-step:

- **Concurrency cap** prevents a single user from queueing 50 jobs that fill the media volume. The count check and the `ReportJob.create()` run together inside a `transaction.atomic()` block with `select_for_update()` on the user's existing active rows, so two concurrent `/export/` calls from the same user serialise rather than both squeezing past the cap. Tunable via `REPORT_MAX_CONCURRENT_PER_USER`.
- **Filter validation** runs the user-supplied filters through the report's `filter_serializer_class` and converts UUID/date/Decimal types to JSON-safe strings via `_jsonify()` so they round-trip through `JSONField`.
- **`ReportJob.create`** is the source of truth for the job. Inheriting from `BaseModel` gives it `uuid`, `created_at/updated_at`, `created_by/updated_by`, and soft-delete. `expires_at` defaults inside `ReportJob.save()` to `now + REPORT_FILE_RETENTION_DAYS` (default 7).
- **`generate_report.delay(...)`** hands the job uuid string to Celery. We pass the uuid, not the pk — uuids are stable across DBs and the task message stays small.
- **`async_result.id`** is the Celery task id; we store it back on the row so a later cancel action can revoke it.
- **HTTP 202 Accepted** is the correct status for "I've taken your request, will work on it." The body includes `uuid`, `status_url`, and (because the serializer always emits it) `download_url` which is `null` until the task completes.

The serializer's `download_url` field uses a `SerializerMethodField`:

```python
def get_download_url(self, obj):
    if obj.status != ReportJob.STATUS_SUCCESS or not obj.file:
        return None
    token = make_download_token(obj)
    path = reverse("api:reports:reportjob-download", kwargs={"uuid": obj.uuid}, request=request)
    return f"{path}?t={token}"
```

Fresh token issued on every poll → max leak window is 24h regardless of how long ago the job finished.

---

### 3.5 The Celery worker picks up the task

This is **`pms_api/reports/tasks.py::generate_report`**. The Celery decorator:

```python
@shared_task(
    bind=True,
    name="pms_api.reports.tasks.generate_report",
    autoretry_for=(OperationalError,),    # transient DB errors get auto-retried
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def generate_report(self, job_id: str):
```

`bind=True` gives the function access to `self` (the Task instance), which is needed for `self.update_state(...)` and `self.request.id`.

**The task in detail:**

```python
# Step A — load the job
try:
    job = ReportJob.objects.get(uuid=job_id)
except ReportJob.DoesNotExist:
    logger.exception(...)
    return

# Step B — mark running
job.status = ReportJob.STATUS_RUNNING
job.started_at = timezone.now()
job.celery_task_id = self.request.id or ""
job.save(update_fields=["status", "started_at", "celery_task_id", "updated_at"])
```

`update_fields=` is intentional — it avoids touching the FileField and avoids any accidental signal cascades.

```python
# Step C — resolve definition + re-validate filters
definition = registry.get(job.report_code)
filters_in = (job.params or {}).get("filters", {})
ser = definition.filter_serializer_class(data=filters_in)
ser.is_valid(raise_exception=True)
params = dict(ser.validated_data)
```

We re-validate filters even though `views.py::export` already did, because the row could theoretically be created by other paths (admin, future migration, etc.) and we want the task itself to be safe.

```python
# Step D — build queryset, count rows, enforce cap
qs = definition.build_queryset(params, user=job.created_by)
total = _safe_count(qs)
_enforce_row_limit(definition, job.format, total)
```

`_enforce_row_limit` raises `BusinessRuleViolation` if `total > REPORT_MAX_ROWS_XLSX` (or `_PDF`). Caps are different per format because openpyxl's write-only mode streams much better than ReportLab's Platypus.

```python
# Step E — stream rows into the exporter
exporter = get_exporter(job.format, definition)
exporter.begin()
written = 0
for chunk in _chunked(definition.iter_rows(qs, params), CHUNK_SIZE):  # 500 rows at a time
    exporter.write_chunk(chunk)
    written += len(chunk)
    pct = min(99, int(written * 100 / max(total, 1)))
    self.update_state(state="PROGRESS", meta={"progress": pct, "rows": written})
    ReportJob.objects.filter(pk=job.pk).update(progress=pct, updated_at=timezone.now())
```

Two important details:

1. **`.filter(pk=).update(...)`** bypasses `Model.save()` — that means no signals fire, the FileField isn't touched, and the `CachedManager` doesn't invalidate the model's cache on every chunk. Progress writes are cheap.
2. **`update_state` to Celery** is for Flower / external observers. Our own polling endpoint reads `job.progress` from the DB row, which is what we just updated.

```python
# Step F — optional summary
if include_summary:
    exporter.write_summary(definition.get_summary(qs, params))

# Step G — finalize: write the file blob
path, size = exporter.finalize()    # returns a temp file path
with Path(path).open("rb") as fh:
    filename = f"{definition.code}_{timezone.now():%Y%m%d_%H%M%S}.{exporter.extension}"
    job.file.save(filename, File(fh), save=False)
# the temp file has been copied into MEDIA_ROOT by FieldFile.save — remove the temp.
with contextlib.suppress(OSError):
    Path(path).unlink(missing_ok=True)
```

`job.file.save(name, File(fh), save=False)` is what actually copies the bytes into `MEDIA_ROOT/reports/<YYYY>/<MM>/<uuid>.<ext>`. The `upload_to` callable on `ReportJob.file` defines that path. `save=False` because we want to set several other fields below before issuing the single DB write.

```python
# Step H — atomic compare-and-swap to mark success.
# A concurrent POST /jobs/<uuid>/cancel/ may have already flipped the row to
# status=cancelled while we were writing rows. `update(...)` returns the
# number of rows that matched the WHERE clause, which is 0 if status is no
# longer "running" — in that case we skip the success write and skip the
# notification. Without this, the cancel would be silently undone.
updated = ReportJob.objects.filter(
    pk=job.pk, status=ReportJob.STATUS_RUNNING,
).update(
    file=job.file.name, file_size=size, row_count=written,
    status=ReportJob.STATUS_SUCCESS, progress=100, error_message="",
    finished_at=finished_at, updated_at=finished_at,
)
if updated == 0:
    logger.info("Job %s was no longer RUNNING; skipping success update.", job.uuid)
    return

notify(
    recipient=job.created_by,
    verb=f"Report '{definition.name_en}' is ready to download",
    action_object=job,
    actor=job.created_by,
)
```

`notify(...)` is the existing helper at `pms_api/core/models/notifications.py`. The frontend's notification poller will pick this up via `/api/v1/notifications/` — no new infrastructure needed.

**Why compare-and-swap and not just `save(update_fields=[...])`?** `save()` writes regardless of the current DB state. If the user posted `/cancel/` 50ms before the task hit Step H, the row in DB is already `status=cancelled` — a plain `save()` would overwrite that back to `success`, silently undoing the user's cancel. The CAS makes the final write conditional on the row still being `status=running`.

```python
# Step I — error path
except Exception as exc:
    logger.exception(...)
    if exporter is not None:
        exporter.cleanup()                  # delete the temp file
    job.status = ReportJob.STATUS_FAILED
    job.error_message = str(exc)[:2000]
    job.finished_at = timezone.now()
    job.save(update_fields=["status", "error_message", "finished_at", "updated_at"])
    raise   # re-raise so Celery records the failure on the result backend
```

The `raise` is important: without it, Celery sees the task as "successful" and `autoretry_for` won't fire. With it, Celery records the exception (visible in Flower / `django_celery_results.TaskResult`) and retries transient errors per the `autoretry_for` tuple.

---

#### How the Excel exporter writes the file

**`pms_api/reports/exporters/excel.py::ExcelExporter`**

```python
def begin(self) -> None:
    self._wb = Workbook(write_only=True)        # streaming mode
    ws = self._wb.create_sheet(title=...)
    self._ws = ws                               # MUST set before creating WriteOnlyCells

    for idx, col in enumerate(self.definition.columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = col.width

    # row 1 — title
    title_cell = self._make_cell(self.definition.name_en, font=Font(size=14, bold=True))
    ws.append([title_cell] + [None] * (len(self.definition.columns) - 1))

    # row 2 — tri-lingual header
    header_cells = []
    for col in self.definition.columns:
        label = "\n".join([col.label_en, col.label_am, col.label_or])
        header_cells.append(self._make_cell(label, fill=HEADER_FILL, font=HEADER_FONT))
    ws.append(header_cells)
```

Why `write_only=True`? Default openpyxl loads every cell into memory; for a 200k-row report that's gigabytes. Write-only streams rows out to the zip-backed xlsx file as they're appended, so memory stays flat.

`_make_cell()` uses `WriteOnlyCell(self._ws, value=value)` and then attaches font/fill/alignment. The crucial bug that bit us in tests: `self._ws` must be assigned **before** any `WriteOnlyCell` is constructed because openpyxl's style descriptors walk `cell.parent.parent` to find the workbook.

```python
def write_chunk(self, rows: list[dict]) -> None:
    for row in rows:
        self._ws.append([
            self._format_cell(col, row.get(col.key)) for col in self.definition.columns
        ])
```

`_format_cell` runs `col.formatter` if defined (e.g. the `_money` formatter on monetary columns).

```python
def finalize(self) -> tuple[Path, int]:
    with tempfile.NamedTemporaryFile(prefix="report_", suffix=".xlsx", delete=False) as tmp:
        self._path = Path(tmp.name)
    self._wb.save(self._path)
    return self._path, self._path.stat().st_size
```

The file is written to a temp path; the caller (Celery task) reads it back to copy into `MEDIA_ROOT`. We can't write directly into Django's storage from openpyxl because openpyxl wants a filesystem path.

---

#### How the PDF exporter writes the file

**`pms_api/reports/exporters/pdf.py::PdfExporter`**

ReportLab Platypus is a different mental model from openpyxl: instead of streaming cells, you build a list of "flowables" (Paragraph, Table, Spacer) and hand the whole list to a `SimpleDocTemplate` which paginates them.

```python
def begin(self) -> None:
    headers = ["\n".join([col.label_en, col.label_am, col.label_or])
               for col in self.definition.columns]
    self._rows = [headers]     # row 0 = header; ReportLab repeats it on each page

def write_chunk(self, rows):
    for row in rows:
        self._rows.append([self._cell(col, row.get(col.key))
                          for col in self.definition.columns])

def finalize(self):
    ...
    doc = SimpleDocTemplate(str(self._path),
                            pagesize=orient(page_size),
                            leftMargin=12*mm, rightMargin=12*mm, ...)
    story = self._build_story()
    doc.build(story, onFirstPage=self._page_footer, onLaterPages=self._page_footer)
```

`_build_story()` constructs:

1. `Paragraph(title, title_style)`
2. Optional description paragraph
3. `Table(self._rows, repeatRows=1)` with a `TableStyle` that paints the header row, sets alternating row backgrounds (`ROW_ALT_BG`), applies per-column alignment (LEFT/RIGHT/CENTER from `ColumnSpec.pdf_align`), and adds a thin grid.
4. Optional summary table

`onFirstPage`/`onLaterPages` draw a "Page N" footer via the canvas API.

**Why the PDF row cap is so much lower (5000 vs 200k):** ReportLab builds every row's flowables in Python memory before paginating. Past a few thousand rows it gets slow and expensive. Excel doesn't have this constraint.

---

### 3.6 Frontend polls for status

**`GET /api/v1/reports/jobs/{uuid}/`**

In **`pms_api/reports/views.py::ReportJobViewSet`**:

```python
class ReportJobViewSet(ActionPermissionMixin, mixins.ListModelMixin,
                       mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    lookup_field = "uuid"

    def get_queryset(self):
        qs = ReportJob.objects.select_related("created_by").order_by("-created_at")
        user = self.request.user
        if user.is_superuser or user.has_perm("reports.view_others_reportjob"):
            return qs
        return qs.filter(created_by=user)
```

The queryset scoping ensures `GET /jobs/` only lists the requesting user's jobs (admins with `view_others_reportjob` see everyone's). For single-record retrieve, the lookup still goes through this queryset, so a leaked UUID can't be polled by a different user.

The response is **`ReportJobSerializer`** which exposes:

```json
{
  "uuid": "...",
  "report_code": "projects_by_status",
  "format": "xlsx",
  "status": "running",
  "progress": 47,
  "row_count": null,
  "file_size": null,
  "error_message": "",
  "celery_task_id": "...",
  "started_at": "2026-05-15T10:00:00Z",
  "finished_at": null,
  "expires_at": "2026-05-22T10:00:00Z",
  "status_url": "https://.../api/v1/reports/jobs/<uuid>/",
  "download_url": null
}
```

When `status === "success"`, `download_url` becomes a fully-formed signed URL like `https://.../api/v1/reports/jobs/<uuid>/download/?t=<token>`.

**Recommended polling cadence on the frontend:** 1s for the first 5s, then exponential backoff to 5s, cap at 10s, stop on terminal status. Terminal statuses are `success`, `failed`, `cancelled`.

---

### 3.7 User downloads the file (signed URL)

**`GET /api/v1/reports/jobs/{uuid}/download/?t=<token>`**

**Crucial:** this endpoint is authenticated by the **signed token alone**. It does NOT require an `Authorization: Bearer …` JWT header, a session cookie, or any other HTTP-level auth. That's deliberate — when the React frontend renders `download_url` as a plain `<a href>` and the user clicks it, the browser navigates fresh and no JWT travels with the request. The signed token in the URL carries cryptographic proof of identity, so it IS the authentication.

In **`pms_api/reports/views.py::ReportJobViewSet.download`**:

```python
@action(detail=True, methods=["get"], url_path="download",
        permission_classes=[AllowAny],          # ← token-only; no DRF auth gate
        authentication_classes=[])              # ← don't try to parse a JWT/session
def download(self, request, *args, **kwargs):
    # `objects` (not `all_objects`) so a soft-deleted job returns a clean 404.
    job = get_object_or_404(ReportJob.objects, uuid=self.kwargs["uuid"])

    if job.status != ReportJob.STATUS_SUCCESS or not job.file:
        raise ResourceNotFound("This report is not ready for download yet.")

    token = request.query_params.get("t", "")
    if not token:
        raise ApiPermissionDenied("Missing signed download token.")
    try:
        token_user_id = verify_download_token(token, job.uuid)
    except BadSignature as e:
        raise ApiPermissionDenied("Invalid or expired download token.") from e

    # The token's encoded user_id must match the job's owner. Tokens are only
    # ever issued (by ReportJobSerializer.get_download_url) for jobs the poller
    # could see, so the issuance side already enforced "who can download what" —
    # this check guards against forged/swapped tokens.
    if token_user_id != job.created_by_id:
        raise ApiPermissionDenied("Token does not match this report's owner.")

    filename = f"{job.report_code}_{job.created_at:%Y%m%d_%H%M%S}.{job.format}"
    try:
        file_handle = job.file.open("rb")
    except (FileNotFoundError, OSError) as e:
        # DB says the file exists, disk says it doesn't (e.g. mid-cleanup race
        # or storage corruption). Surface a clean 404 instead of a 500.
        raise ResourceNotFound("The report file is no longer available.") from e
    response = FileResponse(file_handle, as_attachment=True, filename=filename)
    if job.format == ReportJob.FORMAT_XLSX:
        response["Content-Type"] = "application/vnd.openxml...spreadsheetml.sheet"
    elif job.format == ReportJob.FORMAT_PDF:
        response["Content-Type"] = "application/pdf"
    return response
```

Defense in depth — what stops misuse:

1. **The token is cryptographically signed** — `TimestampSigner` HMAC over `<uuid>:<user_id>` with `SECRET_KEY`. Tampering or fabricating one fails `verify_download_token`.
2. **Token expires after 24h** (`REPORT_DOWNLOAD_TOKEN_MAX_AGE`). A leaked URL is dead by the next business day.
3. **Token binds to a specific job uuid** — a token signed for job A returns 403 if pasted into job B's URL (proven by `test_download_rejects_token_for_different_job`).
4. **Token's `user_id` half must match `job.created_by_id`** — the issuance flow (polling endpoint) only hands a token to users who can see the job, and admin-with-`view_others_reportjob` polling another user's job gets a token signed with that owner's id (not their own). So when an admin uses that URL, the check still passes.
5. **Soft-deleted jobs 404** — `ReportJob.objects` filters `is_deleted=False`, so once cleanup runs the URL becomes inert.
6. **Missing-file fallback** — `FileNotFoundError` → 404, not 500.

The response is `FileResponse(...)` which streams the file rather than loading it into memory — important for multi-MB Excel exports.

**Why no HTTP auth?** A signed URL whose validity depends on *also* having a JWT defeats the purpose of signed URLs. Plain `<a href>` clicks from the browser don't send custom headers; only `fetch()` / `axios` with explicit `Authorization` headers do. By making the token sufficient, the React frontend can render the download as a normal link and the browser handles the file save dialog naturally. The 24h expiry plus uuid+user binding keeps the risk bounded.

---

#### The signing module

**`pms_api/reports/signing.py`**:

```python
_signer = TimestampSigner(salt="report-download")

def make_download_token(job):
    return _signer.sign(f"{job.uuid}:{job.created_by_id}")

def verify_download_token(token, expected_uuid):
    raw = _signer.unsign(token, max_age=settings.REPORT_DOWNLOAD_TOKEN_MAX_AGE)
    uuid_str, user_id = raw.split(":", 1)
    if uuid_str != str(expected_uuid):
        raise BadSignature("uuid mismatch")
    return int(user_id)
```

`TimestampSigner` uses Django's `SECRET_KEY` plus the salt to HMAC-sign the payload. `unsign(..., max_age=...)` raises `SignatureExpired` past the configured window (default 24h via `REPORT_DOWNLOAD_TOKEN_MAX_AGE`).

Tokens are **issued fresh on every poll** by `ReportJobSerializer.get_download_url()`. That keeps the leak window bounded to the max_age — even if a user sends a link to a colleague, after 24h that token is dead. The frontend just re-polls and gets a new one.

---

### 3.8 Daily cleanup

**`cleanup_expired_reports`** in `pms_api/reports/tasks.py`:

```python
@shared_task(name="pms_api.reports.tasks.cleanup_expired_reports")
def cleanup_expired_reports() -> dict:
    now = timezone.now()
    qs = ReportJob.objects.filter(expires_at__lt=now)
    deleted_files = deleted_rows = 0
    for job in qs.iterator(chunk_size=100):
        if job.file:
            try:
                job.file.delete(save=False)   # remove blob; clears name in-memory
                deleted_files += 1
            except OSError:
                logger.warning(...)
        # Soft-delete the row AND persist the cleared file/file_size columns
        # in the SAME save so the DB doesn't keep a path pointing at a missing
        # file. Without `file` in update_fields, the row would still report
        # `file = "reports/2026/05/<uuid>.xlsx"` to anyone reading it later.
        job.is_deleted = True
        job.deleted_at = now
        job.deleted_by = None
        job.file_size = None
        job.save(update_fields=[
            "file", "file_size", "is_deleted", "deleted_at", "deleted_by", "updated_at",
        ])
        deleted_rows += 1
    return {"deleted_files": deleted_files, "deleted_rows": deleted_rows}
```

`file.delete(save=False)` removes the blob from storage and clears `instance.file.name` in memory; the subsequent `save(update_fields=["file", …])` persists that cleared name. The row keeps `is_deleted=True` so the audit trail of "user X exported report Y at time Z" survives — only the binary blob is removed.

Combined with the download view using `ReportJob.objects` (not `all_objects`), this means a stale signed URL hitting the endpoint after cleanup returns a clean 404 instead of trying to open a missing file. Both layers — view filter and DB column clearing — must be correct for defense in depth.

The scheduling is set up by data migration **`0002_periodic_cleanup.py`**:

```python
schedule, _ = CrontabSchedule.objects.get_or_create(
    minute="0", hour="3", day_of_week="*", day_of_month="*", month_of_year="*",
    timezone="Africa/Addis_Ababa",
)
PeriodicTask.objects.update_or_create(
    name="reports.cleanup_expired_reports",
    defaults={
        "task": "pms_api.reports.tasks.cleanup_expired_reports",
        "crontab": schedule,
        "enabled": True,
    },
)
```

`django-celery-beat`'s `DatabaseScheduler` (configured in `base.py` as `CELERY_BEAT_SCHEDULER`) reads this `PeriodicTask` row and fires the task every day at 03:00 Africa/Addis_Ababa.

---

## 4. Permissions model

Three layers, each one gating a different thing:

| Permission | Where it's checked | What it gates |
|---|---|---|
| `reports.export_<report_code>` | `_require_report_perm()` in views | Can the user run this specific report (data, summary, export)? Auto-created per report. |
| `reports.view_others_reportjob` | `ReportJobViewSet.get_queryset` | Can the user see *other people's* jobs? Default: only their own. |
| `reports.download_others_reportjob` | (transitive — via `view_others_reportjob`) | An admin holding `view_others_reportjob` can poll any job, and the poll response hands them a signed token for that job's owner. So admin downloads work without an extra check inside the download view. (The codename is kept for forward-compat in case download is split from view later.) |
| `reports.cancel_reportjob` | (advisory — owners can always cancel their own) | Future hook for admin-cancel-anyone. |

**Note on the download endpoint:** the download action is **token-only authenticated** — no Django/DRF permission is checked. Access control is enforced entirely by:
- *who can obtain the token* (the polling endpoint, which IS permission-checked), and
- *the token's signed `user_id` matching `job.created_by_id`* (verified in the download handler).

This is what makes `<a href>` clicks from the browser work without requiring a JWT in the URL.

The per-report codenames are **auto-synced** by:

- `ReportsConfig.ready()` → connects `post_migrate` → `sync_report_permissions_signal()` → `sync_report_permissions()` (in `permissions.py`), which iterates `registry.all()` and creates missing `Permission` rows on the `ReportJob` content type.
- Manual fallback: `uv run python manage.py sync_report_permissions`.

This means: **add a new report, run `migrate` (or just `sync_report_permissions`), and the permission shows up in the Django admin permission picker.**

To grant a user access:
- Django admin → Users → pick user → `User permissions` → search "export_projects_by_status" → save.
- Or programmatically: `user.user_permissions.add(Permission.objects.get(codename="export_projects_by_status"))`.
- Or via Group: assign permissions to a Group, then assign users to the Group.

---

## 5. Configuration reference

All in `config/settings/base.py`. All are env-overridable:

| Setting | Default | What it controls |
|---|---|---|
| `CELERY_BROKER_URL` | `REDIS_URL` | Where Celery picks up tasks |
| `CELERY_RESULT_BACKEND` | `"django-db"` | Where task results are stored (django_celery_results) |
| `CELERY_TIMEZONE` | `"Africa/Addis_Ababa"` | Timezone for Beat schedules |
| `CELERY_TASK_TIME_LIMIT` | `1800` (30min) | Hard kill an export task past this |
| `CELERY_TASK_SOFT_TIME_LIMIT` | `1500` (25min) | Soft signal first |
| `CELERY_WORKER_PREFETCH_MULTIPLIER` | `1` | Fair queuing for long-running tasks |
| `CELERY_TASK_ROUTES` | `reports`/`maintenance` queues | Reports go to a dedicated queue |
| `REPORT_FILE_RETENTION_DAYS` | `7` | How long files survive before cleanup |
| `REPORT_DOWNLOAD_TOKEN_MAX_AGE` | `86400` (24h) | Signed URL validity window |
| `REPORT_MAX_ROWS_XLSX` | `200_000` | Excel export hard cap |
| `REPORT_MAX_ROWS_PDF` | `5_000` | PDF export hard cap |
| `REPORT_MAX_CONCURRENT_PER_USER` | `3` | Per-user queued+running job ceiling |

---

## 6. Creating a new report — step by step

The whole job is one file edit (plus optionally a permission grant).

### Step 1 — pick the host app and create / open `reports.py`

If the report queries `Project` and related child tables, put it in `pms_api/projects/reports.py`. If it crosses several apps' domains, put it in the app that "owns" the primary concept. New apps just create `pms_api/<app>/reports.py` and the autodiscover will find it.

### Step 2 — define a filter serializer

Declarative — one DRF `Serializer` field per filter you want the frontend to render and the queryset to honor:

```python
from rest_framework import serializers

class _MyReportFilterSerializer(serializers.Serializer):
    fiscal_year = serializers.CharField(required=False)
    region      = serializers.UUIDField(required=False)
    min_budget  = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)
```

The fields become the `filter_schema` exposed at `/reports/<code>/` so the React form can render automatically.

### Step 3 — subclass `ReportDefinition`

```python
from pms_api.reports.base import ColumnSpec
from pms_api.reports.base import ReportDefinition
from pms_api.reports.registry import registry

@registry.register
class ContractorsByZoneReport(ReportDefinition):
    code = "contractors_by_zone"      # MUST be unique; "jobs" is reserved (URL conflict)
    name_en = "Contractors by Zone"
    name_am = "ኮንትራክተሮች በዞን"
    name_or = "Kontiraaktaroota Zoonii"
    description = "Active contractor counts grouped by project zone."
    permission_codename = "reports.export_contractors_by_zone"  # convention
    filter_serializer_class = _MyReportFilterSerializer
    pdf_orientation = "landscape"   # "portrait" or "landscape"
    # pdf_page_size = "A4"          # default; "Letter" also supported
    # max_rows_xlsx = 50_000        # override the global cap for this report
```

The `@registry.register` decorator instantiates the class on import. The `permission_codename` does **not** have to follow the `reports.export_<code>` convention but it's strongly recommended — that's what `sync_report_permissions` looks for.

### Step 4 — declare your columns

```python
columns = [
    ColumnSpec(
        key="zone",                           # the dict key produced by build_queryset
        label_en="Zone",
        label_am="ዞን",
        label_or="Zoonii",
        width=24,                             # Excel column width (chars)
        pdf_align="LEFT",                     # LEFT / CENTER / RIGHT
    ),
    ColumnSpec("count", "Contractors", "ኮንትራክተሮች", "Kontiraaktaroota",
               width=14, pdf_align="RIGHT"),
    ColumnSpec("total_value", "Total Contract Value", "ጠቅላላ የውል ዋጋ",
               "Gatii Konyaa Waliigalaa",
               width=22, pdf_align="RIGHT",
               formatter=lambda v: f"{v:,.2f}" if v else ""),
]
```

The `key` is the dict key in each row your `build_queryset` produces. If you use a `.values()` queryset, that key needs to be either a literal column on the FROM table or an annotation/alias you create with `F("...")`.

`formatter` is any callable; if it raises `TypeError`/`ValueError` the raw value is used as a fallback. Common patterns: money formatting, date formatting, percent formatting.

### Step 5 — implement `build_queryset`

This is the only required method override:

```python
from django.db.models import Count
from django.db.models import F
from django.db.models import Sum
from pms_api.project_data.models import Contractor
from pms_api.project_data.models import ContractorAssignment

def build_queryset(self, params, user):
    qs = ContractorAssignment.objects.filter(status__code="active")

    # Apply filters from the validated serializer
    if params.get("fiscal_year"):
        qs = qs.filter(project__budget_request__fiscal_year=params["fiscal_year"])
    if params.get("region"):
        from pms_api.lookups.models import Location
        try:
            region = Location.all_objects.get(uuid=params["region"])
        except Location.DoesNotExist:
            return ContractorAssignment.objects.none().values()
        ids = region.get_descendants(include_self=True).values("id")
        qs = qs.filter(project__location_id__in=ids)
    if params.get("min_budget") is not None:
        qs = qs.filter(contract_amount__gte=params["min_budget"])

    return (
        qs.values(zone=F("project__location__name_en"))
          .annotate(
              count=Count("contractor_id", distinct=True),
              total_value=Sum("contract_amount"),
          )
          .order_by("-count")
    )
```

Three patterns to know:

1. **Subtree filters with MPTT** — Use `node.get_descendants(include_self=True).values("id")` then `.filter(<fk>_id__in=...)`. There are helpers like `_filter_by_location_subtree` already in `pms_api/projects/reports.py` you can copy.
2. **Grouped reports use `.values(...).annotate(...)`** — return dict rows. The keys in `.values(...)` become column accessors.
3. **Detail reports return real model instances** — set `row_serializer_class = MySerializer` on the class; the default `iter_rows()` will serialize through that.

### Step 6 — (optional) override `iter_rows`

The default behavior:
- If `row_serializer_class` is set → iterate with `.iterator(chunk_size=500)` and serialize each instance through that serializer.
- Else → iterate the queryset with `.iterator(chunk_size=500)` too, so even `.values()` querysets don't materialize their full result set into Django's per-queryset cache before the exporter consumes them. Non-queryset iterables (rare — only if you return a plain list from `build_queryset`) get a plain `iter()`.

Override only when you need transformation:

```python
def iter_rows(self, qs, params):
    for row in qs:
        # mutate or enrich the dict before it reaches the exporter
        row["zone"] = row["zone"] or "Unassigned"
        yield row
```

### Step 7 — (optional) override `get_summary`

If you want a footer summary section appended after the rows:

```python
def get_summary(self, qs, params):
    total = 0
    value = Decimal("0")
    for row in qs:
        total += row["count"]
        value += row["total_value"] or Decimal("0")
    return {
        "total_contractors": total,
        "grand_total_value": f"{value:,.2f}",
    }
```

The summary only appears in exports when the client posts `include_summary: true` in the export payload. It's not shown on the /data/ endpoint by default (use the dedicated /summary/ endpoint there).

### Step 8 — register the permission

`makemigrations` + `migrate` will trigger the `post_migrate` signal that creates the permission row. But if you're not running migrations, just run:

```bash
uv run python manage.py sync_report_permissions
```

You'll see `+ Created permission reports.export_contractors_by_zone`. Then in the Django admin, grant that permission to the relevant user or group.

### Step 9 — try it

No migration needed for your new report (the registry is in-memory). Just restart the Django + Celery processes so they re-import `reports.py`. Then:

```bash
# 1. List your reports (should now include yours):
curl -H "Authorization: Bearer $JWT" http://localhost:8000/api/v1/reports/

# 2. Fetch the table:
curl -H "Authorization: Bearer $JWT" \
    "http://localhost:8000/api/v1/reports/contractors_by_zone/data/?fiscal_year=2017"

# 3. Trigger an export:
curl -X POST -H "Authorization: Bearer $JWT" -H "Content-Type: application/json" \
    -d '{"format":"xlsx","filters":{"fiscal_year":"2017"},"include_summary":true}' \
    http://localhost:8000/api/v1/reports/contractors_by_zone/export/
# → returns 202 with {data: {uuid, status_url, ...}}

# 4. Poll:
curl -H "Authorization: Bearer $JWT" http://localhost:8000/api/v1/reports/jobs/<uuid>/

# 5. Follow the download_url when status=success.
```

### Step 10 — add tests

Drop a quick test in `pms_api/reports/tests/test_<your_report>.py`:

```python
import pytest
from pms_api.reports.models import ReportJob

@pytest.mark.django_db
def test_contractors_by_zone_runs(user, grant_perm, contractor_assignments_factory):
    contractor_assignments_factory(n=10)
    grant_perm(user, "reports.export_contractors_by_zone")
    job = ReportJob.objects.create(
        report_code="contractors_by_zone",
        format="xlsx",
        params={"filters": {}},
        created_by=user, updated_by=user,
    )
    from pms_api.reports.tasks import generate_report
    generate_report.apply(args=[str(job.uuid)])
    job.refresh_from_db()
    assert job.status == ReportJob.STATUS_SUCCESS
    assert job.row_count > 0
```

The `CELERY_TASK_ALWAYS_EAGER = True` in `config/settings/test.py` makes the task run inline in-process, so the test is simple.

---

## 7. Running it locally

### Native (Windows) — no Docker

```powershell
# 1. Have Redis running on localhost:6379 (download Redis for Windows or run in WSL)

# 2. Run Django as usual
uv run python manage.py migrate
uv run python manage.py runserver

# 3. In a second terminal, start a worker (note -P solo for Windows)
uv run celery -A config worker -l info -P solo --queues default,reports,maintenance

# 4. In a third terminal, start the Beat scheduler (for daily cleanup)
uv run celery -A config beat -l info

# 5. (optional) Flower for monitoring
uv run celery -A config flower
# → http://localhost:5555
```

### Docker

```bash
docker compose -f docker-compose.local.yml up
# spins up django + postgres + redis + celeryworker + celerybeat + flower
```

### Production

The production compose now contains `redis`, `celeryworker`, `celerybeat`, and `flower` services in addition to django + postgres + traefik + nginx.

---

## 8. Troubleshooting

**"Unknown report code" 404 on /data/ or /export/**
- The report's `reports.py` wasn't imported. Check `INSTALLED_APPS` includes the host app and the file is named exactly `reports.py` at the app root.
- Or the import raised an error — check Django startup logs.

**Permission denied (403) when listing reports**
- The user doesn't hold `reports.export_<code>`. Grant via Django admin or `user.user_permissions.add(...)`.

**Task stuck in `queued` forever**
- Celery worker isn't running, or it's not subscribed to the `reports` queue. Confirm `--queues default,reports,maintenance` is set on the worker.

**Task stuck in `running`, no progress updates**
- Worker is alive but throwing inside the task. Check worker logs and Flower at `:5555`. The error message also appears in `ReportJob.error_message` after the task crashes.

**Clicking the download link does nothing / "no file to download"**
- Most often: the frontend is fetching the URL via `fetch()` / `axios` with credentials, and the request is being CORS-blocked or rewritten. Use a plain `<a href={download_url}>` with `target="_blank"` (or `rel="noopener noreferrer"`) and let the browser handle navigation — the signed token is the auth, no headers needed.
- Verify the URL contains `?t=…`. If `download_url` is null in the poll response, the job isn't `status === "success"` yet.
- If your frontend hand-crafts the URL: stop. Use the `download_url` field from the poll response verbatim — it carries the fresh signed token.

**Download returns 403 "Missing signed download token"**
- The URL is missing the `?t=...` query string. Always use the `download_url` from the poll response — don't hand-craft it.

**Download returns 403 "Invalid or expired download token"**
- Token is older than 24h (`REPORT_DOWNLOAD_TOKEN_MAX_AGE`). Re-poll to get a fresh one.

**Download returns 403 "Token does not match this report's owner"**
- Token was swapped between jobs (e.g. job-A's token in job-B's URL) or the row's `created_by_id` was changed under it. The frontend should always pair each token with the same job uuid it was polled from.

**Download returns 404 "The report file is no longer available"**
- The DB row says the file exists but the blob is missing from storage. Likely cause: the file was deleted out-of-band, or the cleanup task ran between the poll and the click. Re-export.

**"Report would exceed the row limit"**
- The report has more rows than `REPORT_MAX_ROWS_XLSX` or `REPORT_MAX_ROWS_PDF` allow. Narrow the filters, or bump the cap per-report via `max_rows_xlsx` / `max_rows_pdf` on the definition, or globally via the setting.

**"You already have N active report jobs (limit M)"**
- Per-user concurrency cap hit. Wait for an active job to finish, or cancel one via `POST /jobs/<uuid>/cancel/`.

**Permission codenames not created**
- `post_migrate` ran before the registry was populated. Run `uv run python manage.py sync_report_permissions` manually.

**Celery on Windows: "ValueError: not enough values to unpack"**
- Default prefork pool isn't supported on Windows. Pass `-P solo` (or `-P gevent` if you want parallelism).
