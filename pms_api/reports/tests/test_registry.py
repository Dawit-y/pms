"""
ReportRegistry behavior.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured

from pms_api.core.exceptions import ResourceNotFound
from pms_api.reports.base import ColumnSpec
from pms_api.reports.base import ReportDefinition
from pms_api.reports.registry import ReportRegistry


def test_register_and_lookup_by_code():
    reg = ReportRegistry()

    @reg.register
    class _R(ReportDefinition):
        code = "_unit_test_one"
        name_en = "X"
        columns = [ColumnSpec("k", "K")]

        def build_queryset(self, params, user):
            return []

    assert reg.get("_unit_test_one").code == "_unit_test_one"
    assert reg.all()[0].code == "_unit_test_one"


def test_duplicate_codes_rejected():
    reg = ReportRegistry()

    @reg.register
    class _A(ReportDefinition):
        code = "dup"
        name_en = "A"

        def build_queryset(self, params, user):
            return []

    with pytest.raises(ImproperlyConfigured):

        @reg.register
        class _B(ReportDefinition):
            code = "dup"
            name_en = "B"

            def build_queryset(self, params, user):
                return []


def test_missing_code_rejected():
    reg = ReportRegistry()

    with pytest.raises(ImproperlyConfigured):

        @reg.register
        class _R(ReportDefinition):
            name_en = "no code"

            def build_queryset(self, params, user):
                return []


def test_get_unknown_raises_resource_not_found():
    reg = ReportRegistry()
    with pytest.raises(ResourceNotFound):
        reg.get("does_not_exist")


def test_reserved_code_jobs_rejected():
    """`jobs` collides with /api/v1/reports/jobs/ — must be rejected at registration."""
    reg = ReportRegistry()

    with pytest.raises(ImproperlyConfigured, match="reserved"):

        @reg.register
        class _Conflict(ReportDefinition):
            code = "jobs"
            name_en = "Conflict"

            def build_queryset(self, params, user):
                return []


def test_allowed_for_filters_by_permission(user):
    reg = ReportRegistry()

    @reg.register
    class _NoPerm(ReportDefinition):
        code = "_allowed_no_perm"
        name_en = "no perm"
        permission_codename = ""

        def build_queryset(self, params, user):
            return []

    @reg.register
    class _Gated(ReportDefinition):
        code = "_allowed_gated"
        name_en = "gated"
        permission_codename = "reports.export_projects_by_status"

        def build_queryset(self, params, user):
            return []

    # Regular user has neither permission -> only the no-perm one comes back.
    allowed = reg.allowed_for(user)
    codes = {d.code for d in allowed}
    assert "_allowed_no_perm" in codes
    assert "_allowed_gated" not in codes
