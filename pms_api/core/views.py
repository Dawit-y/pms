"""
BaseModelViewSet — the single source of truth for all CRUD behaviour.

Every feature is implemented here ONCE so app-level ViewSets get it for free:

┌─────────────────────────────────────────────────────────────────┐
│  Feature                │  How it works                         │
├─────────────────────────────────────────────────────────────────┤
│  Soft delete            │  override destroy() → .delete(user)   │
│  Hard delete            │  hard_destroy action (superuser only) │
│  Restore deleted        │  restore action (staff only)          │
│  Audit trail inject     │  get_serializer_context() adds user   │
│  Signals                │  post_save emitted by model layer     │
│  Response envelope      │  success_response() wraps all data    │
│  Pagination             │  StandardPagination on all lists      │
│  Filtering/search/sort  │  DjangoFilterBackend + SearchFilter   │
│  Row-level security     │  get_queryset() enforces owner/dept   │
│  Deleted record access  │  ?include_deleted=true (admin only)   │
│  Bulk soft-delete       │  POST /bulk-delete/                   │
│  Bulk restore           │  POST /bulk-restore/ (admin only)     │
│  Schema docs            │  drf-spectacular annotations          │
└─────────────────────────────────────────────────────────────────┘
"""

import logging
from functools import cache

import django_filters
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from pms_api.lookups.models import Department

from .exceptions import ResourceNotFound
from .exceptions import SoftDeletedResourceError
from .models.access_log import AccessLog
from .models.notifications import Notification
from .pagination import StandardPagination
from .pagination import success_response
from .permissions import ActionPermissionMixin
from .permissions import StrictDjangoModelPermissions
from .permissions import permission_required
from .serializers import BulkDeleteSerializer
from .serializers import BulkRestoreSerializer
from .serializers import NotificationSerializer
from .serializers import RestoreSerializer

logger = logging.getLogger(__name__)


@cache
def _model_has_security_fields(model):
    """
    Cached check: does this model have an `owner` or `department` column?
    Result is constant for the lifetime of the process, so the per-request
    set comprehension over `_meta.get_fields()` was pure waste.
    """
    names = {f.name for f in model._meta.get_fields()}  # noqa: SLF001
    return ("owner" in names) or ("department" in names)


# ─── QuerySet mixin: row-level security + deleted filtering ──────────────────


class SecureQuerySetMixin:
    """
    Plugs into get_queryset() to:
    1. Hide soft-deleted records unless admin passes ?include_deleted=true
    2. Enforce row-level security (owner / department) when not admin
    """

    row_security_enabled: bool = True  # set False on lookup-type endpoints

    def get_queryset(self):
        qs = super().get_queryset()
        request = self.request
        user = request.user

        # ── Deleted filter ────────────────────────────────────────────────────
        include_deleted = request.query_params.get("include_deleted", "false").lower() == "true"
        can_view_deleted = user.is_authenticated and user.has_perm("accounts.view_deleted_records")
        if not (include_deleted and can_view_deleted):
            # Default: hide soft-deleted records.
            # (Requires subclasses to use .all_objects as
            # their base queryset so we can filter here)
            if hasattr(qs.model, "is_deleted"):
                qs = qs.filter(is_deleted=False)

        # ── Row-level security ────────────────────────────────────────────────
        if not self.row_security_enabled:
            return qs
        if user.is_authenticated and user.has_perm("accounts.bypass_row_security"):
            return qs
        if not _model_has_security_fields(qs.model):
            return qs

        # Non-admin: filter by ownership OR department subtree membership.
        filters = Q(owner=user)
        user_dept_id = getattr(user, "department_id", None)
        if user_dept_id:
            # Build a subquery for descendant department ids instead of pulling
            # the user's department row first. MPTT's tree_id / lft / rght
            # columns let us scope to the subtree in one SQL statement.

            dept_row = Department.objects.filter(pk=user_dept_id).values(
                "tree_id",
                "lft",
                "rght",
            )
            descendants = Department.objects.filter(
                tree_id=dept_row.values("tree_id")[:1],
                lft__gte=dept_row.values("lft")[:1],
                rght__lte=dept_row.values("rght")[:1],
            ).values("id")
            filters |= Q(department_id__in=descendants)

        return qs.filter(filters)


# ─── Base ViewSet ─────────────────────────────────────────────────────────────


