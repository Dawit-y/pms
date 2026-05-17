from django.urls import include
from django.urls import path

app_name = "api"
urlpatterns = [
    path("", include("pms_api.core.urls")),
    path("", include("pms_api.accounts.urls")),
    path("", include("pms_api.budget.urls")),
    path("", include("pms_api.projects.urls")),
    path("", include("pms_api.lookups.urls")),
    path("", include("pms_api.project_data.urls")),
    path("", include("pms_api.reports.urls")),
]
