"""
Module-level singleton that holds every registered ReportDefinition.

Reports populate this registry at app-startup time via
`autodiscover_modules("reports")` (called from ReportsConfig.ready). Anywhere
that needs to look up a report — the API ViewSet, the Celery task — goes
through `registry.get(code)`.
"""

from django.core.exceptions import ImproperlyConfigured

from .base import ReportDefinition

# Codes that conflict with `/api/v1/reports/<code>/` URL routing because they
# match an adjacent route segment. Keep this list narrow — every entry here is
# a footgun that would silently shadow a future report.
RESERVED_REPORT_CODES = frozenset({"jobs"})


class ReportRegistry:
    def __init__(self) -> None:
        self._reports: dict[str, ReportDefinition] = {}

    def register(self, cls: type[ReportDefinition]) -> type[ReportDefinition]:
        """Decorator. Instantiates the definition and stores it by code."""
        if not getattr(cls, "code", ""):
            msg = f"{cls.__module__}.{cls.__name__} must define a non-empty `code`."
            raise ImproperlyConfigured(msg)
        if cls.code in RESERVED_REPORT_CODES:
            msg = (
                f"{cls.__module__}.{cls.__name__}: report code {cls.code!r} is reserved "
                "(conflicts with /api/v1/reports/<code>/ URL routing)."
            )
            raise ImproperlyConfigured(msg)
        if cls.code in self._reports:
            msg = (
                f"Duplicate report code {cls.code!r}. "
                f"Already registered by {type(self._reports[cls.code]).__name__}."
            )
            raise ImproperlyConfigured(msg)
        self._reports[cls.code] = cls()
        return cls

    def get(self, code: str) -> ReportDefinition:
        # Local import — avoid pulling the DRF exception module at app-load time.
        from pms_api.core.exceptions import ResourceNotFound  # noqa: PLC0415

        try:
            return self._reports[code]
        except KeyError as e:
            msg = f"Unknown report code: {code!r}"
            raise ResourceNotFound(msg) from e

    def all(self) -> list[ReportDefinition]:
        return list(self._reports.values())

    def allowed_for(self, user) -> list[ReportDefinition]:
        """Filter to definitions whose `permission_codename` the user holds."""
        return [
            d
            for d in self._reports.values()
            if not d.permission_codename or user.has_perm(d.permission_codename)
        ]


registry = ReportRegistry()