class BaseModelViewSet(
    ActionPermissionMixin,
    SecureQuerySetMixin,
    viewsets.ModelViewSet,
):
    """
    Inherit from this for all resource ViewSets.

    Minimal setup:
        class ProjectViewSet(BaseModelViewSet):
            queryset        = Project.objects.select_related('project_type', 'location')
            serializer_class = ProjectSerializer
            filterset_fields = ['code', 'current_status']
            search_fields    = ['title', 'code']
            ordering_fields  = ['created_at', 'title']
    """

    pagination_class = StandardPagination
    permission_classes = [StrictDjangoModelPermissions]
    lookup_field = "uuid"  # all resources addressed by UUID in URLs

    # Override in subclasses for different serializers per action
    serializer_classes: dict = {}

    # ── Serializer dispatch ───────────────────────────────────────────────────

    def get_serializer_class(self):
        return self.serializer_classes.get(self.action, self.serializer_class)

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ctx["request"] = self.request  # audit mixin reads this
        return ctx

    # ── Object lookup (UUID-based, deleted-aware) ─────────────────────────────

    def get_object(self):
        """
        Overridden to:
        - Use uuid as lookup field
        - Return 410 GONE (not 404) for soft-deleted objects when admin requests them
        """
        queryset = self.get_queryset()
        uuid = self.kwargs.get(self.lookup_field)

        try:
            obj = queryset.get(uuid=uuid)
        except queryset.model.DoesNotExist:
            # Check if it exists but is soft-deleted
            try:
                deleted_obj = queryset.model.all_objects.get(uuid=uuid, is_deleted=True)
                msg = f"This resource (uuid={uuid}) was deleted on {deleted_obj.deleted_at}. "
                raise SoftDeletedResourceError(msg)
            except queryset.model.DoesNotExist as err:
                msg = f"{queryset.model.__name__} with uuid={uuid} not found."
                raise ResourceNotFound(msg) from err

        self.check_object_permissions(self.request, obj)
        return obj

    # ── Standard CRUD overrides ───────────────────────────────────────────────

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(success_response(serializer.data))

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(success_response(serializer.data))

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        logger.info(
            "CREATED %s uuid=%s by user=%s",
            instance.__class__.__name__,
            instance.uuid,
            request.user.id,
        )
        return Response(
            success_response(
                self.get_serializer(instance).data,
                message=f"{instance.__class__.__name__} created successfully.",
            ),
            status=status.HTTP_201_CREATED,
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        instance = serializer.save()
        logger.info(
            "UPDATED %s uuid=%s by user=%s",
            instance.__class__.__name__,
            instance.uuid,
            request.user.id,
        )
        return Response(
            success_response(
                self.get_serializer(instance).data,
                message=f"{instance.__class__.__name__} updated successfully.",
            ),
        )

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    # ── Soft delete (replaces ModelViewSet.destroy) ───────────────────────────

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._check_delete_allowed(instance)
        instance.delete(deleted_by=request.user)
        logger.info(
            "SOFT-DELETED %s uuid=%s by user=%s",
            instance.__class__.__name__,
            instance.uuid,
            request.user.id,
        )
        return Response(
            success_response(
                message=f"{instance.__class__.__name__} deleted successfully.",
            ),
            status=status.HTTP_200_OK,
        )

    def _check_delete_allowed(self, instance):
        """Override in subclasses to add domain-specific delete guards."""

    # ── Hard delete (superuser only) ──────────────────────────────────────────

    @extend_schema(
        summary="Hard-delete a record permanently",
        description=(
            "Requires the `accounts.hard_delete_records` permission. "
            "Bypasses soft-delete and removes the row from the database."
        ),
        responses={204: None},
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path="hard-delete",
        permission_classes=[permission_required("accounts.hard_delete_records")],
    )
    @transaction.atomic
    def hard_destroy(self, request, *args, **kwargs):
        # Bypass SoftDeleteManager to find even deleted records
        model = self.get_queryset().model
        try:
            instance = model.all_objects.get(uuid=self.kwargs[self.lookup_field])
        except model.DoesNotExist as err:
            raise ResourceNotFound from err
        instance.hard_delete()
        logger.warning(
            "HARD-DELETED %s uuid=%s by superuser=%s",
            model.__name__,
            self.kwargs[self.lookup_field],
            request.user.id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)

    # ── Restore ───────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Restore a soft-deleted record",
        description="Requires the `accounts.restore_records` permission.",
        request=RestoreSerializer,
        responses={200: {"description": "Record restored."}},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="restore",
        permission_classes=[permission_required("accounts.restore_records")],
    )
    @transaction.atomic
    def restore(self, request, *args, **kwargs):
        model = self.get_queryset().model
        try:
            instance = model.all_objects.get(
                uuid=self.kwargs[self.lookup_field],
                is_deleted=True,
            )
        except model.DoesNotExist as err:
            msg = "No deleted record found with that UUID."
            raise ResourceNotFound(msg) from err

        restore_ser = RestoreSerializer(data=request.data)
        restore_ser.is_valid(raise_exception=True)
        instance.restore()
        instance.updated_by = request.user
        instance.save(update_fields=["updated_by", "updated_at"])

        logger.info(
            "RESTORED %s uuid=%s by user=%s reason=%s",
            model.__name__,
            instance.uuid,
            request.user.id,
            restore_ser.validated_data.get("restore_reason", ""),
        )
        serializer = self.get_serializer(instance)
        return Response(
            success_response(serializer.data, message="Record restored successfully."),
        )

    # ── Bulk soft-delete ──────────────────────────────────────────────────────

    @extend_schema(
        summary="Bulk soft-delete multiple records by UUID",
        request=BulkDeleteSerializer,
    )
    @action(detail=False, methods=["post"], url_path="bulk-delete")
    @transaction.atomic
    def bulk_delete(self, request, *args, **kwargs):
        ser = BulkDeleteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        uuids = ser.validated_data["uuids"]
        model = self.get_queryset().model
        qs = model.objects.filter(uuid__in=uuids)
        count = qs.count()
        for obj in qs:
            obj.delete(deleted_by=request.user)
        return Response(
            success_response(message=f"{count} records deleted."),
        )

    # ── Bulk restore ──────────────────────────────────────────────────────────

    @extend_schema(
        summary="Bulk restore soft-deleted records",
        description="Requires the `accounts.restore_records` permission.",
        request=BulkRestoreSerializer,
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk-restore",
        permission_classes=[permission_required("accounts.restore_records")],
    )
    @transaction.atomic
    def bulk_restore(self, request, *args, **kwargs):
        ser = BulkRestoreSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        uuids = ser.validated_data["uuids"]
        model = self.get_queryset().model
        qs = model.all_objects.filter(uuid__in=uuids, is_deleted=True)
        count = qs.count()
        for obj in qs:
            obj.restore()
        return Response(success_response(message=f"{count} records restored."))


