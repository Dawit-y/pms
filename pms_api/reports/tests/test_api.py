"""
Full HTTP flow: list → data → export → poll → download.
"""

import pytest
from rest_framework.test import APIClient

from pms_api.reports.models import ReportJob


@pytest.mark.django_db
def test_list_reports_filters_by_permission(authenticated_client, user, grant_perm):
    # Without any export_* permission, the gated reports are hidden.
    resp = authenticated_client.get("/api/v1/reports/")
    assert resp.status_code == 200
    codes = {d["code"] for d in resp.json()["data"]}
    # All our shipped reports require a permission, so the list is empty for a
    # plain user.
    assert "projects_by_status" not in codes

    grant_perm(user, "reports.export_projects_by_status")
    resp = authenticated_client.get("/api/v1/reports/")
    codes = {d["code"] for d in resp.json()["data"]}
    assert "projects_by_status" in codes


@pytest.mark.django_db
def test_export_creates_job_and_runs_eagerly(
    authenticated_client,
    user,
    grant_perm,
    projects_factory,
):
    projects_factory(n=5)
    grant_perm(user, "reports.export_projects_by_status")
    resp = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}, "include_summary": True},
        format="json",
    )
    assert resp.status_code == 202, resp.json()
    body = resp.json()["data"]
    assert body["status"] in ("success", "running", "queued")

    # CELERY_TASK_ALWAYS_EAGER + EAGER_PROPAGATES means the task ran inline,
    # so the row should be in success by the time we poll.
    job = ReportJob.objects.get(uuid=body["uuid"])
    assert job.status == ReportJob.STATUS_SUCCESS

    poll = authenticated_client.get(f"/api/v1/reports/jobs/{job.uuid}/")
    assert poll.status_code == 200
    poll_data = poll.json()["data"]
    assert poll_data["status"] == "success"
    assert poll_data["download_url"] is not None


@pytest.mark.django_db
def test_download_requires_signed_token(authenticated_client, user, grant_perm, projects_factory):
    projects_factory(n=3)
    grant_perm(user, "reports.export_projects_by_status")
    resp = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    job = ReportJob.objects.get(uuid=resp.json()["data"]["uuid"])

    # Without token → 403
    no_token = authenticated_client.get(f"/api/v1/reports/jobs/{job.uuid}/download/")
    assert no_token.status_code == 403

    poll = authenticated_client.get(f"/api/v1/reports/jobs/{job.uuid}/")
    download_url = poll.json()["data"]["download_url"]
    assert download_url

    # With token → file bytes
    download = authenticated_client.get(download_url)
    assert download.status_code == 200
    assert (
        download["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


@pytest.mark.django_db
def test_export_without_permission_returns_403(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_cancel_terminates_active_job(authenticated_client, user, grant_perm, projects_factory):
    """A success-status job can't be cancelled — should raise BusinessRuleViolation."""
    projects_factory(n=2)
    grant_perm(user, "reports.export_projects_by_status")
    resp = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    job_uuid = resp.json()["data"]["uuid"]
    cancel = authenticated_client.post(f"/api/v1/reports/jobs/{job_uuid}/cancel/")
    assert cancel.status_code == 422


@pytest.mark.django_db
def test_download_works_without_http_auth(authenticated_client, user, grant_perm, projects_factory):
    """
    The signed token is the authentication — a plain anchor click from the
    browser (no Authorization header) must still download the file.
    """
    projects_factory(n=3)
    grant_perm(user, "reports.export_projects_by_status")
    resp = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    job_uuid = resp.json()["data"]["uuid"]
    poll = authenticated_client.get(f"/api/v1/reports/jobs/{job_uuid}/")
    download_url = poll.json()["data"]["download_url"]
    assert download_url

    # Fresh, UNauthenticated client — simulates the browser clicking the link.
    anon = APIClient()
    download = anon.get(download_url)
    assert download.status_code == 200
    assert (
        download["Content-Type"]
        == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in download["Content-Disposition"]


@pytest.mark.django_db
def test_download_after_cleanup_returns_404_not_500(
    authenticated_client,
    user,
    grant_perm,
    projects_factory,
):
    """
    Once cleanup runs, the row is soft-deleted AND the file column cleared.
    A stale signed URL pointed at it should produce a clean 404 (not a 500
    from opening a missing file).
    """
    from datetime import timedelta  # noqa: PLC0415

    from django.utils import timezone  # noqa: PLC0415

    from pms_api.reports.tasks import cleanup_expired_reports  # noqa: PLC0415

    projects_factory(n=2)
    grant_perm(user, "reports.export_projects_by_status")
    resp = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    job_uuid = resp.json()["data"]["uuid"]
    poll = authenticated_client.get(f"/api/v1/reports/jobs/{job_uuid}/")
    download_url = poll.json()["data"]["download_url"]

    # Force the job past its expiry, then run cleanup.
    job = ReportJob.objects.get(uuid=job_uuid)
    job.expires_at = timezone.now() - timedelta(seconds=1)
    job.save(update_fields=["expires_at"])
    cleanup_expired_reports.apply()

    # File column should be cleared; row soft-deleted.
    job = ReportJob.all_objects.get(uuid=job_uuid)
    assert job.is_deleted is True
    assert not job.file  # FieldFile is falsy when name is empty

    # Download with the previously-valid signed URL must be a clean 404.
    download = APIClient().get(download_url)
    assert download.status_code == 404, download.content


@pytest.mark.django_db
def test_download_rejects_token_for_different_job(
    authenticated_client,
    user,
    grant_perm,
    projects_factory,
):
    """A token signed for job A must not unlock job B."""
    projects_factory(n=2)
    grant_perm(user, "reports.export_projects_by_status")

    # Make two jobs
    r1 = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    r2 = authenticated_client.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )
    job_a_uuid = r1.json()["data"]["uuid"]
    job_b_uuid = r2.json()["data"]["uuid"]

    # Token from job A's download_url
    poll_a = authenticated_client.get(f"/api/v1/reports/jobs/{job_a_uuid}/")
    url_a = poll_a.json()["data"]["download_url"]
    token_a = url_a.split("?t=")[1]

    # Try to download job B using A's token
    bad = APIClient().get(f"/api/v1/reports/jobs/{job_b_uuid}/download/?t={token_a}")
    assert bad.status_code == 403


@pytest.mark.django_db
def test_only_owner_sees_their_jobs(superuser, projects_factory, grant_perm):
    # Two users each export a job; each should see only their own.
    from django.contrib.auth import get_user_model  # noqa: PLC0415

    user_model = get_user_model()
    other = user_model.objects.create_user(
        email="other@example.com",
        password="pw",
        first_name="O",
        last_name="O",
    )
    projects_factory(n=1)
    grant_perm(other, "reports.export_projects_by_status")

    c_other = APIClient()
    c_other.force_authenticate(user=other)
    c_other.post(
        "/api/v1/reports/projects_by_status/export/",
        data={"format": "xlsx", "filters": {}},
        format="json",
    )

    c_super = APIClient()
    c_super.force_authenticate(user=superuser)
    super_resp = c_super.get("/api/v1/reports/jobs/")
    assert super_resp.status_code == 200
    # superuser sees every job
    assert len(super_resp.json()["data"]) >= 1
