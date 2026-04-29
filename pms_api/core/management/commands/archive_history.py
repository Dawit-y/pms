"""
Management command to archive old history records.

WHAT IS ARCHIVING?
==================
Archiving moves old historical data out of the active database to:
1. Reduce database size (history tables grow continuously)
2. Improve query performance (smaller tables = faster queries)
3. Maintain compliance (keep audit trails in cold storage)
4. Manage costs (archive to cheaper storage like S3)

WHAT THIS COMMAND DOES:
=======================
- Finds history records older than X days (default 365)
- Can target specific models or all models with history
- Supports dry-run mode to preview what would be archived
- Can export to JSON file before deletion
- Can permanently delete old history (use with caution)

USAGE EXAMPLES:
===============
# Preview what would be archived (safe, no changes)
python manage.py archive_history --days=365 --dry-run

# Export to JSON and delete (recommended)
python manage.py archive_history --days=730 --export --delete

# Export only (no deletion)
python manage.py archive_history --days=365 --export

# Delete without export (use with caution!)
python manage.py archive_history --days=365 --delete

# Target specific model
python manage.py archive_history --days=365 --model=projects.Project --export --delete

# Custom export directory
python manage.py archive_history --days=365 --export --export-dir=/backups/history/
"""

import json
from datetime import timedelta
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Archive old history records to reduce database size"

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=365,
            help="Archive history older than N days (default: 365)",
        )
        parser.add_argument(
            "--model",
            type=str,
            help="Specific model to archive (e.g., 'projects.Project')",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be archived without actually doing it",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help="Delete old history after archiving (use with caution)",
        )
        parser.add_argument(
            "--export",
            action="store_true",
            help="Export history to JSON files before deletion",
        )
        parser.add_argument(
            "--export-dir",
            type=str,
            default="./history_archives",
            help="Directory to export history files (default: ./history_archives)",
        )

    def handle(self, *args, **options):
        days = options["days"]
        model_name = options["model"]
        dry_run = options["dry_run"]
        delete_mode = options["delete"]
        export_mode = options["export"]
        export_dir = options["export_dir"]

        cutoff_date = timezone.now() - timedelta(days=days)

        self.stdout.write(
            self.style.WARNING(
                f"\n{'=' * 70}\n"
                f"{'[DRY RUN] ' if dry_run else ''}HISTORY ARCHIVING\n"
                f"{'=' * 70}\n"
                f"Cutoff Date: {cutoff_date.date()} ({days} days ago)\n"
                f"Export: {'Yes' if export_mode else 'No'}\n"
                f"Delete: {'Yes' if delete_mode else 'No'}\n"
                f"Export Directory: {export_dir if export_mode else 'N/A'}\n"
                f"{'=' * 70}\n",
            ),
        )

        if model_name:
            models_to_process = [self._get_model(model_name)]
        else:
            models_to_process = self._get_all_history_models()

        if export_mode and not dry_run:
            export_path = Path(export_dir)
            export_path.mkdir(parents=True, exist_ok=True)
            self.stdout.write(
                self.style.SUCCESS(f"Export directory created: {export_path}\n"),
            )

        total_archived = 0
        total_exported = 0

        for model in models_to_process:
            if not hasattr(model, "history"):
                continue

            archived, exported = self._archive_model_history(
                model,
                cutoff_date,
                dry_run,
                delete_mode,
                export_mode,
                export_dir,
            )
            total_archived += archived
            total_exported += exported

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{'=' * 70}\n"
                f"SUMMARY\n"
                f"{'=' * 70}\n"
                f"{'[DRY RUN] ' if dry_run else ''}"
                f"Total records: {total_archived}\n"
                f"Exported: {total_exported if export_mode else 'N/A'}\n"
                f"Deleted: {total_archived if delete_mode and not dry_run else '0'}\n"
                f"{'=' * 70}\n",
            ),
        )

    def _get_model(self, model_path):
        """Get model from string like 'projects.Project'."""
        try:
            app_label, model_name = model_path.split(".")
            return apps.get_model(app_label, model_name)
        except (ValueError, LookupError) as err:
            self.stdout.write(
                self.style.ERROR(f"Model '{model_path}' not found: {err}"),
            )
            raise

    def _get_all_history_models(self):
        """Get all models that have history tracking enabled."""
        return [model for model in apps.get_models() if hasattr(model, "history")]

    def _archive_model_history(  # noqa: PLR0913
        self,
        model,
        cutoff_date,
        dry_run,
        delete_mode,
        export_mode,
        export_dir,
    ):
        """Archive history for a specific model."""
        model_name = f"{model._meta.app_label}.{model._meta.model_name}"  # noqa: SLF001
        history_model = model.history.model

        old_records = history_model.objects.filter(history_date__lt=cutoff_date)
        count = old_records.count()

        if count == 0:
            self.stdout.write(f"  {model_name}: No old history to archive")
            return 0, 0

        self.stdout.write(
            self.style.WARNING(
                f"\n  {model_name}: Found {count} old history records",
            ),
        )

        exported_count = 0

        if not dry_run:
            # Export to JSON if requested
            if export_mode:
                exported_count = self._export_history(
                    model_name,
                    old_records,
                    export_dir,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"    ✓ Exported {exported_count} records to JSON",
                    ),
                )

            # Delete if requested
            if delete_mode:
                if not export_mode:
                    self.stdout.write(
                        self.style.WARNING(
                            "    ⚠ Deleting without export! Data will be lost.",
                        ),
                    )
                old_records.delete()
                self.stdout.write(
                    self.style.SUCCESS(f"    ✓ Deleted {count} records"),
                )
            elif not export_mode:
                self.stdout.write(
                    self.style.WARNING(
                        "    (i) No action taken. Use --export or --delete",
                    ),
                )

        return count, exported_count

    def _export_history(self, model_name, queryset, export_dir):
        """Export history records to JSON file."""
        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{model_name.replace('.', '_')}_history_{timestamp}.json"
        filepath = Path(export_dir) / filename

        # Serialize to JSON
        data = []
        for record in queryset:
            record_data = {
                "history_id": record.history_id,
                "history_date": record.history_date.isoformat(),
                "history_type": record.history_type,
                "history_user_id": record.history_user_id,
                "history_change_reason": getattr(
                    record,
                    "history_change_reason",
                    None,
                ),
            }

            # Add all model fields
            for field in record._meta.fields:  # noqa: SLF001
                if field.name not in record_data and not field.name.startswith(
                    "history_",
                ):
                    value = getattr(record, field.name, None)
                    # Convert to JSON-serializable format
                    if hasattr(value, "isoformat"):  # datetime/date
                        value = value.isoformat()
                    elif hasattr(value, "pk"):  # Foreign key
                        value = value.pk
                    record_data[field.name] = value

            data.append(record_data)

        # Write to file
        with filepath.open("w") as f:
            json.dump(data, f, indent=2, default=str)

        return len(data)