# ─── Read-only base (for lookup endpoints etc.) ───────────────────────────────


class BaseReadOnlyViewSet(
    SecureQuerySetMixin,
    viewsets.ReadOnlyModelViewSet,
):
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"
    row_security_enabled = False

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response(success_response(self.get_serializer(instance).data))

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                self.get_serializer(page, many=True).data,
            )
        return Response(success_response(self.get_serializer(qs, many=True).data))


# ─── Notification ViewSet ─────────────────────────────────────────────────────


class NotificationViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """
    GET  /notifications/              → user's notifications (unread first)
    GET  /notifications/{uuid}/       → single notification
    POST /notifications/{uuid}/read/  → mark as read
    POST /notifications/read-all/     → mark all as read
    GET  /notifications/unread-count/ → fast unread count
    """

    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated]
    lookup_field = "uuid"

    filterset_fields = ["is_read"]
    search_fields = ["verb"]
    ordering_fields = ["created_at"]

    def get_queryset(self):
        return (
            Notification.objects.filter(recipient=self.request.user)
            .select_related("content_type", "actor_content_type")
            .order_by("is_read", "-created_at")
        )

    def get_serializer_class(self):
        return NotificationSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(
                NotificationSerializer(page, many=True).data,
            )
        return Response(success_response(NotificationSerializer(qs, many=True).data))

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, *args, **kwargs):
        note = get_object_or_404(
            self.get_queryset(),
            uuid=self.kwargs["uuid"],
        )
        note.is_read = True
        note.save(update_fields=["is_read"])
        return Response(success_response(message="Marked as read."))

    @action(detail=False, methods=["post"], url_path="read-all")
    def mark_all_read(self, request, *args, **kwargs):
        count = self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response(
            success_response(message=f"{count} notifications marked as read."),
        )

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request, *args, **kwargs):
        count = self.get_queryset().filter(is_read=False).count()
        return Response(success_response({"unread_count": count}))


# ─── AccessLog ViewSet (admin audit trail) ────────────────────────────────────


