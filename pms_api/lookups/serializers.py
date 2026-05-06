from rest_framework import serializers

from pms_api.core.serializers import BaseModelSerializer
from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.lookups.models import Lookup
from pms_api.lookups.models import LookupType


class LookupTypeSerializer(BaseModelSerializer):
    lookup_count = serializers.SerializerMethodField()

    class Meta:
        model = LookupType
        fields = [
            "id",
            "uuid",
            "code",
            "name_en",
            "name_am",
            "name_or",
            "is_active",
            "lookup_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_lookup_count(self, obj) -> int:
        return obj.lookups.filter(is_active=True).count()


class LookupSerializer(BaseModelSerializer):
    lookup_type_uuid = serializers.UUIDField(source="lookup_type.uuid", read_only=True)
    lookup_type_code = serializers.CharField(source="lookup_type.code", read_only=True)
    lookup_type_name = serializers.CharField(
        source="lookup_type.name_en",
        read_only=True,
    )

    class Meta:
        model = Lookup
        fields = [
            "id",
            "uuid",
            "lookup_type_uuid",
            "lookup_type",
            "lookup_type_code",
            "lookup_type_name",
            "code",
            "name_en",
            "name_am",
            "name_or",
            "sort_order",
            "is_active",
            "extra_data",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def validate(self, data):
        lookup_type = data.get("lookup_type") or getattr(
            self.instance,
            "lookup_type",
            None,
        )
        code = data.get("code") or getattr(self.instance, "code", None)
        if lookup_type and code:
            qs = Lookup.objects.filter(lookup_type=lookup_type, code=code)
            if self.instance:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                msg = f"A lookup with code '{code}' already exists in this type."
                raise serializers.ValidationError({"code": msg})
        return data


# ─── Hierarchical: Location ───────────────────────────────────────────────────


class LocationTreeSerializer(serializers.Serializer):
    """Recursive serializer for the full location tree."""

    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    code = serializers.CharField()
    name_en = serializers.CharField()
    name_am = serializers.CharField()
    name_or = serializers.CharField()
    location_type = serializers.CharField()
    children = serializers.SerializerMethodField()

    def get_children(self, obj) -> list:
        if obj.get_children().exists():
            return LocationTreeSerializer(obj.get_children(), many=True).data
        return []


class LocationSerializer(BaseModelSerializer):
    parent_name = serializers.CharField(
        source="parent.name_en",
        read_only=True,
        default=None,
    )
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Location
        fields = [
            "id",
            "uuid",
            "code",
            "name_en",
            "name_am",
            "name_or",
            "location_type",
            "parent",
            "parent_name",
            "children_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_children_count(self, obj) -> int:
        return obj.get_children().count()


# ─── Hierarchical: Department ─────────────────────────────────────────────────


class DepartmentTreeSerializer(serializers.Serializer):
    """Recursive tree serializer for departments."""

    id = serializers.IntegerField()
    uuid = serializers.UUIDField()
    code = serializers.CharField()
    name_en = serializers.CharField()
    name_am = serializers.CharField()
    name_or = serializers.CharField()
    children = serializers.SerializerMethodField()

    def get_children(self, obj) -> list:
        if obj.get_children().exists():
            return DepartmentTreeSerializer(obj.get_children(), many=True).data
        return []


class DepartmentSerializer(BaseModelSerializer):
    parent_name = serializers.CharField(
        source="parent.name_en",
        read_only=True,
        default=None,
    )
    children_count = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = [
            "id",
            "uuid",
            "code",
            "name_en",
            "name_am",
            "name_or",
            "parent",
            "parent_name",
            "children_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["uuid", "created_at", "updated_at"]

    def get_children_count(self, obj) -> int:
        return obj.get_children().count()
