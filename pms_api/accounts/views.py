import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from djoser.views import UserViewSet as DjoserUserViewSet
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

from .serializers import ContentTypeSerializer
from .serializers import CustomTokenObtainPairSerializer
from .serializers import GroupSerializer
from .serializers import PermissionSerializer
from .serializers import UserSerializer

logger = logging.getLogger(__name__)
User = get_user_model()


@method_decorator(csrf_exempt, name="dispatch")
class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            user = User.objects.get(email=request.data.get("email"))

            user_data = UserSerializer(user).data

            all_permissions = user.get_all_permissions()
            permissions_list = list(all_permissions)

            response.data["user"] = user_data
            response.data["permissions"] = permissions_list  # <--- HERE
            samesite = "Lax" if settings.DEBUG else "None"
            # Cookie logic (Keep your existing code)
            refresh_token = response.data.pop("refresh", None)
            if refresh_token:
                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=not settings.DEBUG,
                    samesite=samesite,
                    max_age=7 * 24 * 60 * 60,
                    path="/",
                )
        return response


@method_decorator(csrf_exempt, name="dispatch")
class CustomTokenRefreshView(TokenRefreshView):
    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "Refresh token not provided."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = self.get_serializer(data={"refresh": refresh_token})

        try:
            serializer.is_valid(raise_exception=True)
        except ValidationError:
            return Response(
                {"detail": "Token is invalid or expired", "code": "token_not_valid"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        response_data = serializer.validated_data

        access_token = response_data.get("access")

        if access_token:
            try:
                token = AccessToken(access_token)
                user_id = token.payload.get("user_id")

                user = User.objects.get(id=user_id)

                response_data["user"] = UserSerializer(user).data
                response_data["permissions"] = list(user.get_all_permissions())

            except (TokenError, ObjectDoesNotExist):
                return Response(
                    {"detail": "Invalid token user", "code": "token_user_invalid"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        response = Response(response_data, status=status.HTTP_200_OK)
        samesite = "Lax" if settings.DEBUG else "None"
        # Handle Refresh Token Cookie Rotation
        refresh = response_data.pop("refresh", None)
        if refresh:
            response.set_cookie(
                key="refresh_token",
                value=refresh,
                httponly=True,
                secure=not settings.DEBUG,
                samesite=samesite,
                max_age=7 * 24 * 60 * 60,
                path="/",
            )
        return response


class CustomTokenLogoutView(TokenRefreshView):
    """
    Logout view that blacklists the refresh token and clears the cookie.
    """

    def post(self, request, *args, **kwargs):
        refresh_token = request.COOKIES.get("refresh_token")

        if not refresh_token:
            return Response(
                {"detail": "No active session found."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # Blacklist the refresh token
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            logger.warning("Token already invalid")
        except Exception:
            logger.exception("Unexpected error while blacklisting token")

        # Create response and clear cookie
        response = Response(
            {"detail": "Successfully logged out."},
            status=status.HTTP_200_OK,
        )
        response.delete_cookie("refresh_token", path="/")

        return response


class UserViewSet(DjoserUserViewSet):
    """
    Extended Djoser UserViewSet with custom actions.
    """

    @action(detail=False, methods=["get"])
    def me(self, request):
        """Get current user with permissions."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def assign_groups(self, request, pk=None):
        """Assign groups to a user."""
        user = self.get_object()
        group_ids = request.data.get("group_ids", [])

        groups = Group.objects.filter(id__in=group_ids)
        user.groups.set(groups)

        serializer = self.get_serializer(user)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], permission_classes=[IsAdminUser])
    def assign_permissions(self, request, pk=None):
        """Assign direct permissions to a user."""
        user = self.get_object()
        permission_ids = request.data.get("permission_ids", [])

        permissions = Permission.objects.filter(id__in=permission_ids)
        user.user_permissions.set(permissions)

        serializer = self.get_serializer(user)
        return Response(serializer.data)


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing Django permissions (read-only).
    Permissions should be created in code via model Meta or migrations,
    not through the API, as they need corresponding code implementation.
    """

    queryset = Permission.objects.all().select_related("content_type")
    serializer_class = PermissionSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filterset_fields = {
        "codename": ["exact", "icontains"],
        "name": ["exact", "icontains"],
        "content_type__app_label": ["exact"],
        "content_type__model": ["exact"],
    }
    search_fields = ["name", "codename"]
    ordering_fields = ["id", "codename", "name", "content_type__app_label"]
    ordering = ["content_type__app_label", "codename"]

    @action(detail=False, methods=["get"])
    def by_app(self, request):
        """Get permissions grouped by app."""
        permissions = self.filter_queryset(self.get_queryset())
        grouped = {}

        for perm in permissions:
            app_label = perm.content_type.app_label
            if app_label not in grouped:
                grouped[app_label] = []
            grouped[app_label].append(PermissionSerializer(perm).data)

        return Response(grouped)


class GroupViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing Django groups (used as Roles).
    Full CRUD operations for groups and their permissions.
    """

    queryset = Group.objects.all().prefetch_related("permissions")
    serializer_class = GroupSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filterset_fields = {
        "name": ["exact", "icontains"],
    }
    search_fields = ["name"]
    ordering_fields = ["id", "name"]
    ordering = ["name"]

    @action(detail=True, methods=["get"])
    def users(self, request, pk=None):
        """Get all users in this group."""
        group = self.get_object()
        users = group.user_set.all()

        serializer = UserSerializer(users, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def add_permissions(self, request, pk=None):
        """Add permissions to a group."""
        group = self.get_object()
        permission_ids = request.data.get("permission_ids", [])

        permissions = Permission.objects.filter(id__in=permission_ids)
        group.permissions.add(*permissions)

        serializer = self.get_serializer(group)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    def remove_permissions(self, request, pk=None):
        """Remove permissions from a group."""
        group = self.get_object()
        permission_ids = request.data.get("permission_ids", [])

        permissions = Permission.objects.filter(id__in=permission_ids)
        group.permissions.remove(*permissions)

        serializer = self.get_serializer(group)
        return Response(serializer.data)


class ContentTypeViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for viewing ContentTypes (reference for understanding permissions).
    """

    queryset = ContentType.objects.all()
    serializer_class = ContentTypeSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    filterset_fields = {
        "app_label": ["exact"],
        "model": ["exact", "icontains"],
    }
    search_fields = ["app_label", "model"]
    ordering_fields = ["id", "app_label", "model"]
    ordering = ["app_label", "model"]