class AccessLogFilter(django_filters.FilterSet):
    """
    Filters for the AccessLog list endpoint. Date range filters use
    ISO-8601 timestamps (e.g. ?from=2026-05-01T00:00:00Z).
    """

    user = django_filters.NumberFilter(field_name="user_id")
    user_email = django_filters.CharFilter(
        field_name="user__email",
        lookup_expr="iexact",
    )
    endpoint = django_filters.CharFilter(field_name="endpoint", lookup_expr="icontains")
    method = django_filters.CharFilter(field_name="method", lookup_expr="iexact")
    status_min = django_filters.NumberFilter(
        field_name="response_status",
        lookup_expr="gte",
    )
    status_max = django_filters.NumberFilter(
        field_name="response_status",
        lookup_expr="lte",
    )
    ip_address = django_filters.CharFilter(field_name="ip_address", lookup_expr="exact")
    # `from` is a Python keyword — declare as `from_` and remap the incoming
    # query param in __init__ so the URL stays ?from=… for the caller.
    from_ = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    to = django_filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")

    class Meta:
        model = AccessLog
        fields = [
            "user",
            "user_email",
            "endpoint",
            "method",
            "status_min",
            "status_max",
            "ip_address",
            "from_",
            "to",
        ]

    def __init__(self, data=None, *args, **kwargs):
        # Map the `from` query parameter onto the `from_` filter so callers
        # can write `?from=…&to=…` without bumping into the Python keyword.
        if data is not None and "from" in data and "from_" not in data:
            data = data.copy()
            data["from_"] = data["from"]
        super().__init__(data, *args, **kwargs)


class AccessLogViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    Admin-only audit trail of authenticated POST/PUT/PATCH/DELETE requests.

    GET /access-logs/                 → paginated list
    GET /access-logs/{id}/            → single entry
    GET /access-logs/stats/           → aggregate counts grouped by method/status

    Common filters (all optional):
        ?user=<id>                    by user pk
        ?user_email=<email>           by user email (case-insensitive exact)
        ?method=POST                  by HTTP method
        ?endpoint=projects            substring match against the URL path
        ?status_min=400&status_max=499  only client-error responses
        ?ip_address=1.2.3.4           by source IP
        ?from=2026-05-01T00:00:00Z&to=2026-05-02T00:00:00Z   time window
        ?search=...                   full-text against endpoint / user_agent / email
        ?ordering=-duration_ms        sort (default: -timestamp)
    """

    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated, StrictDjangoModelPermissions]
    lookup_field = "pk"
    queryset = AccessLog.objects.none()  # used by StrictDjangoModelPermissions to resolve the model
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class = AccessLogFilter
    search_fields = ["endpoint", "user_agent", "user__email"]
    ordering_fields = ["timestamp", "duration_ms", "response_status"]
    ordering = ["-timestamp"]

    def get_queryset(self):
        return AccessLog.objects.select_related("user").order_by("-timestamp")

    def get_serializer_class(self):
        # Import here to avoid pulling accounts.serializers at module load time.
        from pms_api.accounts.serializers import AccessLogSerializer  # noqa: PLC0415

        return AccessLogSerializer

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        ser_cls = self.get_serializer_class()
        if page is not None:
            return self.get_paginated_response(ser_cls(page, many=True).data)
        return Response(success_response(ser_cls(qs, many=True).data))

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        ser_cls = self.get_serializer_class()
        return Response(success_response(ser_cls(instance).data))

    @extend_schema(summary="Aggregate stats over the current filter")
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request, *args, **kwargs):
        from django.db.models import Count  # noqa: PLC0415

        qs = self.filter_queryset(self.get_queryset())
        total = qs.count()
        by_method = list(qs.values("method").annotate(count=Count("id")).order_by("-count"))
        by_status = list(
            qs.values("response_status").annotate(count=Count("id")).order_by("-count"),
        )
        top_endpoints = list(
            qs.values("endpoint").annotate(count=Count("id")).order_by("-count")[:20],
        )
        top_users = list(
            qs.exclude(user__isnull=True)
            .values("user_id", "user__email")
            .annotate(count=Count("id"))
            .order_by("-count")[:20],
        )
        return Response(
            success_response(
                {
                    "total": total,
                    "by_method": by_method,
                    "by_status": by_status,
                    "top_endpoints": top_endpoints,
                    "top_users": top_users,
                },
            ),
        )
