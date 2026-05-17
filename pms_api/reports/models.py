"""
ReportJob — one row per export request.

Lifecycle: queued → running → success | failed | cancelled.
Carries the celery task id so the API can revoke a running job.
"""

from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from pms_api.core.models.base import BaseModel


def _report_upload_to(instance, filename: str) -> str:
    """Place the generated file under reports/<YYYY>/<MM>/<uuid>.<ext>."""
    now = timezone.now()
    ext = instance.format
    return f"reports/{now.year}/{now.month:02d}/{instance.uuid}.{ext}"


class ReportJob(BaseModel):
    FORMAT_XLSX = "xlsx"
    FORMAT_PDF = "pdf"
    FORMAT_CHOICES = [
        (FORMAT_XLSX, "Excel"),
        (FORMAT_PDF, "PDF"),
    ]

    STATUS_QUEUED = "queued"
    STATUS_RUNNING = "running"
    STATUS_SUCCESS = "success"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_QUEUED, "Queued"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]
    TERMINAL_STATUSES = (STATUS_SUCCESS, STATUS_FAILED, STATUS_CANCELLED)
    ACTIVE_STATUSES = (STATUS_QUEUED, STATUS_RUNNING)

    report_code = models.CharField(max_length=100, db_index=True)
    format = models.CharField(max_length=8, choices=FORMAT_CHOICES)
    params = models.JSONField(default=dict, blank=True)

    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_QUEUED,
        db_index=True,
    )
    progress = models.PositiveSmallIntegerField(default=0)

    file = models.FileField(upload_to=_report_upload_to, null=True, blank=True, max_length=500)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    row_count = models.PositiveIntegerField(null=True, blank=True)

    error_message = models.TextField(blank=True)
    celery_task_id = models.CharField(max_length=64, blank=True, db_index=True)

    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["created_by", "-created_at"]),
            models.Index(fields=["status", "expires_at"]),
        ]
        permissions = [
            ("cancel_reportjob", "Can cancel a running report job"),
            ("download_others_reportjob", "Can download other users' report files"),
            ("view_others_reportjob", "Can view other users' report jobs"),
        ]

    def __str__(self) -> str:
        return f"ReportJob({self.report_code}, {self.status})"

    def save(self, *args, **kwargs):
        # expires_at defaults to now + retention window. Setting at save time
        # (not as a default lambda) keeps it pinned to the moment the job was
        # created even if the row is re-saved later.
        if not self.expires_at:
            days = getattr(settings, "REPORT_FILE_RETENTION_DAYS", 7)
            self.expires_at = timezone.now() + timedelta(days=days)
        super().save(*args, **kwargs)

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    @property
    def is_active(self) -> bool:
        return self.status in self.ACTIVE_STATUSES
