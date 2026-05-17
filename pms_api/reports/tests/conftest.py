"""
Reports-specific fixtures.
"""

import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType

from pms_api.projects.models import Project
from pms_api.reports.models import ReportJob


def _grant(user, codename: str) -> None:
    """Grant the auth Permission row for `codename` on the ReportJob content type."""
    ct = ContentType.objects.get_for_model(ReportJob)
    cn = codename.split(".", 1)[1] if "." in codename else codename
    perm = Permission.objects.filter(codename=cn, content_type=ct).first()
    if perm is None:
        # Permission must be auto-created by post_migrate, but in --nomigrations mode
        # we may need to add it here. Best effort.
        perm = Permission.objects.create(
            codename=cn,
            content_type=ct,
            name=f"Auto: {cn}",
        )
    user.user_permissions.add(perm)
    # Force Django to reload permissions on the next has_perm() call.
    # force_authenticate keeps the same user instance across requests, so the
    # _perm_cache populated by an earlier call would otherwise hide the grant.
    for attr in ("_perm_cache", "_user_perm_cache", "_group_perm_cache"):
        if hasattr(user, attr):
            delattr(user, attr)


@pytest.fixture
def grant_perm():
    return _grant


@pytest.fixture
def projects_factory(db, project_type, location, department, user):
    """Bulk-create N projects across a few statuses for aggregation tests."""

    def _make(n: int = 6) -> list[Project]:
        statuses = ["registered", "in_progress", "completed"]
        out = []
        for i in range(n):
            p = Project.objects.create(
                code=f"P{i:03d}",
                title=f"Project {i}",
                project_type=project_type,
                location=location,
                implementing_department=department,
                total_budget=1000 * (i + 1),
                is_active=(i % 2 == 0),
                created_by=user,
                updated_by=user,
            )
            out.append(p)
        return out

    return _make
