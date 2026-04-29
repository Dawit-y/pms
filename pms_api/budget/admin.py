from django.contrib import admin

from pms_api.core.admin import BaseSoftDeleteAdmin

from .models import BudgetForwardingStep
from .models import BudgetRequest


@admin.register(BudgetRequest)
class BudgetRequestAdmin(BaseSoftDeleteAdmin):
    """Admin for BudgetRequest with soft-delete support."""

    list_display = [
        "project",
        "requested_amount",
        "approved_amount",
        "status",
        "fiscal_year",
        "created_at",
    ]
    list_filter = ["status", "fiscal_year", "created_at", "is_deleted"]
    search_fields = ["project__code", "project__title", "fiscal_year"]

    fieldsets = (
        (
            "Project",
            {
                "fields": ("project",),
            },
        ),
        (
            "Budget Details",
            {
                "fields": (
                    "requested_amount",
                    "approved_amount",
                    "fiscal_year",
                    "justification",
                    "status",
                    "current_department",
                ),
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


@admin.register(BudgetForwardingStep)
class BudgetForwardingStepAdmin(BaseSoftDeleteAdmin):
    """Admin for BudgetForwardingStep with soft-delete support."""

    list_display = [
        "budget_request",
        "step_number",
        "from_department",
        "to_department",
        "action",
        "acted_by",
        "created_at",
    ]
    list_filter = ["action", "created_at", "is_deleted"]
    search_fields = ["budget_request__project__code", "acted_by__email", "remarks"]
