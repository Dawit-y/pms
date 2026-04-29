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
    serializer for django-simple-history records.

    Provides:
    - Full change tracking with field-level diffs
    - User attribution
    - Change reasons
    - History type (created/updated/deleted)
    - Timestamp information
    """

    history_id = serializers.IntegerField(read_only=True)
    history_date = serializers.DateTimeField(read_only=True)
    history_type = serializers.SerializerMethodField()
    history_user = serializers.SerializerMethodField()
    history_change_reason = serializers.CharField(read_only=True, allow_null=True)
    changed_fields = serializers.SerializerMethodField()

    # Include the actual record data for context
    record_data = serializers.SerializerMethodField()

    def get_history_type(self, record) -> str:
        """Returns human-readable action type."""
        type_map = {
            "+": "Created",
            "~": "Updated",
            "-": "Deleted",
        }
        return type_map.get(record.history_type, record.history_type)

    def get_history_user(self, record) -> dict | None:
        """Returns user info who made the change."""
        if not record.history_user_id:
            return None
        return {
            "email": record.history_user.email,
            "uuid": str(record.history_user.uuid),
            "full_name": getattr(record.history_user, "get_full_name", lambda: None)(),
        }

    def get_changed_fields(self, record) -> list[dict]:
        """
        Returns detailed field-level changes.

        Format: [{"field": "title", "old": "Old Title", "new": "New Title"}]
        """
        try:
            prev = record.prev_record
        except Exception:  # noqa: BLE001
            return []

        if not prev:
            # First record (creation) - show all non-null fields
            if record.history_type == "+":
                fields = []
                for field in record.instance._meta.fields:  # noqa: SLF001
                    field_name = field.name
                    if field_name in ["id", "uuid", "created_at", "updated_at"]:
                        continue
                    value = getattr(record, field_name, None)
                    if value is not None:
                        fields.append(
                            {
                                "field": field_name,
                                "old": None,
                                "new": self._format_field_value(value),
                            },
                        )
                return fields
            return []

        # Compare with previous version
        delta = record.diff_against(prev)
        return [
            {
                "field": change.field,
                "old": self._format_field_value(change.old),
                "new": self._format_field_value(change.new),
            }
            for change in delta.changes
        ]

    def get_record_data(self, record) -> dict:
        """
        Returns a snapshot of key fields at this point in history.
        Useful for understanding the full state, not just changes.
        """
        # Only include key identifying fields to keep response size manageable
        data = {
            "uuid": str(getattr(record, "uuid", None)),
        }

        # Add model-specific key fields
        if hasattr(record, "code"):
            data["code"] = record.code
        if hasattr(record, "title"):
            data["title"] = record.title
        if hasattr(record, "name"):
            data["name"] = record.name
        if hasattr(record, "status"):
            data["status"] = record.status

        return data

    def _format_field_value(self, value) -> str:
        """Format field values for display."""
        if value is None:
            return None
        if hasattr(value, "isoformat"):  # datetime/date
            return value.isoformat()
        return str(value)


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
