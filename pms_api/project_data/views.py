from django.db import transaction
from django.db.models import Count
from django.db.models import Prefetch
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.pagination import success_response
from pms_api.core.permissions import permission_required
from pms_api.core.views import BaseModelViewSet
from pms_api.project_data.filters import RiskFilter
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
from pms_api.project_data.serializers import ContractorAssignmentSerializer
from pms_api.project_data.serializers import ContractorSerializer
from pms_api.project_data.serializers import EvaluationSerializer
from pms_api.project_data.serializers import IssueCommentCreateSerializer
from pms_api.project_data.serializers import IssueCommentSerializer
from pms_api.project_data.serializers import IssueSerializer
from pms_api.project_data.serializers import MilestoneSerializer
from pms_api.project_data.serializers import MonitoringVisitSerializer
from pms_api.project_data.serializers import PaymentSerializer
from pms_api.project_data.serializers import ProcurementSerializer
from pms_api.project_data.serializers import ProjectDocumentSerializer
from pms_api.project_data.serializers import ProjectEmployeeSerializer
from pms_api.project_data.serializers import RiskSerializer

# ─── ProjectEmployee ViewSet ──────────────────────────────────────────────────


class ProjectEmployeeViewSet(BaseModelViewSet):
    """
    Manages employees assigned to projects with their roles and rates.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "user", "role_on_project", "is_current"]
    search_fields = ["user__email", "user__first_name", "user__last_name"]
    ordering_fields = ["start_date", "created_at"]
    ordering = ["-start_date"]
    serializer_class = ProjectEmployeeSerializer

    queryset = ProjectEmployee.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("project", "user", "role_on_project")
            .order_by("-start_date")
        )


# ─── ProjectDocument ViewSet ──────────────────────────────────────────────────


class ProjectDocumentViewSet(BaseModelViewSet):
    """
    Manages project documents with version control and confidentiality flags.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "document_type", "is_confidential"]
    search_fields = ["title", "version"]
    ordering_fields = ["created_at", "expiry_date"]
    ordering = ["-created_at"]
    serializer_class = ProjectDocumentSerializer

    queryset = ProjectDocument.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("project", "document_type")
            .order_by("-created_at")
        )


# ─── Contractor ViewSet ───────────────────────────────────────────────────────


class ContractorViewSet(BaseModelViewSet):
    """
    Manages contractor registry with blacklist functionality.
    """

    row_security_enabled = False
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["contractor_type", "is_blacklisted"]
    search_fields = ["name", "registration_number", "tin_number", "email"]
    ordering_fields = ["name", "created_at"]
    ordering = ["name"]
    serializer_class = ContractorSerializer

    action_permissions = {
        "blacklist": [permission_required("project_data.blacklist_contractor")],
        "unblacklist": [permission_required("project_data.blacklist_contractor")],
    }

    queryset = Contractor.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("contractor_type")
            .annotate(
                assignment_count=Count(
                    "assignments",
                    filter=Q(assignments__project__is_deleted=False),
                ),
            )
            .order_by("name")
        )

    def _check_delete_allowed(self, instance):
        if instance.assignments.exists():
            msg = (
                "Cannot delete a contractor with existing assignments. "
                "Remove or reassign contracts first."
            )
            raise BusinessRuleViolation(msg)

    @extend_schema(summary="Blacklist a contractor")
    @action(detail=True, methods=["post"], url_path="blacklist")
    @transaction.atomic
    def blacklist(self, request, *args, **kwargs):
        contractor = self.get_object()
        reason = request.data.get("reason", "")

        if not reason:
            msg = "Blacklist reason is required."
            raise BusinessRuleViolation(msg)

        contractor.is_blacklisted = True
        contractor.blacklist_reason = reason
        contractor.save(update_fields=["is_blacklisted", "blacklist_reason"])

        return Response(
            success_response(
                ContractorSerializer(contractor).data,
                message="Contractor blacklisted successfully.",
            ),
        )

    @extend_schema(summary="Remove contractor from blacklist")
    @action(detail=True, methods=["post"], url_path="unblacklist")
    @transaction.atomic
    def unblacklist(self, request, *args, **kwargs):
        contractor = self.get_object()
        contractor.is_blacklisted = False
        contractor.blacklist_reason = ""
        contractor.save(update_fields=["is_blacklisted", "blacklist_reason"])

        return Response(
            success_response(
                ContractorSerializer(contractor).data,
                message="Contractor removed from blacklist.",
            ),
        )


# ─── ContractorAssignment ViewSet ─────────────────────────────────────────────


