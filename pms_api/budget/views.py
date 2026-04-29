from django.db import transaction
from django.db.models import Count
from django.db.models import Sum
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework.decorators import action
from rest_framework.response import Response

from pms_api.budget.models import BudgetForwardingStep
from pms_api.budget.models import BudgetRequest
from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.models.notifications import notify
from pms_api.core.pagination import success_response
from pms_api.core.permissions import IsSuperAdmin
from pms_api.core.permissions import permission_required
from pms_api.core.views import BaseModelViewSet
from pms_api.projects.models import ProjectStatus

from .serializers import ApproveSerializer
from .serializers import BudgetRequestCreateSerializer
from .serializers import BudgetRequestDetailSerializer
from .serializers import BudgetRequestListSerializer
from .serializers import ForwardSerializer
from .serializers import RejectSerializer


class BudgetRequestViewSet(BaseModelViewSet):
    lookup_field = "uuid"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["status", "current_department", "fiscal_year", "project"]
    search_fields = ["project__code", "project__title", "fiscal_year"]
    ordering_fields = ["created_at", "requested_amount"]
    ordering = ["-created_at"]

    serializer_classes = {
        "list": BudgetRequestListSerializer,
        "retrieve": BudgetRequestDetailSerializer,
        "create": BudgetRequestCreateSerializer,
    }
    serializer_class = BudgetRequestDetailSerializer

    # Custom action permissions — CRUD handled by StrictDjangoModelPermissions
    action_permissions = {
        "submit": [permission_required("budget.submit_budgetrequest")],
        "forward": [permission_required("budget.forward_budgetrequest")],
        "approve": [permission_required("budget.approve_budgetrequest")],
        "reject": [permission_required("budget.approve_budgetrequest")],
        "return_for_revision": [permission_required("budget.approve_budgetrequest")],
        "restore": [IsSuperAdmin],
    }

    queryset = BudgetRequest.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "project",
                "current_department",
                "created_by",
                "updated_by",
            )
            .prefetch_related(
                "forwarding_steps__from_department",
                "forwarding_steps__to_department",
            )
            .order_by("-created_at")
        )

    def _check_delete_allowed(self, instance):
        if instance.status != "draft":
            msg = f"Only draft budget requests can be deleted. Current status: {instance.status}."
            raise BusinessRuleViolation(msg)

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.status not in ("draft", "revision_requested"):
            msg = (
                f"Cannot edit a budget request with status '{instance.status}'. "
                "Only draft or revision-requested requests can be edited."
            )
            raise BusinessRuleViolation(msg)
        return super().partial_update(request, *args, **kwargs)

    # ── Submit ────────────────────────────────────────────────────────────────

    @extend_schema(summary="Submit budget request for departmental review")
    @action(detail=True, methods=["post"], url_path="submit")
    @transaction.atomic
    def submit(self, request, *args, **kwargs):
        br = self.get_object()
        if br.status not in ("draft", "revision_requested"):
            msg = f"Cannot submit a request with status '{br.status}'."
            raise BusinessRuleViolation(msg)
        br.submit(submitted_by=request.user)

        # Notify department head
        dept = getattr(request.user, "department", None)
        if dept and hasattr(dept, "head_id") and dept.head_id:
            notify(
                recipient=dept.head,
                verb=(
                    f"Budget request for project '{br.project.title}' has been submitted for review"
                ),
                action_object=br,
                actor=request.user,
            )
        return Response(
            success_response(
                BudgetRequestDetailSerializer(br, context={"request": request}).data,
                message="Budget request submitted.",
            ),
        )

    # ── Forward ───────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Forward budget request to another department",
        request=ForwardSerializer,
    )
    @action(detail=True, methods=["post"], url_path="forward")
    @transaction.atomic
    def forward(self, request, *args, **kwargs):
        br = self.get_object()
        if br.status not in ("submitted", "under_review", "forwarded"):
            msg = f"Cannot forward a request with status '{br.status}'."
            raise BusinessRuleViolation(msg)

        ser = ForwardSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        to_dept = ser.validated_data["to_department"]

        if to_dept == br.current_department:
            msg = "Cannot forward to the same department."
            raise BusinessRuleViolation(msg)

        # Determine next step number
        last_step = br.forwarding_steps.order_by("-step_number").first()
        step_number = (last_step.step_number + 1) if last_step else 1

        user_dept = getattr(request.user, "department", None)
        from_dept = br.current_department or user_dept or br.project.implementing_department

        BudgetForwardingStep.objects.create(
            budget_request=br,
            from_department=from_dept,
            to_department=to_dept,
            action="forwarded",
            acted_by=request.user,
            remarks=ser.validated_data.get("remarks", ""),
            step_number=step_number,
            created_by=request.user,
            updated_by=request.user,
        )
        # step.save() triggers _notify_target_department via model.save()

        br.status = "forwarded"
        br.current_department = to_dept
        br.updated_by = request.user
        br.save(
            update_fields=["status", "current_department", "updated_by", "updated_at"],
        )

        return Response(
            success_response(
                BudgetRequestDetailSerializer(br, context={"request": request}).data,
                message=f"Request forwarded to {to_dept.name_en}.",
            ),
        )

    # ── Approve ───────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Approve budget request — unlocks the project for data entry",
        request=ApproveSerializer,
    )
    @action(detail=True, methods=["post"], url_path="approve")
    @transaction.atomic
    def approve(self, request, *args, **kwargs):
        br = self.get_object()
        if br.status in ("approved", "rejected"):
            msg = f"Request is already {br.status} and cannot be re-approved."
            raise BusinessRuleViolation(msg)

        ser = ApproveSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        br.approve(
            approved_by=request.user,
            approved_amount=ser.validated_data["approved_amount"],
        )

        # Log the approval step
        last_step = br.forwarding_steps.order_by("-step_number").first()
        user_dept = getattr(request.user, "department", None)
        dept = br.current_department or user_dept or br.project.implementing_department
        BudgetForwardingStep.objects.create(
            budget_request=br,
            from_department=dept,
            to_department=dept,
            action="approved",
            acted_by=request.user,
            remarks=ser.validated_data.get("remarks", ""),
            step_number=(last_step.step_number + 1) if last_step else 1,
            created_by=request.user,
            updated_by=request.user,
        )

        # Notify project owner that budget is approved
        if br.project.owner_id:
            notify(
                recipient=br.project.owner,
                verb=f"Budget request for '{br.project.title}' has been approved. "
                f"Approved amount: {ser.validated_data['approved_amount']}",
                action_object=br,
                actor=request.user,
            )

        # Update project status to 'budget_approved'
        ps = ProjectStatus.objects.create(
            project=br.project,
            status="budget_approved",
            changed_by=request.user,
            created_by=request.user,
            updated_by=request.user,
        )
        br.project.current_status = ps
        br.project.save(update_fields=["current_status"])

        return Response(
            success_response(
                BudgetRequestDetailSerializer(br, context={"request": request}).data,
                message="Budget request approved. Project is now active.",
            ),
        )

    # ── Reject ────────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Reject a budget request",
        request=RejectSerializer,
    )
    @action(detail=True, methods=["post"], url_path="reject")
    @transaction.atomic
    def reject(self, request, *args, **kwargs):
        br = self.get_object()
        if br.status in ("approved", "rejected"):
            msg = f"Request is already {br.status}."
            raise BusinessRuleViolation(msg)

        ser = RejectSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        br.reject(rejected_by=request.user, remarks=ser.validated_data["remarks"])

        # Log step
        last_step = br.forwarding_steps.order_by("-step_number").first()
        user_dept = getattr(request.user, "department", None)
        dept = br.current_department or user_dept or br.project.implementing_department
        BudgetForwardingStep.objects.create(
            budget_request=br,
            from_department=dept,
            to_department=dept,
            action="rejected",
            acted_by=request.user,
            remarks=ser.validated_data["remarks"],
            step_number=(last_step.step_number + 1) if last_step else 1,
            created_by=request.user,
            updated_by=request.user,
        )

        # Notify requester
        if br.created_by_id:
            notify(
                recipient=br.created_by,
                verb=f"Your budget request for '{br.project.title}' was rejected. "
                f"Reason: {ser.validated_data['remarks']}",
                action_object=br,
                actor=request.user,
            )
        return Response(
            success_response(
                BudgetRequestDetailSerializer(br, context={"request": request}).data,
                message="Budget request rejected.",
            ),
        )

    # ── Return for revision ───────────────────────────────────────────────────

    @extend_schema(summary="Return for revision (requester must edit and resubmit)")
    @action(detail=True, methods=["post"], url_path="return-revision")
    @transaction.atomic
    def return_for_revision(self, request, *args, **kwargs):
        br = self.get_object()
        if br.status in ("approved", "rejected"):
            msg = "Cannot return an already resolved request."
            raise BusinessRuleViolation(msg)

        remarks = request.data.get("remarks", "")
        br.status = "revision_requested"
        br.updated_by = request.user
        br.save(update_fields=["status", "updated_by", "updated_at"])

        if br.created_by_id:
            notify(
                recipient=br.created_by,
                verb=(
                    f"Budget request for '{br.project.title}' "
                    "was returned for revision. "
                    f"Remarks: {remarks}"
                ),
                action_object=br,
                actor=request.user,
            )
        return Response(success_response(message="Returned for revision."))

    # ── My department queue ───────────────────────────────────────────────────

    @extend_schema(summary="Budget requests currently in my department's queue")
    @action(detail=False, methods=["get"], url_path="my-department")
    def my_department(self, request, *args, **kwargs):
        user_dept = getattr(request.user, "department", None)
        if not user_dept:
            return Response(success_response([]))
        qs = BudgetRequest.objects.filter(
            current_department=user_dept,
            status__in=["submitted", "under_review", "forwarded"],
        ).select_related("project", "current_department")
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                BudgetRequestListSerializer(page, many=True).data,
            )
        return Response(
            success_response(BudgetRequestListSerializer(qs, many=True).data),
        )

    # ── Stats ─────────────────────────────────────────────────────────────────

    @extend_schema(summary="Budget request aggregated stats")
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request, *args, **kwargs):
        qs = BudgetRequest.objects
        by_status = list(qs.values("status").annotate(count=Count("id")))
        totals = qs.aggregate(
            total_requested=Sum("requested_amount"),
            total_approved=Sum("approved_amount"),
        )
        return Response(
            success_response(
                {
                    "by_status": by_status,
                    **totals,
                },
            ),
        )
