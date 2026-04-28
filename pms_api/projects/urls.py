from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from .views import ProjectStatusViewSet
from .views import ProjectViewSet

app_name = "projects"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("projects", ProjectViewSet, basename="project")
router.register("project-statuses", ProjectStatusViewSet, basename="project-status")

urlpatterns = [path("", include(router.urls))]
