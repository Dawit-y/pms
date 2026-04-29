from django.contrib import admin

from pms_api.core.admin import BaseModelAdmin

from .models import Project
from .models import ProjectStatus


@admin.register(Project)
class ProjectAdmin(BaseModelAdmin):
    """
    Admin interface for Project with history tracking.

    Features:
    - View full change history (click "History" button)
    - Compare versions side-by-side
    - Revert to previous versions
    - Filter by history date and user
    - See soft-deleted projects
    """

    list_display = [
        "code",
        "title",
        "project_type",
        "location",
        "is_active",
        "created_at",
    ]
    list_filter = [
        "is_active",
        "project_type",
        "location",
        "implementing_department",
        "created_at",
    ]
    search_fields = ["code", "title", "description"]

    # History configuration - fields to show in history list
    history_list_display = ["code", "title", "is_active"]

    fieldsets = (
        (
            "Basic Information",
            {
                "fields": ("code", "title", "description", "uuid"),
            },
        ),
        (
            "Classification",
            {
                "fields": ("project_type", "location", "implementing_department"),
            },
        ),
        (
            "Timeline",
            {
                "fields": ("start_date", "planned_end_date", "actual_end_date"),
            },
        ),
        (
            "Budget & Status",
            {
                "fields": ("total_budget", "current_status", "is_active"),
            },
        ),
        (
            "Audit Trail",
            {
                "fields": (
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                    "deleted_at",
                    "deleted_by",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(ProjectStatus)
class ProjectStatusAdmin(BaseModelAdmin):
    """
    Admin interface for ProjectStatus with history tracking.
    """

    list_display = [
        "project",
        "status",
        "visit_date",
        "physical_progress_pct",
        "financial_progress_pct",
        "changed_by",
        "created_at",
    ]
    list_filter = ["status", "visit_date", "created_at"]
    search_fields = ["project__code", "project__title", "remarks"]

    # History configuration
    history_list_display = ["status", "physical_progress_pct", "financial_progress_pct"]

    fieldsets = (
        (
            "Project & Status",
            {
                "fields": ("project", "status", "visit_date"),
            },
        ),
        (
            "Progress",
            {
                "fields": ("physical_progress_pct", "financial_progress_pct"),
            },
        ),
        (
            "Details",
            {
                "fields": ("remarks", "changed_by"),
            },
        ),
        (
            "Audit Trail",
            {
                "fields": (
                    "uuid",
                    "created_at",
                    "created_by",
                    "updated_at",
                    "updated_by",
                    "deleted_at",
                    "deleted_by",
                ),
                "classes": ("collapse",),
            },
        ),
    )
