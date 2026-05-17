"""
Register the daily report-cleanup periodic task so Celery Beat picks it up.
Idempotent — re-runnable.
"""

from django.db import migrations


def create_cleanup_periodic_task(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")

    schedule, _ = CrontabSchedule.objects.get_or_create(
        minute="0",
        hour="3",
        day_of_week="*",
        day_of_month="*",
        month_of_year="*",
        timezone="Africa/Addis_Ababa",
    )
    PeriodicTask.objects.update_or_create(
        name="reports.cleanup_expired_reports",
        defaults={
            "task": "pms_api.reports.tasks.cleanup_expired_reports",
            "crontab": schedule,
            "enabled": True,
            "description": "Daily cleanup of expired report files and job rows.",
        },
    )


def remove_cleanup_periodic_task(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name="reports.cleanup_expired_reports").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("reports", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_cleanup_periodic_task, remove_cleanup_periodic_task),
    ]
