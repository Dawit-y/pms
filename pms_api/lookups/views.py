from django.contrib.auth import get_user_model
from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.exceptions import ResourceNotFound
from pms_api.core.pagination import success_response
from pms_api.core.permissions import IsStaffOrReadOnly
from pms_api.core.permissions import IsSuperAdmin
from pms_api.core.views import BaseModelViewSet
from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.lookups.models import Lookup
from pms_api.lookups.models import LookupType

from .serializers import DepartmentSerializer
from .serializers import DepartmentTreeSerializer
from .serializers import LocationSerializer
from .serializers import LocationTreeSerializer
from .serializers import LookupSerializer
from .serializers import LookupTypeSerializer

User = get_user_model()


# ─── LookupType ViewSet ───────────────────────────────────────────────────────


class LookupTypeViewSet(BaseModelViewSet):
    """
    Manages the categories of lookup values (e.g. project_type, document_type).
    Only admins can create/edit; all authenticated users can read.
    """

    row_security_enabled = False
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name_en", "name_am", "name_or"]
    ordering_fields = ["code", "name_en", "created_at"]
    ordering = ["code"]
    serializer_class = LookupTypeSerializer

    action_permissions = {
        "create": [IsStaffOrReadOnly],
        "update": [IsStaffOrReadOnly],
        "partial_update": [IsStaffOrReadOnly],
        "destroy": [IsStaffOrReadOnly],
        "restore": [IsSuperAdmin],
    }

    queryset = LookupType.all_objects.all()

    def get_queryset(self):
        return super().get_queryset().prefetch_related("lookups").order_by("code")

    def _check_delete_allowed(self, instance):
        if instance.lookups.filter(is_active=True).exists():
            msg = (
                f"Cannot delete LookupType '{instance.code}' — it has active values. "
                "Deactivate or delete all values first."
            )
            raise BusinessRuleViolation(msg)

    # ── All values for this type ──────────────────────────────────────────────

    @extend_schema(summary="List all lookup values for this type")
    @action(detail=True, methods=["get"], url_path="values")
    def values(self, request, *args, **kwargs):
        lt = self.get_object()
        qs = Lookup.objects.filter(lookup_type=lt).order_by("sort_order", "name_en")
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(LookupSerializer(page, many=True).data)
        return Response(success_response(LookupSerializer(qs, many=True).data))

    # ── Bulk create values ────────────────────────────────────────────────────

    @extend_schema(
        summary="Bulk-create multiple lookup values for this type",
        request=LookupSerializer(many=True),
    )
    @action(detail=True, methods=["post"], url_path="bulk-values")
    @transaction.atomic
    def bulk_values(self, request, *args, **kwargs):
        lt = self.get_object()
        items = request.data if isinstance(request.data, list) else []
        if not items:
            msg = "Provide a list of lookup values."
            raise BusinessRuleViolation(msg)
        created = []
        for item in items:
            item["lookup_type"] = lt.pk
            ser = LookupSerializer(data=item, context={"request": request})
            ser.is_valid(raise_exception=True)
            created.append(ser.save())
        return Response(
            success_response(
                LookupSerializer(created, many=True).data,
                message=f"{len(created)} values created.",
            ),
            status=status.HTTP_201_CREATED,
        )


# ─── Lookup (value) ViewSet ───────────────────────────────────────────────────


class LookupViewSet(BaseModelViewSet):
    """
    Individual lookup values. Filter by ?lookup_type=project_type to get
    values for a specific dropdown.
    """

    row_security_enabled = False
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["lookup_type", "lookup_type__code", "is_active"]
    search_fields = ["code", "name_en", "name_am", "name_or"]
    ordering_fields = ["sort_order", "name_en", "created_at"]
    ordering = ["sort_order", "name_en"]
    serializer_class = LookupSerializer

    action_permissions = {
        "create": [IsStaffOrReadOnly],
        "update": [IsStaffOrReadOnly],
        "partial_update": [IsStaffOrReadOnly],
        "destroy": [IsStaffOrReadOnly],
        "restore": [IsSuperAdmin],
    }

    queryset = Lookup.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("lookup_type")
            .order_by("sort_order", "name_en")
        )

    # ── Reorder values ────────────────────────────────────────────────────────

    @extend_schema(
        summary="Reorder lookup values",
        request={
            "application/json": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "uuid": {"type": "string"},
                        "sort_order": {"type": "integer"},
                    },
                },
            },
        },
    )
    @action(detail=False, methods=["post"], url_path="reorder")
    @transaction.atomic
    def reorder(self, request, *args, **kwargs):
        items = request.data if isinstance(request.data, list) else []
        for item in items:
            Lookup.objects.filter(uuid=item["uuid"]).update(
                sort_order=item["sort_order"],
            )
        return Response(success_response(message="Order updated."))


# ─── Location ViewSet ─────────────────────────────────────────────────────────


