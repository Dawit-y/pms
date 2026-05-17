from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class ReportsConfig(AppConfig):
    name = "pms_api.reports"
    verbose_name = "Reports"

    def ready(self):
        # Loads every installed app's `reports.py` module if present, so each
        # report self-registers via @registry.register before any HTTP request
        # asks the registry what reports exist.
        autodiscover_modules("reports")

        # Wire up post_migrate so codenames declared via ReportDefinition.permission_codename
        # are created automatically — admins don't need to remember to run a manual
        # `sync_report_permissions` after every migrate.
        from django.db.models.signals import post_migrate  # noqa: PLC0415

        from .permissions import sync_report_permissions_signal  # noqa: PLC0415

        post_migrate.connect(sync_report_permissions_signal, sender=self)
