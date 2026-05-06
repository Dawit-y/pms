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
│  History / changelog    │  history action (GET /{uuid}/history) │
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

from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import mixins
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .exceptions import ResourceNotFound
from .exceptions import SoftDeletedResourceError
from .models.notifications import Notification
from .pagination import StandardPagination
from .pagination import success_response
from .permissions import ActionPermissionMixin
from .permissions import IsSuperAdmin
from .permissions import StrictDjangoModelPermissions
from .serializers import BulkDeleteSerializer
from .serializers import BulkRestoreSerializer
from .serializers import NotificationSerializer
from .serializers import RestoreSerializer

logger = logging.getLogger(__name__)


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

        # ── Deleted filter ────────────────────────────────────────────────────
        include_deleted = request.query_params.get("include_deleted", "false").lower() == "true"
        if not (include_deleted and (request.user.is_staff or request.user.is_superuser)):
            # Default: hide soft-deleted records.
            # (Requires subclasses to use .all_objects as
            # their base queryset so we can filter here)
            if hasattr(qs.model, "is_deleted"):
                qs = qs.filter(is_deleted=False)

        # ── Row-level security ────────────────────────────────────────────────
        if not self.row_security_enabled:
            return qs
        if request.user.is_superuser or request.user.is_staff:
            return qs

        # Non-admin: filter by ownership OR department membership
        user = request.user
        user_dept = getattr(user, "department_id", None)

        filters = Q(owner=user)
        if user_dept:
            # Also grant access to records belonging to the user's department subtree
            try:
                dept = user.department
                dept_ids = dept.get_descendants(include_self=True).values_list(
                    "id",
                    flat=True,
                )
                filters |= Q(department_id__in=dept_ids)
            except Exception:  # noqa: BLE001
                filters |= Q(department_id=user_dept)

        # Prevents crashes if the model doesn't have owner or department fields.
        meta_fields = {f.name for f in qs.model._meta.get_fields()}  # noqa: SLF001
        if "owner" in meta_fields or "department" in meta_fields:
            qs = qs.filter(filters)

        return qs


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
        summary="Hard-delete a record permanently (superuser only)",
        responses={204: None},
    )
    @action(
        detail=True,
        methods=["delete"],
        url_path="hard-delete",
        permission_classes=[IsSuperAdmin],
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
        summary="Restore a soft-deleted record (staff/admin only)",
        request=RestoreSerializer,
        responses={200: {"description": "Record restored."}},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="restore",
        permission_classes=[IsSuperAdmin],
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
        summary="Bulk restore soft-deleted records (admin only)",
        request=BulkRestoreSerializer,
    )
    @action(
        detail=False,
        methods=["post"],
        url_path="bulk-restore",
        permission_classes=[IsSuperAdmin],
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