class ContractorAssignmentViewSet(BaseModelViewSet):
    """
    Manages contractor assignments to projects with contract details.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "contractor", "status"]
    search_fields = ["contract_number", "contractor__name"]
    ordering_fields = ["contract_start", "created_at"]
    ordering = ["-contract_start"]
    serializer_class = ContractorAssignmentSerializer

    queryset = ContractorAssignment.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("project", "contractor", "status")
            .annotate(
                approved_payments_total=Sum(
                    "payments__amount",
                    filter=Q(payments__is_approved=True),
                ),
            )
            .order_by("-contract_start")
        )


# ─── Payment ViewSet ──────────────────────────────────────────────────────────


class PaymentViewSet(BaseModelViewSet):
    """
    Manages payments to contractors with approval workflow.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = [
        "project",
        "contractor_assignment",
        "payment_type",
        "is_approved",
    ]
    search_fields = ["reference_number", "bank_reference"]
    ordering_fields = ["payment_date", "created_at"]
    ordering = ["-payment_date"]
    serializer_class = PaymentSerializer

    action_permissions = {
        "approve": [permission_required("project_data.approve_payment")],
    }

    queryset = Payment.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "project",
                "contractor_assignment__contractor",
                "approved_by",
            )
            .order_by("-payment_date")
        )

    @extend_schema(summary="Approve a payment")
    @action(detail=True, methods=["post"], url_path="approve")
    @transaction.atomic
    def approve(self, request, *args, **kwargs):
        payment = self.get_object()

        if payment.is_approved:
            msg = "Payment is already approved."
            raise BusinessRuleViolation(msg)

        payment.is_approved = True
        payment.approved_by = request.user
        payment.save(update_fields=["is_approved", "approved_by"])

        return Response(
            success_response(
                PaymentSerializer(payment).data,
                message="Payment approved successfully.",
            ),
        )


# ─── MonitoringVisit ViewSet ──────────────────────────────────────────────────


class MonitoringVisitViewSet(BaseModelViewSet):
    """
    Manages monitoring visits with progress tracking and status updates.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "visit_date"]
    search_fields = ["findings", "recommendations"]
    ordering_fields = ["visit_date", "created_at"]
    ordering = ["-visit_date"]
    serializer_class = MonitoringVisitSerializer

    queryset = MonitoringVisit.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("project")
            .prefetch_related("visit_team")
            .order_by("-visit_date")
        )


# ─── Evaluation ViewSet ───────────────────────────────────────────────────────


class EvaluationViewSet(BaseModelViewSet):
    """
    Manages project evaluations with scoring and summaries.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "evaluation_type", "evaluator"]
    search_fields = ["summary"]
    ordering_fields = ["evaluation_date", "score", "created_at"]
    ordering = ["-evaluation_date"]
    serializer_class = EvaluationSerializer

    queryset = Evaluation.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("project", "evaluator")
            .order_by("-evaluation_date")
        )


# ─── Risk ViewSet ─────────────────────────────────────────────────────────────


class RiskViewSet(BaseModelViewSet):
    """
    Manages project risks with probability, impact, and mitigation plans.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = RiskFilter
    search_fields = ["title", "description", "mitigation_plan"]
    ordering_fields = ["created_at"]
    ordering = ["-created_at"]
    serializer_class = RiskSerializer

    action_permissions = {
        "resolve": [],
    }

    queryset = Risk.all_objects.all()

    def get_queryset(self):
        return (
            super().get_queryset().select_related("project", "risk_owner").order_by("-created_at")
        )

    @extend_schema(summary="Mark a risk as resolved")
    @action(detail=True, methods=["post"], url_path="resolve")
    @transaction.atomic
    def resolve(self, request, *args, **kwargs):
        risk = self.get_object()
        risk.is_resolved = True
        risk.save(update_fields=["is_resolved"])

        return Response(
            success_response(
                RiskSerializer(risk).data,
                message="Risk marked as resolved.",
            ),
        )

    @extend_schema(summary="Risk heatmap")
    @action(detail=False, methods=["get"], url_path="heatmap")
    def heatmap(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        project_param = request.query_params.get("project")

        if project_param:
            queryset = queryset.filter(project__uuid=project_param)

        heatmap_data = (
            queryset.order_by().values("probability", "impact").annotate(count=Count("id"))
        )
        heatmap = {
            "low": {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            },
            "medium": {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            },
            "high": {
                "low": 0,
                "medium": 0,
                "high": 0,
                "critical": 0,
            },
        }

        for row in heatmap_data:
            heatmap[row["probability"]][row["impact"]] = row["count"]

        return Response(
            success_response(heatmap),
        )


# ─── Milestone ViewSet ────────────────────────────────────────────────────────


class MilestoneViewSet(BaseModelViewSet):
    """
    Manages project milestones with completion tracking.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "is_completed"]
    search_fields = ["title", "description"]
    ordering_fields = ["planned_date", "actual_date", "created_at"]
    ordering = ["planned_date"]
    serializer_class = MilestoneSerializer

    action_permissions = {
        "complete": [],
    }

    queryset = Milestone.all_objects.all()

    def get_queryset(self):
        return super().get_queryset().select_related("project").order_by("planned_date")

    @extend_schema(summary="Mark a milestone as completed")
    @action(detail=True, methods=["post"], url_path="complete")
    @transaction.atomic
    def complete(self, request, *args, **kwargs):
        milestone = self.get_object()

        milestone.is_completed = True
        milestone.actual_date = timezone.now().date()
        milestone.completion_pct = 100
        milestone.save(update_fields=["is_completed", "actual_date", "completion_pct"])

        return Response(
            success_response(
                MilestoneSerializer(milestone).data,
                message="Milestone marked as completed.",
            ),
        )


