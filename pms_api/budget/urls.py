from django.conf import settings
from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from .views import BudgetRequestViewSet

app_name = "budget"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("requests", BudgetRequestViewSet, basename="budget-request")

urlpatterns = [path("", include(router.urls))]
