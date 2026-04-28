from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from .views import ChangePasswordView
from .views import ContentTypeViewSet
from .views import CustomTokenLogoutView
from .views import CustomTokenObtainPairView
from .views import CustomTokenRefreshView
from .views import GroupViewSet
from .views import MeView
from .views import PermissionViewSet
from .views import UserViewSet

app_name = "accounts"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("users", UserViewSet, basename="user")
router.register("permissions", PermissionViewSet, basename="permission")
router.register("groups", GroupViewSet, basename="group")
router.register("content-types", ContentTypeViewSet, basename="content-type")


urlpatterns = [
    path("login/", CustomTokenObtainPairView.as_view(), name="login"),
    path("refresh/", CustomTokenRefreshView.as_view(), name="jwt-refresh"),
    path("logout/", CustomTokenLogoutView.as_view(), name="logout"),
    path("me/", MeView.as_view(), name="me"),
    path("me/change-password/", ChangePasswordView.as_view(), name="change-password"),
]

urlpatterns += router.urls
