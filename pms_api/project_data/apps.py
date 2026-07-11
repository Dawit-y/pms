from django.apps import AppConfig


class ProjectDataConfig(AppConfig):
    name = "pms_api.project_data"

    def ready(self):
        from . import signals  # noqa: F401, PLC0415
