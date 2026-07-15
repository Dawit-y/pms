from django.conf import settings
from django.utils import timezone
from rest_framework import serializers

from pms_api.core.serializers import BaseModelSerializer
from pms_api.project_data.models import Contractor
from pms_api.project_data.models import ContractorAssignment
from pms_api.project_data.models import Evaluation
from pms_api.project_data.models import Issue
from pms_api.project_data.models import IssueComment
from pms_api.project_data.models import Milestone
from pms_api.project_data.models import MonitoringVisit
from pms_api.project_data.models import Payment
from pms_api.project_data.models import Procurement
from pms_api.project_data.models import ProjectDocument
from pms_api.project_data.models import ProjectEmployee
from pms_api.project_data.models import Risk

# ─── ProjectEmployee Serializers ──────────────────────────────────────────────


class ProjectEmployeeSerializer(BaseModelSerializer):
    user_email = serializers.CharField(source="user.email", read_only=True)
    user_name = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role_on_project.name_en", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)

    class Meta:
        model = ProjectEmployee
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "user",
            "user_email",
            "user_name",
            "role_on_project",
            "role_name",
            "start_date",
            "end_date",
            "daily_rate",
            "is_current",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_user_name(self, obj) -> str:
        return f"{obj.user.first_name} {obj.user.last_name}".strip() or obj.user.email


# ─── ProjectDocument Serializers ──────────────────────────────────────────────


class ProjectDocumentSerializer(BaseModelSerializer):
    document_type_name = serializers.CharField(
        source="document_type.name_en",
        read_only=True,
    )
    project_code = serializers.CharField(source="project.code", read_only=True)
    file_url = serializers.SerializerMethodField()
    file_size = serializers.SerializerMethodField()

    class Meta:
        model = ProjectDocument
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "title",
            "document_type",
            "document_type_name",
            "file",
            "file_url",
            "file_size",
            "version",
            "is_confidential",
            "expiry_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_file_url(self, obj) -> str | None:
        if obj.file:
            request = self.context.get("request")
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None

    def get_file_size(self, obj) -> str | None:
        if not obj.file:
            return None

        size = obj.file.size
        kilobyte = 1024
        megabyte = kilobyte * 1024

        if size < kilobyte:
            return f"{size} B"
        if size < megabyte:
            return f"{size / 1024:.1f} KB"
        return f"{size / megabyte:.1f} MB"

    def validate_file(self, value):
        if value.size > settings.MAX_DOCUMENT_UPLOAD_SIZE:
            max_mb = settings.MAX_DOCUMENT_UPLOAD_SIZE / (1024 * 1024)
            message = f"File size exceeds the limit. Maximum allowed size is {max_mb:.1f} MB."
            raise serializers.ValidationError(message)
        return value


# ─── Contractor Serializers ───────────────────────────────────────────────────