class LocationViewSet(BaseModelViewSet):
    """
    Hierarchical location management.
    MPTT powers the tree queries and ancestor lookups.
    """

    row_security_enabled = False
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["location_type", "parent"]
    search_fields = ["name_en", "name_am", "name_or", "code"]
    ordering = ["tree_id", "lft"]
    serializer_class = LocationSerializer

    action_permissions = {
        "create": [IsStaffOrReadOnly],
        "update": [IsStaffOrReadOnly],
        "partial_update": [IsStaffOrReadOnly],
        "destroy": [IsStaffOrReadOnly],
        "restore": [IsSuperAdmin],
    }

    queryset = Location.all_objects.all()

    def get_queryset(self):
        return (
            super().get_queryset().select_related("parent").order_by("tree_id", "lft")
        )

    def _check_delete_allowed(self, instance):
        if instance.get_children().exists():
            msg = (
                "Cannot delete a location that has child locations. "
                "Delete or reassign children first."
            )
            raise BusinessRuleViolation(msg)
        if instance.projects.exists():
            msg = "Cannot delete a location that is referenced by projects."
            raise BusinessRuleViolation(msg)

    # ── Full tree ─────────────────────────────────────────────────────────────

    @extend_schema(summary="Return the full location tree (roots + nested children)")
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        roots = self.get_queryset().filter(parent__isnull=True).order_by("name_en")
        return Response(success_response(LocationTreeSerializer(roots, many=True).data))

    # ── Direct children ───────────────────────────────────────────────────────

    @extend_schema(summary="Direct children of this location")
    @action(detail=True, methods=["get"], url_path="children")
    def children(self, request, *args, **kwargs):
        loc = self.get_object()
        children = loc.get_children().order_by("name_en")
        return Response(success_response(LocationSerializer(children, many=True).data))

    # ── Move node ─────────────────────────────────────────────────────────────

    @extend_schema(
        summary="Move a location node to a new parent",
        request={
            "application/json": {
                "type": "object",
                "properties": {"parent_uuid": {"type": "string"}},
            },
        },
    )
    @action(detail=True, methods=["post"], url_path="move")
    @transaction.atomic
    def move(self, request, *args, **kwargs):
        loc = self.get_object()
        parent_uuid = request.data.get("parent_uuid")
        if parent_uuid:
            try:
                new_parent = Location.objects.get(uuid=parent_uuid)
            except Location.DoesNotExist as err:
                msg = "Parent location not found."
                raise ResourceNotFound(msg) from err
            if new_parent == loc or new_parent.is_descendant_of(loc):
                msg = "Cannot move a location inside its own subtree."
                raise BusinessRuleViolation(msg)
            loc.parent = new_parent
        else:
            loc.parent = None
        loc.save()
        return Response(
            success_response(LocationSerializer(loc).data, message="Location moved."),
        )


# ─── Department ViewSet ───────────────────────────────────────────────────────


class DepartmentViewSet(BaseModelViewSet):
    """
    Hierarchical department management.
    Depth is unlimited — IT admin builds the tree freely.
    """

    row_security_enabled = False
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ["parent"]
    search_fields = ["name_en", "name_am", "name_or", "code"]
    ordering = ["tree_id", "lft"]
    serializer_class = DepartmentSerializer

    action_permissions = {
        "create": [IsStaffOrReadOnly],
        "update": [IsStaffOrReadOnly],
        "partial_update": [IsStaffOrReadOnly],
        "destroy": [IsStaffOrReadOnly],
        "restore": [IsSuperAdmin],
    }

    queryset = Department.all_objects.all()

    def get_queryset(self):
        return (
            super().get_queryset().select_related("parent").order_by("tree_id", "lft")
        )

    def _check_delete_allowed(self, instance):
        if instance.get_children().exists():
            msg = "Cannot delete a department that has sub-departments."
            raise BusinessRuleViolation(msg)

    # ── Full tree ─────────────────────────────────────────────────────────────

    @extend_schema(summary="Full department hierarchy tree")
    @action(detail=False, methods=["get"], url_path="tree")
    def tree(self, request, *args, **kwargs):
        roots = self.get_queryset().filter(parent__isnull=True).order_by("name_en")
        return Response(
            success_response(DepartmentTreeSerializer(roots, many=True).data),
        )

    # ── Children ──────────────────────────────────────────────────────────────

    @extend_schema(summary="Direct sub-departments")
    @action(detail=True, methods=["get"], url_path="children")
    def children(self, request, *args, **kwargs):
        dept = self.get_object()
        children = dept.get_children().order_by("name_en")
        return Response(
            success_response(DepartmentSerializer(children, many=True).data),
        )

    # ── Move department ───────────────────────────────────────────────────────

    @extend_schema(
        summary="Move a department to a new parent",
        request={
            "application/json": {
                "type": "object",
                "properties": {"parent_uuid": {"type": "string"}},
            },
        },
    )
    @action(detail=True, methods=["post"], url_path="move")
    @transaction.atomic
    def move(self, request, *args, **kwargs):
        dept = self.get_object()
        parent_uuid = request.data.get("parent_uuid")
        if parent_uuid:
            try:
                new_parent = Department.objects.get(uuid=parent_uuid)
            except Department.DoesNotExist as err:
                msg = "Parent department not found."
                raise ResourceNotFound(msg) from err
            if new_parent == dept or new_parent.is_descendant_of(dept):
                msg = "Cannot move a department inside its own subtree."
                raise BusinessRuleViolation(msg)
            dept.parent = new_parent
        else:
            dept.parent = None
        dept.save()
        return Response(
            success_response(
                DepartmentSerializer(dept).data,
                message="Department moved.",
            ),
        )
