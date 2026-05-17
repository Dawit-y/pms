"""
Manual entry point for syncing per-report Django Permission rows.

Normally this is wired automatically via `post_migrate`, but the command is
handy after adding a new ReportDefinition without running a migration.
"""

from django.core.management.base import BaseCommand

from pms_api.reports.permissions import sync_report_permissions


class Command(BaseCommand):
    help = "Create Django Permission rows for every registered report's permission_codename."

    def handle(self, *args, **options):
        created, existing = sync_report_permissions(stdout=self.stdout)
        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Created {created} permission(s); {existing} already existed.",
            ),
        )
