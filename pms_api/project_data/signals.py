from django.dispatch import receiver

from pms_api.core.models.notifications import notify
from pms_api.core.signals import model_changed
from pms_api.project_data.models import Risk


@receiver(model_changed, sender=Risk)
def notify_high_risk_owner(sender, instance, created, **kwargs):
    if not created:
        return

    if instance.impact not in {"high", "critical"}:
        return

    notify(
        recipient=instance.risk_owner,
        verb=f"High-risk '{instance.title}' has been assigned to you.",
        action_object=instance,
        actor=instance.created_by,
    )
