"""
End-to-end generate_report task (with CELERY_TASK_ALWAYS_EAGER=True).
"""

import pytest

from pms_api.reports.models import ReportJob


@pytest.mark.django_db
def test_generate_report_writes_excel_and_marks_success(projects_factory, user):
    projects_factory(n=6)
    job = ReportJob.objects.create(
        report_code="projects_by_status",
        format="xlsx",
        params={"filters": {}, "include_summary": True},
        created_by=user,
        updated_by=user,
    )
    from pms_api.reports.tasks import generate_report  # noqa: PLC0415

    generate_report.apply(args=[str(job.uuid)])

    job.refresh_from_db()
    assert job.status == ReportJob.STATUS_SUCCESS
    assert job.progress == 100
    assert job.row_count is not None
    assert job.row_count > 0
    assert job.file.name.endswith(".xlsx")
    assert job.file_size is not None
    assert job.file_size > 0
    assert job.error_message == ""


@pytest.mark.django_db
def test_generate_report_pdf_path(projects_factory, user):
    projects_factory(n=4)
    job = ReportJob.objects.create(
        report_code="projects_by_status",
        format="pdf",
        params={"filters": {}, "include_summary": False},
        created_by=user,
        updated_by=user,
    )
    from pms_api.reports.tasks import generate_report  # noqa: PLC0415

    generate_report.apply(args=[str(job.uuid)])

    job.refresh_from_db()
    assert job.status == ReportJob.STATUS_SUCCESS
    assert job.file.name.endswith(".pdf")
    with job.file.open("rb") as f:
        assert f.read(4) == b"%PDF"


@pytest.mark.django_db
def test_generate_report_unknown_code_marks_failed(user):
    job = ReportJob.objects.create(
        report_code="not_a_real_report",
        format="xlsx",
        params={"filters": {}},
        created_by=user,
        updated_by=user,
    )
    from pms_api.reports.tasks import generate_report  # noqa: PLC0415

    with pytest.raises(Exception):  # noqa: B017, PT011
        generate_report.apply(args=[str(job.uuid)], throw=True)

    job.refresh_from_db()
    assert job.status == ReportJob.STATUS_FAILED
    assert job.error_message


@pytest.mark.django_db
def test_concurrent_cancel_not_overwritten_by_completion(projects_factory, user, monkeypatch):
    """
    Race scenario: /cancel/ flips the row to `cancelled` while the task is mid-write.
    The task's final compare-and-swap MUST see status != running and skip the
    success update — otherwise the cancel is silently undone.
    """
    from pms_api.reports.exporters.excel import ExcelExporter  # noqa: PLC0415
    from pms_api.reports.tasks import generate_report  # noqa: PLC0415

    projects_factory(n=4)
    job = ReportJob.objects.create(
        report_code="projects_by_status",
        format="xlsx",
        params={"filters": {}},
        created_by=user,
        updated_by=user,
    )

    original_write_chunk = ExcelExporter.write_chunk

    def cancel_mid_stream(self, rows):
        # Simulate a /cancel/ arriving while the task is still writing chunks.
        ReportJob.objects.filter(pk=job.pk).update(
            status=ReportJob.STATUS_CANCELLED,
        )
        return original_write_chunk(self, rows)

    monkeypatch.setattr(ExcelExporter, "write_chunk", cancel_mid_stream)

    generate_report.apply(args=[str(job.uuid)])

    job.refresh_from_db()
    assert job.status == ReportJob.STATUS_CANCELLED, (
        f"CAS failed — task overwrote cancel with status={job.status!r}"
    )
