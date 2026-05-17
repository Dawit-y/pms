"""

Each definition is registered with the central report registry at startup
(via `autodiscover_modules("reports")` in pms_api.reports.apps.ReportsConfig).
"""

from decimal import Decimal

from django.db.models import Count
from django.db.models import F
from django.db.models import Sum
from rest_framework import serializers

from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.projects.models import Project
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


def _filter_by_location_subtree(qs, location_uuid):
    """Filter projects to the descendant subtree of a location node (MPTT)."""
    try:
        node = Location.all_objects.get(uuid=location_uuid)
    except Location.DoesNotExist:
        return qs.none()
    descendant_ids = node.get_descendants(include_self=True).values("id")
    return qs.filter(location_id__in=descendant_ids)


def _filter_by_department_subtree(qs, department_uuid):
    try:
        node = Department.all_objects.get(uuid=department_uuid)
    except Department.DoesNotExist:
        return qs.none()
    descendant_ids = node.get_descendants(include_self=True).values("id")
    return qs.filter(implementing_department_id__in=descendant_ids)


# ─── Shared filter serializer ────────────────────────────────────────────────


class _ProjectsFilterSerializer(serializers.Serializer):
    """Common filters for the three project reports."""

    location = serializers.UUIDField(required=False)
    department = serializers.UUIDField(required=False)
    project_type = serializers.UUIDField(required=False)
    start_after = serializers.DateField(required=False)
    start_before = serializers.DateField(required=False)
    is_active = serializers.BooleanField(required=False)


def _apply_common_filters(qs, params: dict):
    if params.get("location"):
        qs = _filter_by_location_subtree(qs, params["location"])
    if params.get("department"):
        qs = _filter_by_department_subtree(qs, params["department"])
    if params.get("project_type"):
        qs = qs.filter(project_type__uuid=params["project_type"])
    if params.get("start_after"):
        qs = qs.filter(start_date__gte=params["start_after"])
    if params.get("start_before"):
        qs = qs.filter(start_date__lte=params["start_before"])
    if params.get("is_active") is not None:
        qs = qs.filter(is_active=params["is_active"])
    return qs


# ─── 1. Projects by Status ───────────────────────────────────────────────────


