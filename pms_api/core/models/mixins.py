import uuid

from django.db import models
from django.db.models.signals import post_delete
from django.db.models.signals import post_save
from django.utils import timezone

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
