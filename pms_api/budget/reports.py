"""
Budget-focused standardized reports.
"""

from decimal import Decimal

from django.db.models import Count
from django.db.models import F
from django.db.models import Sum
from rest_framework import serializers

from pms_api.budget.models import BudgetRequest
from pms_api.lookups.models import Department
from pms_api.reports.base import ColumnSpec
from pms_api.reports.base import ReportDefinition
from pms_api.reports.registry import registry


def _money(value) -> str:
    if value is None:
        return ""
    try:
        return f"{Decimal(value):,.2f}"
    except (TypeError, ValueError):
        return str(value)


class _BudgetFilterSerializer(serializers.Serializer):
    fiscal_year = serializers.CharField(required=False)
    department = serializers.UUIDField(required=False)
    status = serializers.ChoiceField(
        required=False,
        choices=[c[0] for c in BudgetRequest.STATUS_CHOICES],
    )


def _apply_budget_filters(qs, params: dict):
    if params.get("fiscal_year"):
        qs = qs.filter(fiscal_year=params["fiscal_year"])
    if params.get("status"):
        qs = qs.filter(status=params["status"])
    if params.get("department"):
        try:
            node = Department.all_objects.get(uuid=params["department"])
        except Department.DoesNotExist:
            return qs.none()
        descendant_ids = node.get_descendants(include_self=True).values("id")
        qs = qs.filter(current_department_id__in=descendant_ids)
    return qs


# ─── 1. Budget by Fiscal Year ────────────────────────────────────────────────


@registry.register
class BudgetByFiscalYearReport(ReportDefinition):
    code = "budget_by_fiscal_year"
    name_en = "Budget Requests by Fiscal Year"
    name_am = "የበጀት ጥያቄዎች በበጀት ዓመት"
    name_or = "Gaaffii Baajataa Bara Baajataan"
    description = "Budget request totals grouped by fiscal year."
    permission_codename = "reports.export_budget_by_fiscal_year"
    filter_serializer_class = _BudgetFilterSerializer
    pdf_orientation = "portrait"

    columns = [
        ColumnSpec("fiscal_year", "Fiscal Year", "የበጀት ዓመት", "Bara Baajataa", width=18),
        ColumnSpec("count", "Requests", "ጥያቄዎች", "Gaaffii", width=14, pdf_align="RIGHT"),
        ColumnSpec(
            "requested",
            "Requested",
            "የተጠየቀ",
            "Gaafatame",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
        ColumnSpec(
            "approved",
            "Approved",
            "የጸደቀ",
            "Mirkanaa'e",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
    ]

    def build_queryset(self, params, user):
        qs = _apply_budget_filters(BudgetRequest.objects.all(), params)
        return (
            qs.values("fiscal_year")
            .annotate(
                count=Count("id"),
                requested=Sum("requested_amount"),
                approved=Sum("approved_amount"),
            )
            .order_by("-fiscal_year")
        )

    def iter_rows(self, qs, params):
        yield from qs

    def get_summary(self, qs, params):
        total_count = 0
        total_req = Decimal("0")
        total_app = Decimal("0")
        for row in qs:
            total_count += row["count"]
            total_req += row["requested"] or Decimal("0")
            total_app += row["approved"] or Decimal("0")
        return {
            "total_requests": total_count,
            "grand_total_requested": _money(total_req),
            "grand_total_approved": _money(total_app),
        }


# ─── 2. Budget by Department ─────────────────────────────────────────────────


@registry.register
class BudgetByDepartmentReport(ReportDefinition):
    code = "budget_by_department"
    name_en = "Budget Requests by Department"
    name_am = "የበጀት ጥያቄዎች በመምሪያ"
    name_or = "Gaaffii Baajataa Kutaa Hojiitiin"
    description = "Budget request totals grouped by current owning department."
    permission_codename = "reports.export_budget_by_department"
    filter_serializer_class = _BudgetFilterSerializer
    pdf_orientation = "landscape"

    columns = [
        ColumnSpec("department", "Department", "መምሪያ", "Kutaa Hojii", width=30),
        ColumnSpec("count", "Requests", "ጥያቄዎች", "Gaaffii", width=14, pdf_align="RIGHT"),
        ColumnSpec(
            "requested",
            "Requested",
            "የተጠየቀ",
            "Gaafatame",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
        ColumnSpec(
            "approved",
            "Approved",
            "የጸደቀ",
            "Mirkanaa'e",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
    ]

    def build_queryset(self, params, user):
        qs = _apply_budget_filters(BudgetRequest.objects.all(), params)
        return (
            qs.values(department=F("current_department__name_en"))
            .annotate(
                count=Count("id"),
                requested=Sum("requested_amount"),
                approved=Sum("approved_amount"),
            )
            .order_by("-count")
        )

    def iter_rows(self, qs, params):
        yield from qs

    def get_summary(self, qs, params):
        total_count = 0
        total_req = Decimal("0")
        total_app = Decimal("0")
        for row in qs:
            total_count += row["count"]
            total_req += row["requested"] or Decimal("0")
            total_app += row["approved"] or Decimal("0")
        return {
            "total_requests": total_count,
            "grand_total_requested": _money(total_req),
            "grand_total_approved": _money(total_app),
        }