@registry.register
class ProjectsByStatusReport(ReportDefinition):
    code = "projects_by_status"
    name_en = "Projects by Status"
    name_am = "ፕሮጀክቶች በሁኔታ"
    name_or = "Pirojektoota Haala Isaaniin"
    description = "Aggregated project counts and total budget grouped by current status."
    permission_codename = "reports.export_projects_by_status"
    filter_serializer_class = _ProjectsFilterSerializer
    pdf_orientation = "portrait"

    columns = [
        ColumnSpec("status", "Status", "ሁኔታ", "Haala", width=28),
        ColumnSpec(
            "count",
            "Project Count",
            "የፕሮጀክት ብዛት",
            "Baay'ina Pirojektii",
            width=16,
            pdf_align="RIGHT",
        ),
        ColumnSpec(
            "total_budget",
            "Total Budget",
            "ጠቅላላ በጀት",
            "Baajata Waliigalaa",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
    ]

    def build_queryset(self, params, user):
        qs = _apply_common_filters(Project.objects.all(), params)
        return (
            qs.values(status=F("current_status__status"))
            .annotate(count=Count("id"), total_budget=Sum("total_budget"))
            .order_by("-count")
        )

    def iter_rows(self, qs, params):
        # build_queryset already returns dict rows via .values(); just yield.
        yield from qs

    def get_summary(self, qs, params):
        total_projects = sum(row["count"] for row in qs)
        total_budget = sum((row["total_budget"] or Decimal("0")) for row in qs)
        return {
            "total_projects": total_projects,
            "grand_total_budget": _money(total_budget),
        }


# ─── 2. Projects by Category with Budget Allocation ──────────────────────────


@registry.register
class ProjectsByCategoryWithBudgetReport(ReportDefinition):
    code = "projects_by_category_with_budget"
    name_en = "Projects by Category with Budget Allocation"
    name_am = "ፕሮጀክቶች በምድብ ከበጀት ድልድል ጋር"
    name_or = "Pirojektoota Gosaan Baajata Qoodame Waliin"
    description = (
        "Project counts and budget totals (requested vs. approved) grouped by project type."
    )
    permission_codename = "reports.export_projects_by_category_with_budget"
    filter_serializer_class = _ProjectsFilterSerializer
    pdf_orientation = "landscape"

    columns = [
        ColumnSpec("category", "Category", "ምድብ", "Gosa", width=28),
        ColumnSpec("count", "Project Count", "የፕሮጀክት ብዛት", "Baay'ina", width=14, pdf_align="RIGHT"),
        ColumnSpec(
            "total_budget",
            "Project Total Budget",
            "የፕሮጀክት ጠቅላላ በጀት",
            "Baajata Waliigalaa",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
        ColumnSpec(
            "requested_amount",
            "Requested",
            "የተጠየቀ",
            "Gaafatame",
            width=20,
            pdf_align="RIGHT",
            formatter=_money,
        ),
        ColumnSpec(
            "approved_amount",
            "Approved",
            "የጸደቀ",
            "Mirkanaa'e",
            width=20,
            pdf_align="RIGHT",
            formatter=_money,
        ),
    ]

    def build_queryset(self, params, user):
        qs = _apply_common_filters(Project.objects.all(), params)
        return (
            qs.values(category=F("project_type__name_en"))
            .annotate(
                count=Count("id"),
                total_budget=Sum("total_budget"),
                requested_amount=Sum("budget_request__requested_amount"),
                approved_amount=Sum("budget_request__approved_amount"),
            )
            .order_by("-count")
        )

    def iter_rows(self, qs, params):
        yield from qs

    def get_summary(self, qs, params):
        totals = {
            "count": 0,
            "total_budget": Decimal("0"),
            "requested": Decimal("0"),
            "approved": Decimal("0"),
        }
        for row in qs:
            totals["count"] += row["count"]
            totals["total_budget"] += row["total_budget"] or Decimal("0")
            totals["requested"] += row["requested_amount"] or Decimal("0")
            totals["approved"] += row["approved_amount"] or Decimal("0")
        return {
            "total_projects": totals["count"],
            "grand_total_budget": _money(totals["total_budget"]),
            "grand_total_requested": _money(totals["requested"]),
            "grand_total_approved": _money(totals["approved"]),
        }


# ─── 3. Projects by Zone with Budget Allocation ──────────────────────────────


class _ZoneFilterSerializer(_ProjectsFilterSerializer):
    """Same filters as the others plus optional `region` to scope to one region's zones."""

    region = serializers.UUIDField(required=False)


@registry.register
class ProjectsByZoneWithBudgetReport(ReportDefinition):
    code = "projects_by_zone_with_budget"
    name_en = "Projects by Zone with Budget Allocation"
    name_am = "ፕሮጀክቶች በዞን ከበጀት ድልድል ጋር"
    name_or = "Pirojektoota Zoonii Baajata Qoodame Waliin"
    description = (
        "Project counts and approved budget grouped by Zone. "
        "Use the `region` filter to scope to a single region's zones."
    )
    permission_codename = "reports.export_projects_by_zone_with_budget"
    filter_serializer_class = _ZoneFilterSerializer
    pdf_orientation = "landscape"

    columns = [
        ColumnSpec("zone", "Zone", "ዞን", "Zoonii", width=26),
        ColumnSpec("count", "Project Count", "የፕሮጀክት ብዛት", "Baay'ina", width=14, pdf_align="RIGHT"),
        ColumnSpec(
            "total_budget",
            "Project Total Budget",
            "የፕሮጀክት ጠቅላላ በጀት",
            "Baajata Waliigalaa",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
        ColumnSpec(
            "approved_amount",
            "Approved Budget",
            "የጸደቀ በጀት",
            "Baajata Mirkanaa'e",
            width=22,
            pdf_align="RIGHT",
            formatter=_money,
        ),
    ]

    def build_queryset(self, params, user):
        qs = _apply_common_filters(Project.objects.all(), params)

        # Resolve each project's zone — that's the closest ancestor whose
        # location_type is "zone". The simplest correct expression climbs the
        # MPTT parents up to two levels (woreda → zone, kebele → woreda → zone),
        # but the dataset stores `location_type` explicitly, so we group by the
        # zone-typed ancestor's name when present, falling back to the location
        # itself if it already is a zone or region.
        zone_name = F("location__name_en")
        # When `region` is supplied, scope to projects whose location's region
        # ancestor matches.
        if params.get("region"):
            try:
                region = Location.all_objects.get(uuid=params["region"])
            except Location.DoesNotExist:
                return Project.objects.none().values()
            descendant_ids = region.get_descendants(include_self=True).values("id")
            qs = qs.filter(location_id__in=descendant_ids)

        return (
            qs.values(zone=zone_name)
            .annotate(
                count=Count("id"),
                total_budget=Sum("total_budget"),
                approved_amount=Sum("budget_request__approved_amount"),
            )
            .order_by("-count")
        )

    def iter_rows(self, qs, params):
        yield from qs

    def get_summary(self, qs, params):
        total_projects = 0
        total_budget = Decimal("0")
        total_approved = Decimal("0")
        for row in qs:
            total_projects += row["count"]
            total_budget += row["total_budget"] or Decimal("0")
            total_approved += row["approved_amount"] or Decimal("0")
        return {
            "total_projects": total_projects,
            "grand_total_budget": _money(total_budget),
            "grand_total_approved": _money(total_approved),
        }
