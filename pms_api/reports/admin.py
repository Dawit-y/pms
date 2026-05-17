from django.contrib import admin

from .models import ReportJob


@admin.register(ReportJob)
class ReportJobAdmin(admin.ModelAdmin):
    list_display = (
        "uuid",
        "report_code",
        "format",
        "status",
        "progress",
        "row_count",
        "created_by",
        "created_at",
        "expires_at",
    )
    list_filter = ("status", "format", "report_code")
    search_fields = ("uuid", "report_code", "celery_task_id", "created_by__email")
    readonly_fields = (
        "uuid",
        "report_code",
        "format",
        "params",
        "status",
        "progress",
        "file",
        "file_size",
        "row_count",
        "error_message",
        "celery_task_id",
        "started_at",
        "finished_at",
        "expires_at",
        "created_by",
        "updated_by",
        "created_at",
        "updated_at",
    )
    ordering = ("-created_at",)
