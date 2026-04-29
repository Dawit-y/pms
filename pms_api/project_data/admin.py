from django.contrib import admin

from pms_api.core.admin import BaseSoftDeleteAdmin

from .models import Contractor
from .models import ContractorAssignment
from .models import Evaluation
from .models import Issue
from .models import Milestone
from .models import MonitoringVisit
from .models import Payment
from .models import Procurement
from .models import ProjectDocument
from .models import ProjectEmployee
from .models import Risk


@admin.register(Contractor)
class ContractorAdmin(BaseSoftDeleteAdmin):
    """Admin for Contractor with soft-delete support."""

    list_display = [
        "name",
        "registration_number",
        "contractor_type",
        "phone",
        "email",
        "is_blacklisted",
    ]
    list_filter = ["contractor_type", "is_blacklisted", "created_at", "is_deleted"]
    search_fields = ["name", "registration_number", "email", "phone", "tin_number"]


@admin.register(ContractorAssignment)
class ContractorAssignmentAdmin(BaseSoftDeleteAdmin):
    """Admin for ContractorAssignment with soft-delete support."""

    list_display = [
        "project",
        "contractor",
        "contract_number",
        "contract_amount",
        "contract_start",
        "contract_end",
    ]
    list_filter = ["contract_start", "contract_end", "created_at", "is_deleted"]
    search_fields = ["project__code", "contractor__name", "contract_number"]


@admin.register(Payment)
class PaymentAdmin(BaseSoftDeleteAdmin):
    """Admin for Payment with soft-delete support."""

    list_display = [
        "project",
        "amount",
        "payment_date",
        "payment_type",
        "is_approved",
        "reference_number",
    ]
    list_filter = ["payment_type", "is_approved", "payment_date", "is_deleted"]
    search_fields = ["project__code", "reference_number", "bank_reference"]


@admin.register(Procurement)
class ProcurementAdmin(BaseSoftDeleteAdmin):
    """Admin for Procurement with soft-delete support."""

    list_display = [
        "project",
        "item_description",
        "procurement_method",
        "estimated_cost",
        "status",
    ]
    list_filter = ["procurement_method", "created_at", "is_deleted"]
    search_fields = ["project__code", "item_description"]


@admin.register(Evaluation)
class EvaluationAdmin(BaseSoftDeleteAdmin):
    """Admin for Evaluation with soft-delete support."""

    list_display = [
        "project",
        "evaluation_type",
        "evaluation_date",
        "evaluator",
        "score",
    ]
    list_filter = ["evaluation_type", "evaluation_date", "created_at", "is_deleted"]
    search_fields = ["project__code", "evaluator__email", "summary"]


@admin.register(Issue)
class IssueAdmin(BaseSoftDeleteAdmin):
    """Admin for Issue with soft-delete support."""

    list_display = [
        "project",
        "title",
        "severity",
        "is_resolved",
        "assigned_to",
        "due_date",
    ]
    list_filter = ["severity", "is_resolved", "due_date", "is_deleted"]
    search_fields = ["project__code", "title", "description"]


@admin.register(MonitoringVisit)
class MonitoringVisitAdmin(BaseSoftDeleteAdmin):
    """Admin for MonitoringVisit with soft-delete support."""

    list_display = [
        "project",
        "visit_date",
        "physical_progress_pct",
        "financial_progress_pct",
        "next_visit_date",
    ]
    list_filter = ["visit_date", "created_at", "is_deleted"]
    search_fields = ["project__code", "findings", "recommendations"]


@admin.register(ProjectDocument)
class ProjectDocumentAdmin(BaseSoftDeleteAdmin):
    """Admin for ProjectDocument with soft-delete support."""

    list_display = [
        "project",
        "title",
        "document_type",
        "version",
        "is_confidential",
        "created_at",
    ]
    list_filter = ["document_type", "is_confidential", "created_at", "is_deleted"]
    search_fields = ["project__code", "title"]


@admin.register(ProjectEmployee)
class ProjectEmployeeAdmin(BaseSoftDeleteAdmin):
    """Admin for ProjectEmployee with soft-delete support."""

    list_display = [
        "project",
        "user",
        "role_on_project",
        "start_date",
        "end_date",
        "is_current",
    ]
    list_filter = ["is_current", "start_date", "is_deleted"]
    search_fields = ["project__code", "user__email"]


@admin.register(Risk)
class RiskAdmin(BaseSoftDeleteAdmin):
    """Admin for Risk with soft-delete support."""

    list_display = [
        "project",
        "title",
        "probability",
        "impact",
        "is_resolved",
        "risk_owner",
    ]
    list_filter = ["probability", "impact", "is_resolved", "is_deleted"]
    search_fields = ["project__code", "title", "description"]


@admin.register(Milestone)
class MilestoneAdmin(BaseSoftDeleteAdmin):
    """Admin for Milestone with soft-delete support."""

    list_display = [
        "project",
        "title",
        "planned_date",
        "actual_date",
        "is_completed",
        "completion_pct",
    ]
    list_filter = ["is_completed", "planned_date", "is_deleted"]
    search_fields = ["project__code", "title", "description"]
