"""
Report-specific permission classes + post_migrate sync of per-report codenames.
"""

import logging

from rest_framework.permissions import BasePermission

logger = logging.getLogger(__name__)


class IsReportJobOwner(BasePermission):
    """Object-level: only the user who requested the report (or superuser) passes."""

    message = "You can only operate on your own report jobs."

    def has_object_permission(self, request, view, obj):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        return user.is_superuser or obj.created_by_id == user.id


def sync_report_permissions(*, stdout=None) -> tuple[int, int]:
    """
    Ensure a Django Permission row exists for every report's
    `permission_codename`. Idempotent.

    Returns (created_count, existing_count).
    """
    from django.contrib.auth.models import Permission  # noqa: PLC0415
    from django.contrib.contenttypes.models import ContentType  # noqa: PLC0415

    from .models import ReportJob  # noqa: PLC0415
    from .registry import registry  # noqa: PLC0415

    ct = ContentType.objects.get_for_model(ReportJob)
    created = existing = 0
    for definition in registry.all():
        codename_full = definition.permission_codename
        if not codename_full:
            continue
        # codenames are "<app>.<codename>" — split off the app prefix
        if "." in codename_full:
            _app, codename = codename_full.split(".", 1)
        else:
            codename = codename_full
        # `name` is the human label shown in the Django admin permission picker.
        name = f"Can export report: {definition.name_en or definition.code}"
        _, was_created = Permission.objects.get_or_create(
            codename=codename,
            content_type=ct,
            defaults={"name": name},
        )
        if was_created:
            created += 1
            if stdout is not None:
                stdout.write(f"  + Created permission {ct.app_label}.{codename}")
        else:
            existing += 1
    return created, existing


def sync_report_permissions_signal(sender, **kwargs):
    """post_migrate receiver. Wraps sync_report_permissions and swallows errors."""
    try:
        created, existing = sync_report_permissions()
        if created:
            logger.info("Created %d report permission(s); %d already existed.", created, existing)
    except Exception:  # noqa: BLE001
        # Don't break migrations if the registry hasn't been populated yet
        # (e.g. when running migrations from a fresh checkout before all apps load).
        logger.warning("Could not sync report permissions during post_migrate.", exc_info=True)
