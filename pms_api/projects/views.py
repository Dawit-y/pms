# Standard library imports

# Django imports
from django.db.models import Count
from django.db.models import Prefetch

# Third-party imports
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

# Local application imports
from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.models.notifications import notify
from pms_api.core.pagination import success_response
from pms_api.core.permissions import IsSuperAdmin
from pms_api.core.permissions import permission_required
from pms_api.core.views import BaseModelViewSet
from pms_api.projects.models import Project
from pms_api.projects.models import ProjectStatus

from .serializers import ProjectCreateSerializer
from .serializers import ProjectDetailSerializer
from .serializers import ProjectListSerializer
from .serializers import ProjectStatusCreateSerializer
from .serializers import ProjectStatusSerializer


class ProjectViewSet(BaseModelViewSet):
    """
    Central resource of the system. All child data (employees, payments, etc.)
    hangs off a Project. Editing child data is blocked until budget is approved.
    """

    lookup_field = "uuid"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        "project_type",
        "location",
        "implementing_department",
        "current_status__status",
        "is_active",
    ]
    search_fields = ["code", "title", "description"]
    ordering_fields = ["created_at", "code", "title", "start_date"]
    ordering = ["-created_at"]

    serializer_classes = {
        "list": ProjectListSerializer,
        "retrieve": ProjectDetailSerializer,
        "create": ProjectCreateSerializer,
        "update": ProjectDetailSerializer,
        "partial_update": ProjectDetailSerializer,
    }
    serializer_class = ProjectDetailSerializer

    # Custom action permissions — CRUD handled by StrictDjangoModelPermissions
    action_permissions = {
        "restore": [IsSuperAdmin],
        "update_status": [permission_required("projects.monitor_project")],
        "status_history": [],  # inherits StrictDjangoModelPermissions (view)
        "dashboard": [],  # inherits StrictDjangoModelPermissions (view)
        "stats": [],  # inherits StrictDjangoModelPermissions (view)
        "my_projects": [],  # inherits StrictDjangoModelPermissions (view)
    }

    queryset = Project.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related(
                "project_type",
                "location",
                "implementing_department",
                "current_status",
                "created_by",
                "updated_by",
                "budget_request",
            )
            .prefetch_related(
                Prefetch(
                    "status_history",
                    queryset=ProjectStatus.objects.select_related("changed_by").order_by(
                        "-created_at",
                    ),
                ),
            )
            .order_by("-created_at")
        )

    def _check_delete_allowed(self, instance):
        # Prevent deleting a project with approved budget / active data
        if instance.is_active:
            msg = (
                "Cannot delete an active project. "
                "Deactivate all associated data and close the budget first."
            )
            raise BusinessRuleViolation(msg)

    # ── Status history ────────────────────────────────────────────────────────

    @extend_schema(summary="Full status change history for this project")
    @action(detail=True, methods=["get"], url_path="status-history")
    def status_history(self, request, *args, **kwargs):
        project = self.get_object()
        history = project.status_history.select_related("changed_by").order_by(
            "-created_at",
        )
        return Response(
            success_response(ProjectStatusSerializer(history, many=True).data),
        )

    # ── Update project status (monitoring visit) ──────────────────────────────

    @extend_schema(
        summary="Monitoring team records a new status update",
        request=ProjectStatusCreateSerializer,
    )
    @action(detail=True, methods=["post"], url_path="update-status")
    def update_status(self, request, *args, **kwargs):
        project = self.get_object()
        request.data["project"] = project.pk
        ser = ProjectStatusCreateSerializer(
            data=request.data,
            context={"request": request},
        )
        ser.is_valid(raise_exception=True)
        status_record = ser.save()

        # Notify project owner of status change
        if project.owner_id:
            notify(
                recipient=project.owner,
                verb=(f"Project '{project.title}' status updated to '{status_record.status}'",),
                action_object=project,
                actor=request.user,
            )

        return Response(
            success_response(
                ProjectStatusSerializer(status_record).data,
                message="Project status updated.",
            ),
            status=status.HTTP_201_CREATED,
        )

    # ── Project dashboard ─────────────────────────────────────────────────────

    @extend_schema(summary="Project summary dashboard card")
    @action(detail=True, methods=["get"], url_path="dashboard")
    def dashboard(self, request, *args, **kwargs):
        project = self.get_object()

        # Budget summary
        budget_info = None
        try:
            br = project.budget_request
            budget_info = {
                "status": br.status,
                "requested": str(br.requested_amount),
                "approved": str(br.approved_amount) if br.approved_amount else None,
            }
        except Exception:  # noqa: BLE001, S110
            pass

        # Latest monitoring
        latest_monitoring = None
        try:
            mon = project.monitoringvisit_set.order_by("-created_at").first()
            if mon:
                latest_monitoring = {
                    "visit_date": str(mon.mon_visit_date),
                    "physical_progress": float(mon.mon_physical_progress_pct),
                    "financial_progress": float(mon.mon_financial_progress_pct),
                }
        except Exception:  # noqa: BLE001, S110
            pass

        # Counts
        data = {
            "project": {
                "uuid": str(project.uuid),
                "code": project.code,
                "title": project.title,
                "status": project.current_status.status if project.current_status_id else None,
                "is_active": project.is_active,
            },
            "budget": budget_info,
            "latest_monitoring": latest_monitoring,
            "counts": {
                "employees": getattr(
                    project,
                    "projectemployee_set",
                    project.__class__.objects.none(),
                )
                .model.objects.filter(project=project)
                .count()
                if project.is_active
                else 0,
                "documents": project.__class__.objects.filter(pk=project.pk)
                .values("id")
                .count(),  # placeholder
                "open_issues": 0,  # populated by project_data app
            },
        }
        return Response(success_response(data))

    # ── Portfolio stats ───────────────────────────────────────────────────────

    @extend_schema(summary="Portfolio-level project statistics")
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request, *args, **kwargs):
        qs = self.get_queryset()
        total = qs.count()
        active = qs.filter(is_active=True).count()
        by_status = list(
            qs.values("current_status__status").annotate(count=Count("id")).order_by("-count"),
        )
        by_type = list(
            qs.values("project_type__name_en").annotate(count=Count("id")).order_by("-count"),
        )
        return Response(
            success_response(
                {
                    "total": total,
                    "active": active,
                    "inactive": total - active,
                    "by_status": by_status,
                    "by_type": by_type,
                },
            ),
        )

    # ── My projects ───────────────────────────────────────────────────────────

    @extend_schema(summary="Projects owned by the authenticated user")
    @action(detail=False, methods=["get"], url_path="my-projects")
    def my_projects(self, request, *args, **kwargs):
        qs = self.filter_queryset(
            self.get_queryset().filter(owner=request.user),
        )
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                ProjectListSerializer(page, many=True).data,
            )
        return Response(success_response(ProjectListSerializer(qs, many=True).data))


# ─── Project Status ViewSet ───────────────────────────────────────────────────


class ProjectStatusViewSet(BaseModelViewSet):
    """
    Standalone access to status records.
    Mainly used by the monitoring module.
    """

    lookup_field = "uuid"
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["project", "status"]
    ordering = ["-created_at"]

    serializer_classes = {
        "create": ProjectStatusCreateSerializer,
    }
    serializer_class = ProjectStatusSerializer

    # Custom action permissions — CRUD handled by StrictDjangoModelPermissions
    action_permissions = {
        "restore": [IsSuperAdmin],
    }

    queryset = ProjectStatus.all_objects.all()

    def get_queryset(self):
        return (
            super().get_queryset().select_related("project", "changed_by").order_by("-created_at")
        )
