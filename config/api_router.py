from django.urls import include
from django.urls import path

app_name = "api"
urlpatterns = [
    path("", include("pms_api.accounts.urls")),
]