class ContractorSerializer(BaseModelSerializer):
    contractor_type_name = serializers.CharField(
        source="contractor_type.name_en",
        read_only=True,
    )
    assignment_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Contractor
        fields = [
            "id",
            "uuid",
            "name",
            "registration_number",
            "contractor_type",
            "contractor_type_name",
            "tin_number",
            "phone",
            "email",
            "address",
            "is_blacklisted",
            "blacklist_reason",
            "assignment_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]


# ─── ContractorAssignment Serializers ─────────────────────────────────────────


class ContractorAssignmentSerializer(BaseModelSerializer):
    contractor_name = serializers.CharField(source="contractor.name", read_only=True)
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    status_name = serializers.CharField(source="status.name_en", read_only=True)
    total_payments = serializers.SerializerMethodField()

    class Meta:
        model = ContractorAssignment
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "contractor",
            "contractor_name",
            "contract_number",
            "contract_amount",
            "contract_start",
            "contract_end",
            "scope_of_work",
            "status",
            "status_name",
            "total_payments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_total_payments(self, obj) -> str:
        # Populated by an annotation on the viewset queryset; falls back to 0.
        total = getattr(obj, "approved_payments_total", None) or 0
        return str(total)


# ─── Payment Serializers ──────────────────────────────────────────────────────


class PaymentSerializer(BaseModelSerializer):
    contractor_name = serializers.CharField(
        source="contractor_assignment.contractor.name",
        read_only=True,
    )
    contract_number = serializers.CharField(
        source="contractor_assignment.contract_number",
        read_only=True,
    )
    project_code = serializers.CharField(source="project.code", read_only=True)
    approved_by_email = serializers.CharField(
        source="approved_by.email",
        read_only=True,
        default=None,
    )

    class Meta:
        model = Payment
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "contractor_assignment",
            "contractor_name",
            "contract_number",
            "payment_type",
            "amount",
            "payment_date",
            "reference_number",
            "bank_reference",
            "is_approved",
            "approved_by",
            "approved_by_email",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at", "approved_by"]


# ─── MonitoringVisit Serializers ──────────────────────────────────────────────


class MonitoringVisitSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    visit_team_emails = serializers.SerializerMethodField()

    class Meta:
        model = MonitoringVisit
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "visit_date",
            "visit_team",
            "visit_team_emails",
            "physical_progress_pct",
            "financial_progress_pct",
            "findings",
            "recommendations",
            "next_visit_date",
            "status_changed_to",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_visit_team_emails(self, obj) -> list[str]:
        return [user.email for user in obj.visit_team.all()]


# ─── Evaluation Serializers ───────────────────────────────────────────────────


class EvaluationSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    evaluator_email = serializers.CharField(source="evaluator.email", read_only=True)
    evaluator_name = serializers.SerializerMethodField()

    class Meta:
        model = Evaluation
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "evaluation_type",
            "evaluator",
            "evaluator_email",
            "evaluator_name",
            "evaluation_date",
            "score",
            "summary",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_evaluator_name(self, obj) -> str:
        return (
            f"{obj.evaluator.first_name} {obj.evaluator.last_name}".strip() or obj.evaluator.email
        )


# ─── Risk Serializers ─────────────────────────────────────────────────────────


class RiskSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    risk_owner_email = serializers.CharField(source="risk_owner.email", read_only=True)
    risk_level = serializers.SerializerMethodField()
    score = serializers.ReadOnlyField()

    class Meta:
        model = Risk
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "title",
            "description",
            "probability",
            "impact",
            "score",
            "risk_level",
            "mitigation_plan",
            "risk_owner",
            "risk_owner_email",
            "is_resolved",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_risk_level(self, obj) -> str:
        """Calculate risk level based on probability and impact."""
        critical_threshold = 9
        high_threshold = 6
        medium_threshold = 3

        total = obj.score

        if total >= critical_threshold:
            return "critical"
        if total >= high_threshold:
            return "high"
        if total >= medium_threshold:
            return "medium"
        return "low"


# ─── Milestone Serializers ────────────────────────────────────────────────────


class MilestoneSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    status = serializers.SerializerMethodField()
    days_overdue = serializers.SerializerMethodField()
    is_overdue = serializers.ReadOnlyField()

    class Meta:
        model = Milestone
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "title",
            "description",
            "planned_date",
            "actual_date",
            "is_completed",
            "completion_pct",
            "status",
            "days_overdue",
            "is_overdue",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_status(self, obj) -> str:
        if obj.is_completed:
            return "completed"

        # if obj.planned_date < timezone.now().date():
        if obj.is_overdue:
            return "overdue"
        return "on_track"

    def get_days_overdue(self, obj) -> int | None:
        if obj.is_completed or not obj.planned_date:
            return None

        delta = (timezone.now().date() - obj.planned_date).days
        return delta if delta > 0 else None


# ─── IssueComment Serializers ──────────────────────────────────────────────────


class IssueCommentSerializer(BaseModelSerializer):
    class Meta:
        model = IssueComment
        fields = ["uuid", "body", "created_at", "created_by_email"]


# ─── IssueCommentCreate Serializers ──────────────────────────────────────────────────


class IssueCommentCreateSerializer(BaseModelSerializer):
    class Meta:
        model = IssueComment
        fields = [
            "body",
        ]

    def validate_body(self, value):
        value = value.strip()
        if not value:
            message = "Comment body can not be empty."
            raise serializers.ValidationError(message)
        return value


# ─── Issue Serializers ────────────────────────────────────────────────────────


class IssueSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    assigned_to_email = serializers.CharField(
        source="assigned_to.email",
        read_only=True,
        default=None,
    )
    status = serializers.SerializerMethodField()
    is_overdue = serializers.ReadOnlyField()
    comments = IssueCommentSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Issue
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "title",
            "description",
            "severity",
            "assigned_to",
            "assigned_to_email",
            "due_date",
            "is_resolved",
            "status",
            "is_overdue",
            "comments",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_status(self, obj) -> str:
        if obj.is_resolved:
            return "resolved"
        # if obj.due_date:
        #     if obj.due_date < timezone.now().date():
        if obj.is_overdue:
            return "overdue"
        return "open"


# ─── Procurement Serializers ──────────────────────────────────────────────────


class ProcurementSerializer(BaseModelSerializer):
    project_code = serializers.CharField(source="project.code", read_only=True)
    project_title = serializers.CharField(source="project.title", read_only=True)
    status_name = serializers.CharField(source="status.name_en", read_only=True)
    cost_variance = serializers.SerializerMethodField()

    class Meta:
        model = Procurement
        fields = [
            "id",
            "uuid",
            "project",
            "project_code",
            "project_title",
            "item_description",
            "procurement_method",
            "estimated_cost",
            "actual_cost",
            "cost_variance",
            "tender_date",
            "award_date",
            "status",
            "status_name",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_cost_variance(self, obj) -> str | None:
        if obj.actual_cost and obj.estimated_cost:
            variance = obj.actual_cost - obj.estimated_cost
            return str(variance)
        return None
