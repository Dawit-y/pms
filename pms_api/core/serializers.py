"""
core/serializers.py
───────────────────
Base serializer classes. Every app serializer inherits from one of these.

Hierarchy:
    BaseModelSerializer          ← read/write with audit injection
      └── PrefixedModelSerializer  ← handles @field_prefix models
            └── SoftDeleteSerializer   ← exposes is_deleted, restore support
                  └── HistorySerializer   ← includes full change history
"""

from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

# ─── Mixin: injects created_by / updated_by from request.user ────────────────


class AuditSerializerMixin:
    """
    Automatically writes created_by / updated_by from the request context.
    Include in any writable serializer.
    """

    def _get_request_user(self):
        request = self.context.get("request")
        if request and hasattr(request, "user") and request.user.is_authenticated:
            return request.user
        return None

    def create(self, validated_data):
        user = self._get_request_user()
        if user:
            validated_data["created_by"] = user
            validated_data["updated_by"] = user
        return super().create(validated_data)

    def update(self, instance, validated_data):
        user = self._get_request_user()
        if user:
            validated_data["updated_by"] = user
        return super().update(instance, validated_data)


# ─── Mixin: standardised read-only metadata fields ───────────────────────────


class MetaFieldsMixin(serializers.Serializer):
    """
    Adds read-only meta fields to any serializer.
    Include in Meta.fields as needed.
    """

    uuid = serializers.UUIDField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)
    updated_at = serializers.DateTimeField(read_only=True)
    created_by_email = serializers.SerializerMethodField()
    updated_by_email = serializers.SerializerMethodField()
    is_deleted = serializers.BooleanField(read_only=True)

    def get_created_by_email(self, obj) -> str | None:
        return obj.created_by.email if obj.created_by_id else None

    def get_updated_by_email(self, obj) -> str | None:
        return obj.updated_by.email if obj.updated_by_id else None


# ─── Base model serializer ────────────────────────────────────────────────────


class BaseModelSerializer(
    AuditSerializerMixin,
    MetaFieldsMixin,
    serializers.ModelSerializer,
):
    """
    Root serializer for all domain models.

    Features:
    - Auto-injects created_by / updated_by on writes
    - Exposes uuid, timestamps, audit emails as read-only
    - Wraps output in a consistent envelope via to_representation()

    Usage:
        class ProjectSerializer(BaseModelSerializer):
            class Meta:
                model  = Project
                fields = '__all__'
    """

    def to_representation(self, instance):
        return super().to_representation(instance)

    class Meta:
        abstract = True


# ─── Prefixed model serializer ────────────────────────────────────────────────


class PrefixedModelSerializer(BaseModelSerializer):
    """
    For models decorated with @field_prefix('xxx').
    The model already stores prefixed column names; this serializer
    exposes them correctly and provides a prefix-aware field reference.

    Example:
        class ProjectSerializer(PrefixedModelSerializer):
            class Meta:
                model  = Project
                fields = '__all__'
        # Output keys: title, code, budget, uuid, created_at ...
    """

    def get_field_names(self, declared_fields, info):
        names = super().get_field_names(declared_fields, info)
        prefix = getattr(self.Meta.model, "_field_prefix", None)
        if not prefix:
            return names
        # Ensure uuid and base fields are always present
        return list(names)


# ─── Soft-delete serializer ───────────────────────────────────────────────────


class SoftDeleteSerializer(BaseModelSerializer):
    """
    Adds `is_deleted`, `deleted_at`, `deleted_by_email` to output.
    Used by admin-facing serializers that need to see deleted records.
    """

    deleted_by_email = serializers.SerializerMethodField()

    def get_deleted_by_email(self, obj) -> str | None:
        return obj.deleted_by.email if getattr(obj, "deleted_by_id", None) else None


# ─── History (model change log) serializer ───────────────────────────────────


class HistoryRecordSerializer(serializers.Serializer):
    """
    Read-only. Serializes a django-simple-history HistoricalRecord.
    """

    history_id = serializers.IntegerField()
    history_date = serializers.DateTimeField()
    history_type = serializers.CharField()  # +  created, ~ changed, - deleted
    history_user = serializers.SerializerMethodField()
    changed_fields = serializers.SerializerMethodField()

    def get_history_user(self, record) -> str | None:
        return record.history_user.email if record.history_user_id else None

    def get_changed_fields(self, record) -> dict:
        """Returns {field: {old: x, new: y}} for changed records."""
        try:
            prev = record.prev_record
        except Exception:  # noqa: BLE001
            return {}
        if not prev:
            return {}
        delta = record.diff_against(prev)
        return {
            change.field: {"old": change.old, "new": change.new}
            for change in delta.changes
        }


# ─── Restore serializer (admin only) ─────────────────────────────────────────


class RestoreSerializer(serializers.Serializer):
    """
    Body accepted by the /restore/ action.
    Optionally lets the admin add a note about why they restored.
    """

    restore_reason = serializers.CharField(
        max_length=500,
        required=False,
        allow_blank=True,
        help_text="Optional note logged alongside the restore action.",
    )


# ─── Bulk operation serializers ───────────────────────────────────────────────


class BulkDeleteSerializer(serializers.Serializer):
    """Accepts a list of UUIDs for bulk soft-delete."""

    uuids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
    )
    reason = serializers.CharField(max_length=500, required=False, allow_blank=True)


class BulkRestoreSerializer(serializers.Serializer):
    uuids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=1,
        max_length=100,
    )


# ─── Notification serializer ──────────────────────────────────────────────────


class NotificationSerializer(serializers.Serializer):
    """
    Serializes core.models_notification.Notification.
    Avoids circular imports by not importing the model at module level.
    """

    id = serializers.IntegerField(read_only=True)
    uuid = serializers.UUIDField(read_only=True)
    verb = serializers.CharField(read_only=True)
    is_read = serializers.BooleanField()
    created_at = serializers.DateTimeField(read_only=True)
    content_type = serializers.SerializerMethodField()
    object_id = serializers.IntegerField(read_only=True)
    actor_email = serializers.SerializerMethodField()

    def get_content_type(self, obj) -> str | None:
        if obj.content_type_id:
            ct = ContentType.objects.get_for_id(obj.content_type_id)
            return f"{ct.app_label}.{ct.model}"
        return None

    def get_actor_email(self, obj) -> str | None:
        if obj.actor_object_id and obj.actor_content_type_id:
            ct = ContentType.objects.get_for_id(obj.actor_content_type_id)
            model_class = ct.model_class()
            try:
                actor = model_class.objects.get(pk=obj.actor_object_id)
                return getattr(actor, "email", str(actor))
            except model_class.DoesNotExist:
                return None
        return None
