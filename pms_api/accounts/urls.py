from django.urls import include
from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import CustomTokenLogoutView
from .views import CustomTokenObtainPairView
from .views import CustomTokenRefreshView
from .views import UserViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")

app_name = "accounts"

urlpatterns = [
    # Custom JWT endpoints with cookie handling
    path("login/", CustomTokenObtainPairView.as_view(), name="login"),
    path("refresh/", CustomTokenRefreshView.as_view(), name="jwt-refresh"),
    path("logout/", CustomTokenLogoutView.as_view(), name="logout"),
    # Djoser endpoints (registration, password reset, etc.)
    path("", include("djoser.urls")),
    # User management endpoints
    path("", include(router.urls)),
]