# ─── Issue ViewSet ────────────────────────────────────────────────────────────


class IssueViewSet(BaseModelViewSet):
    """
    Manages project issues with severity levels and assignments.
    """

    lookup_field = "uuid"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "severity", "assigned_to", "is_resolved"]
    search_fields = ["title", "description"]
    ordering_fields = ["due_date", "created_at"]
    ordering = ["-created_at"]
    serializer_class = IssueSerializer

    action_permissions = {
        "resolve": [],
        "summary": [
            permission_required("project_data.view_issue"),
        ],
    }

    queryset = Issue.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("project", "assigned_to")
            .prefetch_related(
                Prefetch(
                    "comments",
                    queryset=IssueComment.objects.select_related("created_by"),
                ),
            )
            .order_by("-created_at")
        )

    @extend_schema(summary="Mark an issue as resolved")
    @action(detail=True, methods=["post"], url_path="resolve")
    @transaction.atomic
    def resolve(self, request, *args, **kwargs):
        issue = self.get_object()
        issue.is_resolved = True
        issue.save(update_fields=["is_resolved"])

        return Response(
            success_response(
                IssueSerializer(issue).data,
                message="Issue marked as resolved.",
            ),
        )

    @extend_schema(summary="Issue summary")
    @action(detail=False, methods=["get"], url_path="summary")
    def summary(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        project_param = request.query_params.get("project")

        if project_param:
            queryset = queryset.filter(project__uuid=project_param)

        total = queryset.count()

        resolved = queryset.filter(
            is_resolved=True,
        ).count()

        open_count = queryset.filter(
            is_resolved=False,
        ).count()

        severity_counts = queryset.order_by().values("severity").annotate(count=Count("id"))
        by_severity = {row["severity"]: row["count"] for row in severity_counts}

        return Response(
            success_response(
                {
                    "total": total,
                    "by_severity": by_severity,
                    "open": open_count,
                    "resolved": resolved,
                },
            ),
        )

    # ── Issuecomment ──────────────────────────────

    @extend_schema(
        summary="List or create issue comments",
        request=IssueCommentCreateSerializer,
    )
    @action(detail=True, methods=["get", "post"], url_path="comments")
    @transaction.atomic
    def comments(self, request, *args, **kwargs):
        issue = self.get_object()
        if request.method == "GET":
            serializer = IssueCommentSerializer(
                issue.comments.order_by("created_at"),
                many=True,
            )
            return Response(
                success_response(serializer.data),
            )
        serializer = IssueCommentCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        comment = serializer.save(issue=issue)

        return Response(
            success_response(
                IssueCommentSerializer(comment).data,
                message="Comment added successfully.",
            ),
            status=status.HTTP_201_CREATED,
        )


# ─── Procurement ViewSet ──────────────────────────────────────────────────────


class ProcurementViewSet(BaseModelViewSet):
    """
    Manages project procurement with tender and award tracking.
    """

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["project", "procurement_method", "status"]
    search_fields = ["item_description"]
    ordering_fields = ["tender_date", "award_date", "created_at"]
    ordering = ["-created_at"]
    serializer_class = ProcurementSerializer

    queryset = Procurement.all_objects.all()

    def get_queryset(self):
        return super().get_queryset().select_related("project", "status").order_by("-created_at")
