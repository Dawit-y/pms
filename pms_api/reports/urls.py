from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from .views import ReportJobViewSet
from .views import ReportViewSet

app_name = "reports"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()
router.register("reports/jobs", ReportJobViewSet, basename="reportjob")
router.register("reports", ReportViewSet, basename="report")

urlpatterns = [path("", include(router.urls))]
