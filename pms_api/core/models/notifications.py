from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from .base import BaseModel


class Notification(BaseModel):
    """
    In-app notification. ContentType FK means any model can trigger one.

    Example: when a BudgetRequest is forwarded to department X,
    a Notification is created for each user in that department.
    """

    recipient = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    verb = models.CharField(
        max_length=255,
    )  # e.g. "forwarded a budget request to your department"
    is_read = models.BooleanField(default=False, db_index=True)

    # Generic FK — can point to any model instance
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    content_object = GenericForeignKey("content_type", "object_id")

    actor_content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="actor_notifications",
    )
    actor_object_id = models.PositiveIntegerField(null=True, blank=True)
    actor = GenericForeignKey("actor_content_type", "actor_object_id")

    class Meta:
        app_label = "core"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "is_read"]),
        ]

    def __str__(self):
        return f"Notification({self.recipient}, {self.verb})"


def notify(recipient, verb, action_object=None, actor=None):
    """
    Helper to create a notification from anywhere in the codebase.

    Usage:
        from pms_api.core.models.notifications import notify
        notify(
            recipient=user,
            verb="forwarded a budget request to your department",
            action_object=budget_request_instance,
            actor=forwarding_user,
        )
    """
    ct = ContentType.objects.get_for_model(action_object) if action_object else None
    actor_ct = ContentType.objects.get_for_model(actor) if actor else None
    Notification.objects.create(
        recipient=recipient,
        verb=verb,
        content_type=ct,
        object_id=action_object.pk if action_object else None,
        actor_content_type=actor_ct,
        actor_object_id=actor.pk if actor else None,
    )
