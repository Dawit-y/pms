import uuid

from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.utils import timezone
from simple_history.models import HistoricalRecords

from pms_api.core.signals import model_changed
from pms_api.core.signals import model_deleted


class UUIDMixin(models.Model):
    """Every model gets both an auto-increment PK and a public UUID."""

    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        db_index=True,
    )

    class Meta:
        abstract = True


class TimestampMixin(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class AuditMixin(models.Model):
    """Tracks which user created/updated each record."""

    created_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created",
    )
    updated_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_updated",
    )

    class Meta:
        abstract = True


class SoftDeleteManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(is_deleted=False)


class AllObjectsManager(models.Manager):
    """Use Model.all_objects.all() to see soft-deleted records too."""


class SoftDeleteMixin(models.Model):
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_deleted",
    )

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta:
        abstract = True

    def delete(self, deleted_by=None, *args, **kwargs):
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = deleted_by
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def hard_delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)

    def restore(self):
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])


class RowLevelSecurityMixin(models.Model):
    """
    Attach an optional owner or department for row-level access checks.
    """

    owner = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_owned",
    )

    class Meta:
        abstract = True


class SignalMixin:
    """
    Automatically connects post_save, post_delete signals on the model.
    """

    @classmethod
    def connect_signals(cls):
        post_save.connect(cls._on_post_save, sender=cls)
        post_delete.connect(cls._on_post_delete, sender=cls)

    @classmethod
    def _on_post_save(cls, sender, instance, created, **kwargs):
        model_changed.send(sender=sender, instance=instance, created=created)

    @classmethod
    def _on_post_delete(cls, sender, instance, **kwargs):
        model_deleted.send(sender=sender, instance=instance)


class HistoryMixin(models.Model):
    """
    history tracking mixin using django-simple-history.

    Features:
    - Automatic tracking of all field changes
    - User attribution via HistoryRequestMiddleware
    - Soft-delete aware (tracks deletion events)
    - Queryable history via .history.all()
    - Diff support between versions
    - Revert capability

    Usage:
        class MyModel(HistoryMixin, BaseModel):
            # your fields
            pass

    Access history:
        obj.history.all()                    # All historical records
        obj.history.first()                  # Most recent change
        obj.history.as_of(datetime)          # State at specific time

    Compare versions:
        current = obj.history.first()
        previous = current.prev_record
        delta = current.diff_against(previous)
        for change in delta.changes:
            print(f"{change.field}: {change.old} -> {change.new}")

    Revert:
        historical_obj = obj.history.first()
        historical_obj.instance.save()       # Reverts to that version
    """

    history = HistoricalRecords(
        inherit=True,
        # Exclude these fields from history tracking to reduce noise
        excluded_fields=["updated_at"],
        # Custom history table naming
        table_name=None,  # Auto-generates as 'historical_{model_name}'
        # Track history changes even during migrations
        history_change_reason_field=models.TextField(null=True, blank=True),
    )

    class Meta:
        abstract = True

    def save_with_history_reason(self, reason: str, *args, **kwargs):
        """
        Save with a custom change reason that appears in history.

        Example:
            project.title = "New Title"
            project.save_with_history_reason("Updated title per client request")
        """
        self._change_reason = reason
        self.save(*args, **kwargs)

    def get_history_summary(self, limit: int = 10) -> list[dict]:
        """
        Returns a simplified history summary for API responses.

        Returns:
            List of dicts with: date, user, action, changed_fields
        """
        history_records = []
        for record in self.history.all()[:limit]:
            prev = record.prev_record
            changed_fields = []

            if prev:
                delta = record.diff_against(prev)
                changed_fields = [
                    {
                        "field": change.field,
                        "old": str(change.old),
                        "new": str(change.new),
                    }
                    for change in delta.changes
                ]

            history_records.append(
                {
                    "date": record.history_date,
                    "user": record.history_user.email if record.history_user else None,
                    "action": record.get_history_type_display(),
                    "changed_fields": changed_fields,
                    "change_reason": getattr(record, "history_change_reason", None),
                },
            )

        return history_records
