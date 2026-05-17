"""
Background tasks for report generation and cleanup.

`generate_report` is the long-running export — it builds the queryset, streams
rows to the chosen exporter, persists progress to the ReportJob row so the API
can report it back to the polling frontend, then notifies the requesting user
via the existing core notification system.

`cleanup_expired_reports` is the daily janitor that removes file blobs and
soft-deletes job rows past their retention window.
"""

import contextlib
import logging
from itertools import islice
from pathlib import Path

from celery import shared_task
from django.conf import settings
from django.core.files import File
from django.db import OperationalError
from django.utils import timezone

from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.models.notifications import notify

from .exporters import get_exporter
from .models import ReportJob
from .registry import registry

logger = logging.getLogger(__name__)

CHUNK_SIZE = 500


def _chunked(iterable, size: int):
    iterator = iter(iterable)
    while chunk := list(islice(iterator, size)):
        yield chunk


def _enforce_row_limit(definition, format_: str, total: int) -> None:
    if format_ == ReportJob.FORMAT_XLSX:
        cap = definition.max_rows_xlsx or settings.REPORT_MAX_ROWS_XLSX
    else:
        cap = definition.max_rows_pdf or settings.REPORT_MAX_ROWS_PDF
    if total > cap:
        msg = (
            f"Report would exceed the row limit for {format_.upper()} "
            f"({total:,} > {cap:,}). Narrow filters or pick another format."
        )
        raise BusinessRuleViolation(msg)


def _safe_count(qs) -> int:
    """Use .count() on QuerySets, len() on lists-of-dicts from .values()."""
    try:
        return qs.count()
    except (AttributeError, TypeError):
        return len(list(qs))


@shared_task(
    bind=True,
    name="pms_api.reports.tasks.generate_report",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    retry_backoff_max=60,
    max_retries=3,
)
def generate_report(self, job_id: str):  # noqa: PLR0915
    """Render a ReportJob's file. Updates `progress` continuously."""
    try:
        job = ReportJob.objects.get(uuid=job_id)
    except ReportJob.DoesNotExist:
        logger.exception("ReportJob uuid=%s not found in DB; aborting task.", job_id)
        return

    job.status = ReportJob.STATUS_RUNNING
    job.started_at = timezone.now()
    job.celery_task_id = self.request.id or ""
    job.save(update_fields=["status", "started_at", "celery_task_id", "updated_at"])

    exporter = None
    try:
        definition = registry.get(job.report_code)

        # Validate filters via the report's declared serializer. Filter values are
        # whatever JSON the user submitted to /export/ — never trust them raw.
        filters_in = (job.params or {}).get("filters", {})
        if definition.filter_serializer_class is not None:
            ser = definition.filter_serializer_class(data=filters_in)
            ser.is_valid(raise_exception=True)
            params = dict(ser.validated_data)
        else:
            params = dict(filters_in)

        include_summary = bool((job.params or {}).get("include_summary"))

        qs = definition.build_queryset(params, user=job.created_by)
        total = _safe_count(qs)
        _enforce_row_limit(definition, job.format, total)

        exporter = get_exporter(job.format, definition)
        exporter.begin()
        written = 0
        for chunk in _chunked(definition.iter_rows(qs, params), CHUNK_SIZE):
            exporter.write_chunk(chunk)
            written += len(chunk)
            pct = min(99, int(written * 100 / max(total, 1)))
            # Tell the Celery result backend so external observers (Flower) see
            # progress, and persist to the row so our own polling endpoint sees
            # the same number. `.filter().update()` skips signals so we don't
            # spam the cached-manager invalidation hooks on every chunk.
            self.update_state(state="PROGRESS", meta={"progress": pct, "rows": written})
            ReportJob.objects.filter(pk=job.pk).update(progress=pct, updated_at=timezone.now())

        if include_summary:
            exporter.write_summary(definition.get_summary(qs, params))

        path, size = exporter.finalize()

        with Path(path).open("rb") as fh:
            filename = f"{definition.code}_{timezone.now():%Y%m%d_%H%M%S}.{exporter.extension}"
            job.file.save(filename, File(fh), save=False)

        # Successful path tears down the temp file Django already copied into MEDIA_ROOT.
        with contextlib.suppress(OSError):
            Path(path).unlink(missing_ok=True)

        # Compare-and-swap: only flip to success if the row is STILL running.
        # If a concurrent /cancel/ already set status=cancelled (or it was
        # failed by retry), we don't overwrite that terminal state.
        finished_at = timezone.now()
        updated_count = ReportJob.objects.filter(
            pk=job.pk,
            status=ReportJob.STATUS_RUNNING,
        ).update(
            file=job.file.name,
            file_size=size,
            row_count=written,
            status=ReportJob.STATUS_SUCCESS,
            progress=100,
            error_message="",
            finished_at=finished_at,
            updated_at=finished_at,
        )
        if updated_count == 0:
            # Lost the race — job was cancelled (or otherwise terminal) before we
            # could mark success. The file we just wrote will be reaped at expiry
            # alongside the row; don't notify the user.
            logger.info(
                "Job %s was no longer RUNNING when generate_report finished; "
                "skipping success update (likely cancelled mid-task).",
                job.uuid,
            )
            return

        # Refresh local instance so `notify`'s GenericFK on the action_object
        # picks up the post-CAS state if a hook walks it.
        job.refresh_from_db()
        try:
            notify(
                recipient=job.created_by,
                verb=f"Report '{definition.name_en or definition.code}' is ready to download",
                action_object=job,
                actor=job.created_by,
            )
        except Exception:  # noqa: BLE001
            logger.warning("Failed to send notification for job %s", job.uuid, exc_info=True)

    except Exception as exc:
        logger.exception("Report job %s failed", job.uuid)
        if exporter is not None:
            exporter.cleanup()
        job.status = ReportJob.STATUS_FAILED
        job.error_message = str(exc)[:2000]
        job.finished_at = timezone.now()
        job.save(
            update_fields=["status", "error_message", "finished_at", "updated_at"],
        )
        # Re-raise so Celery records the failure on the result backend; the
        # autoretry_for tuple decides whether to actually retry.
        raise


@shared_task(name="pms_api.reports.tasks.cleanup_expired_reports")
def cleanup_expired_reports() -> dict:
    """Daily janitor. Removes files past their retention window and soft-deletes the rows."""
    now = timezone.now()
    qs = ReportJob.objects.filter(expires_at__lt=now)
    deleted_files = 0
    deleted_rows = 0
    for job in qs.iterator(chunk_size=100):
        if job.file:
            try:
                # delete(save=False) removes the blob from storage AND clears
                # the in-memory FieldFile.name. We persist that cleared name
                # via the save() below so the DB doesn't keep a stale path.
                job.file.delete(save=False)
                deleted_files += 1
            except OSError:
                logger.warning("Failed to delete file for job %s", job.uuid, exc_info=True)
        # Soft-delete the row AND persist the cleared file/file_size columns.
        # The previous version saved only the soft-delete flags, leaving the DB
        # with `file = "reports/..."` pointing at a now-missing blob — a leaked
        # signed URL hitting the download view would then 500 on file.open().
        job.is_deleted = True
        job.deleted_at = now
        job.deleted_by = None
        job.file_size = None
        job.save(
            update_fields=[
                "file",
                "file_size",
                "is_deleted",
                "deleted_at",
                "deleted_by",
                "updated_at",
            ],
        )
        deleted_rows += 1
    logger.info(
        "cleanup_expired_reports: deleted %d files, %d rows.",
        deleted_files,
        deleted_rows,
    )
    return {"deleted_files": deleted_files, "deleted_rows": deleted_rows}
