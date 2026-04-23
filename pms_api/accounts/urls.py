from django.conf import settings
from django.urls import path
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from .views import ContentTypeViewSet
from .views import CustomTokenLogoutView
from .views import CustomTokenObtainPairView
from .views import CustomTokenRefreshView
from .views import GroupViewSet
from .views import PermissionViewSet
from .views import UserViewSet

app_name = "accounts"

router = DefaultRouter() if settings.DEBUG else SimpleRouter()

router.register("permissions", PermissionViewSet, basename="permission")
router.register("groups", GroupViewSet, basename="group")
router.register("content-types", ContentTypeViewSet, basename="content-type")

# Users endpoints
user_list = UserViewSet.as_view(
    {
        "get": "list",
        "post": "create",
    },
)

user_detail = UserViewSet.as_view(
    {
        "get": "retrieve",
        "put": "update",
        "patch": "partial_update",
        "delete": "destroy",
    },
)

user_me = UserViewSet.as_view(
    {
        "get": "me",
        "put": "me",
        "patch": "me",
    },
)

urlpatterns = [
    path("login/", CustomTokenObtainPairView.as_view(), name="login"),
    path("refresh/", CustomTokenRefreshView.as_view(), name="jwt-refresh"),
    path("logout/", CustomTokenLogoutView.as_view(), name="logout"),
    path("users/", user_list, name="user-list"),
    path("users/<int:id>/", user_detail, name="user-detail"),
    path("users/me/", user_me, name="user-me"),
]

urlpatterns += router.urls
