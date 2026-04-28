from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from .views import DepartmentViewSet
from .views import LocationViewSet
from .views import LookupTypeViewSet
from .views import LookupViewSet

app_name = "lookups"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("lookup_types", LookupTypeViewSet, basename="lookup-type")
router.register("lookups", LookupViewSet, basename="lookup")
router.register("locations", LocationViewSet, basename="location")
router.register("departments", DepartmentViewSet, basename="department")

urlpatterns = [path("", include(router.urls))]
