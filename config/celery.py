"""
Celery application entrypoint.

Workers run via:  celery -A config worker -l info -P solo
Beat scheduler:   celery -A config beat -l info
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

app = Celery("pms_api")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
