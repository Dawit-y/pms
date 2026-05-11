from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import AccessLogViewSet
from .views import NotificationViewSet

router = DefaultRouter()
router.register("notifications", NotificationViewSet, basename="notification")
router.register("access-logs", AccessLogViewSet, basename="access-log")

urlpatterns = [path("", include(router.urls))]
