"""
Abstract report contract.

Subclass `ReportDefinition`, declare a `.code`, columns, filter serializer, and
`build_queryset`. Then decorate with `@registry.register` so the singleton can
hand the report definition back to the API and the Celery task by string code.

The same definition powers both the JSON `/data/` endpoint (used by the React
table) and the background export task (.xlsx / .pdf). That contract is what
keeps a report's logic in one file.
"""

from collections.abc import Callable
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.db.models import QuerySet
from rest_framework.serializers import Serializer


@dataclass(frozen=True)
class ColumnSpec:
    """Declarative column definition shared by the JSON table and the file exports."""

    key: str  # row dict key produced by build_queryset / serializer
    label_en: str
    label_am: str = ""
    label_or: str = ""
    width: int = 20  # excel column width in characters
    formatter: Callable[[Any], Any] | None = None
    pdf_align: str = "LEFT"  # LEFT | CENTER | RIGHT (ReportLab style alignment)


class ReportDefinition:
    """
    Base class for every standardized report.

    Subclasses must set: `code`, `name_en`, `permission_codename`,
    `filter_serializer_class`, `columns`, and override `build_queryset`.

    Optional: `name_am`, `name_or`, `description`, `pdf_orientation`,
    `pdf_page_size`, `max_rows_xlsx`, `max_rows_pdf`, `iter_rows`, `get_summary`.
    """

    code: str = ""
    name_en: str = ""
    name_am: str = ""
    name_or: str = ""
    description: str = ""

    permission_codename: str = ""

    filter_serializer_class: type[Serializer] | None = None
    row_serializer_class: type[Serializer] | None = None

    columns: list[ColumnSpec] = []

    pdf_page_size: str = "A4"  # "A4" or "Letter"
    pdf_orientation: str = "landscape"  # "portrait" or "landscape"

    max_rows_xlsx: int | None = None  # None → use settings.REPORT_MAX_ROWS_XLSX
    max_rows_pdf: int | None = None

    # ── Required overrides ───────────────────────────────────────────────

    def build_queryset(self, params: dict, user) -> QuerySet:
        """Return the QuerySet (or ValuesQuerySet) that backs the report."""
        raise NotImplementedError

    # ── Optional overrides ───────────────────────────────────────────────

    def iter_rows(self, qs, params: dict) -> Iterable[dict]:
        """
        Stream rows as dicts. Default: serialize via `row_serializer_class`,
        falling back to assuming the qs already yields dicts (from `.values(...)`).

        Always uses `.iterator(chunk_size=500)` when available so even
        `.values()` querysets don't materialize their full result set into
        Django's per-queryset result cache before the exporter has finished
        consuming them.
        """
        chunk = 500
        # `.iterator()` exists on both Model querysets and ValuesQuerySets; fall
        # back to plain iteration only for non-queryset iterables (e.g. a list
        # returned from a custom build_queryset).
        rows = qs.iterator(chunk_size=chunk) if hasattr(qs, "iterator") else iter(qs)
        if self.row_serializer_class is None:
            yield from rows
            return
        for obj in rows:
            yield self.row_serializer_class(obj).data

    def get_summary(self, qs, params: dict) -> dict:
        """Optional aggregate summary (totals, counts). Appears at the bottom of exports."""
        return {}

    def get_filter_schema(self) -> dict:
        """
        Introspect the filter serializer for the frontend so the React side knows
        which filters to render. Returns `{field_name: {type, required, choices?}}`.
        """
        if self.filter_serializer_class is None:
            return {}
        schema: dict = {}
        instance = self.filter_serializer_class()
        for name, field in instance.fields.items():
            entry: dict[str, Any] = {
                "type": field.__class__.__name__.removesuffix("Field").lower() or "string",
                "required": bool(field.required),
            }
            choices = getattr(field, "choices", None)
            if choices:
                entry["choices"] = [{"value": k, "label": v} for k, v in choices.items()]
            schema[name] = entry
        return schema

    def get_column_dicts(self) -> list[dict]:
        """Serializable form of `columns` for the API."""
        return [
            {
                "key": c.key,
                "label_en": c.label_en,
                "label_am": c.label_am,
                "label_or": c.label_or,
                "pdf_align": c.pdf_align,
            }
            for c in self.columns
        ]
