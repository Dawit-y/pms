import logging
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter
from drf_spectacular.utils import extend_schema
from rest_framework import filters
from rest_framework import status
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAdminUser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.views import TokenRefreshView

from pms_api.core.exceptions import BusinessRuleViolation
from pms_api.core.exceptions import ResourceNotFound
from pms_api.core.models.access_log import AccessLog
from pms_api.core.pagination import StandardPagination
from pms_api.core.pagination import success_response
from pms_api.core.permissions import IsSuperAdmin
from pms_api.core.permissions import permission_required
from pms_api.core.throttling import AuthRateThrottle
from pms_api.core.views import BaseModelViewSet
from pms_api.core.views import BaseReadOnlyViewSet

from .serializers import AccessLogSerializer
from .serializers import AdminSetPasswordSerializer
from .serializers import ChangePasswordSerializer
from .serializers import ContentTypeSerializer
from .serializers import CustomTokenObtainPairSerializer
from .serializers import GroupSerializer
from .serializers import PermissionSerializer
from .serializers import UserCreateSerializer
from .serializers import UserDetailSerializer
from .serializers import UserListSerializer
from .serializers import UserSelfSerializer
from .serializers import UserUpdateSerializer

User = get_user_model()
logger = logging.getLogger(__name__)


# ─── Auth views ───────────────────────────────────────────────────────────────


@method_decorator(csrf_exempt, name="dispatch")
class CustomTokenObtainPairView(TokenObtainPairView):
    """
    Custom login view that returns user data and permissions along with tokens.
    Sets refresh token in HTTP-only cookie for security.
    Rate limited to prevent brute force attacks.
    """

    serializer_class = CustomTokenObtainPairSerializer
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Login - Obtain access token",
        description=(
            "Authenticate with email and password. Returns access "
            "token in response body and refresh token in HTTP-only cookie."
        ),
        request=CustomTokenObtainPairSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "access": {"type": "string", "description": "JWT access token"},
                    "user": {"type": "object", "description": "User profile data"},
                    "permissions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of user permissions",
                    },
                },
            },
        },
        tags=["Authentication"],
    )
    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)

        if response.status_code == status.HTTP_200_OK:
            user = User.objects.get(email=request.data.get("email"))
            user_data = UserListSerializer(user).data
            all_permissions = user.get_all_permissions()
            permissions_list = list(all_permissions)

            response.data["user"] = user_data
            response.data["permissions"] = permissions_list

            samesite = "Lax" if settings.DEBUG else "None"

            # Set refresh token in HTTP-only cookie
            refresh_token = response.data.pop("refresh", None)
            if refresh_token:
                response.set_cookie(
                    key="refresh_token",
                    value=refresh_token,
                    httponly=True,
                    secure=not settings.DEBUG,
                    samesite=samesite,
                    max_age=7 * 24 * 60 * 60,  # 7 days
                    path="/",
                )
        return response


@method_decorator(csrf_exempt, name="dispatch")
class CustomTokenRefreshView(TokenRefreshView):
    """
    Custom token refresh view that retrieves refresh token from cookie
    and returns updated user data and permissions.
    """

    @extend_schema(
        summary="Refresh access token",
        description=(
            "Refresh the access token using the refresh token stored in "
            "HTTP-only cookie. Returns new access token and updated user data."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {},
                "description": "No body required - refresh token is read from cookie",
            },
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "access": {"type": "string", "description": "New JWT access token"},
                    "user": {"type": "object", "description": "Updated user profile data"},
                    "permissions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of user permissions",
                    },
                },
            },
            401: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string"},
                    "code": {"type": "string"},
                },
            },
        },
        tags=["Authentication"],
    )
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

                response_data["user"] = UserListSerializer(user).data
                response_data["permissions"] = list(user.get_all_permissions())

            except (TokenError, ObjectDoesNotExist):
                return Response(
                    {"detail": "Invalid token user", "code": "token_user_invalid"},
                    status=status.HTTP_401_UNAUTHORIZED,
                )

        response = Response(response_data, status=status.HTTP_200_OK)
        samesite = "Lax" if settings.DEBUG else "None"

        # Handle refresh token rotation
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

    @extend_schema(
        summary="Logout - Invalidate refresh token",
        description="Logout by blacklisting the refresh token and clearing the HTTP-only cookie.",
        request={
            "application/json": {
                "type": "object",
                "properties": {},
                "description": "No body required - refresh token is read from cookie",
            },
        },
        responses={
            200: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string", "example": "Successfully logged out."},
                },
            },
            400: {
                "type": "object",
                "properties": {
                    "detail": {"type": "string", "example": "No active session found."},
                },
            },
        },
        tags=["Authentication"],
    )
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


class MeView(APIView):
    """
    GET   /api/auth/me/   → current user's full profile
    PATCH /api/auth/me/   → update own non-sensitive fields
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user profile",
        description="Retrieve the authenticated user's full profile information.",
        responses={200: UserSelfSerializer},
        tags=["User Profile"],
    )
    def get(self, request):
        serializer = UserSelfSerializer(request.user, context={"request": request})
        return Response(success_response(serializer.data))

    @extend_schema(
        summary="Update current user profile",
        description="Update the authenticated user's profile (non-sensitive fields only).",
        request=UserSelfSerializer,
        responses={200: UserSelfSerializer},
        tags=["User Profile"],
    )
    def patch(self, request):
        serializer = UserSelfSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(success_response(serializer.data, message="Profile updated."))


class ChangePasswordView(APIView):
    """
    POST /api/auth/me/change-password/
    Rate limited to prevent brute force attacks.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [AuthRateThrottle]

    @extend_schema(
        summary="Change password",
        description=(
            "Change the authenticated user's password. Requires current password for verification."
        ),
        request=ChangePasswordSerializer,
        responses={
            200: {
                "type": "object",
                "properties": {
                    "success": {"type": "boolean"},
                    "message": {"type": "string", "example": "Password changed successfully."},
                },
            },
        },
        tags=["User Profile"],
    )
    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        request.user.set_password(ser.validated_data["new_password"])
        request.user.save(update_fields=["password"])
        logger.info("Password changed for user=%s", request.user.id)
        return Response(success_response(message="Password changed successfully."))


# ─── User ViewSet ─────────────────────────────────────────────────────────────


class UserViewSet(BaseModelViewSet):
    """
    Full user lifecycle management for admins.
    All write operations require 'user.manage' permission or staff/superuser.

    Uses Django's built-in Group model for role management.
    """

    lookup_field = "uuid"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = ["is_active", "is_staff", "groups"]
    search_fields = ["email", "first_name", "last_name", "phone"]
    ordering_fields = ["created_at", "email", "first_name", "last_name"]
    ordering = ["-created_at"]

    # Different serializers per action
    serializer_classes = {
        "list": UserListSerializer,
        "retrieve": UserDetailSerializer,
        "create": UserCreateSerializer,
        "update": UserUpdateSerializer,
        "partial_update": UserUpdateSerializer,
    }
    serializer_class = UserDetailSerializer  # fallback

    # Custom action permissions — CRUD is handled by StrictDjangoModelPermissions
    action_permissions = {
        "restore": [IsSuperAdmin],
        "hard_destroy": [IsSuperAdmin],
        "set_password": [permission_required("accounts.manage_user")],
        "activate": [permission_required("accounts.manage_user")],
        "deactivate": [permission_required("accounts.manage_user")],
        "assign_groups": [permission_required("accounts.manage_user")],
        "activity": [permission_required("accounts.view_user")],
        "stats": [permission_required("accounts.view_user")],
    }

    queryset = User.all_objects.all()

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .prefetch_related("groups", "groups__permissions", "user_permissions")
            .order_by("-created_at")
        )

    def _check_delete_allowed(self, instance):
        if instance == self.request.user:
            msg = "You cannot delete your own account."
            raise BusinessRuleViolation(msg)
        if instance.is_superuser and not self.request.user.is_superuser:
            msg = "Only superusers can delete superuser accounts."
            raise BusinessRuleViolation(msg)

    # ── Admin force-reset password ────────────────────────────────────────────

    @extend_schema(
        summary="Admin: force-reset a user's password",
        request=AdminSetPasswordSerializer,
    )
    @action(detail=True, methods=["post"], url_path="set-password")
    def set_password(self, request, *args, **kwargs):
        user = self.get_object()
        ser = AdminSetPasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user.set_password(ser.validated_data["new_password"])
        user.save(update_fields=["password"])
        logger.info("Admin %s reset password for user %s", request.user.id, user.id)
        return Response(success_response(message=f"Password reset for {user.email}."))

    # ── Activate / Deactivate ─────────────────────────────────────────────────

    @extend_schema(summary="Activate a user account")
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, *args, **kwargs):
        user = self.get_object()
        if user.is_active:
            return Response(success_response(message="User is already active."))
        user.is_active = True
        user.updated_by = request.user
        user.save(update_fields=["is_active", "updated_by", "updated_at"])
        return Response(success_response(message=f"{user.email} activated."))

    @extend_schema(summary="Deactivate (suspend) a user account")
    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, *args, **kwargs):
        user = self.get_object()
        if user == request.user:
            msg = "You cannot deactivate your own account."
            raise BusinessRuleViolation(msg)
        if user.is_superuser and not request.user.is_superuser:
            msg = "Cannot deactivate a superuser account."
            raise BusinessRuleViolation(msg)
        user.is_active = False
        user.updated_by = request.user
        user.save(update_fields=["is_active", "updated_by", "updated_at"])
        return Response(success_response(message=f"{user.email} deactivated."))

    # ── Assign groups (replaces assign_role) ──────────────────────────────────

    @extend_schema(
        summary="Assign groups to a user (replaces role assignment)",
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "group_ids": {"type": "array", "items": {"type": "integer"}},
                },
            },
        },
    )
    @action(detail=True, methods=["post"], url_path="assign-groups")
    @transaction.atomic
    def assign_groups(self, request, *args, **kwargs):
        user = self.get_object()
        group_ids = request.data.get("group_ids", [])

        if not isinstance(group_ids, list):
            msg = "group_ids must be a list of group IDs."
            raise BusinessRuleViolation(msg)

        groups = Group.objects.filter(pk__in=group_ids)
        if len(groups) != len(group_ids):
            found_ids = set(groups.values_list("pk", flat=True))
            missing = set(group_ids) - found_ids
            msg = f"Groups with ids={list(missing)} not found."
            raise ResourceNotFound(msg)

        user.groups.set(groups)
        user.updated_by = request.user
        user.save(update_fields=["updated_by", "updated_at"])
        return Response(
            success_response(
                UserDetailSerializer(user, context={"request": request}).data,
                message="Groups assigned successfully.",
            ),
        )

    # ── User activity (access log) ────────────────────────────────────────────

    @extend_schema(
        summary="User's recent API activity (access log)",
        parameters=[
            OpenApiParameter("days", int, description="Last N days, default 30"),
        ],
    )
    @action(detail=True, methods=["get"], url_path="activity")
    def activity(self, request, *args, **kwargs):
        user = self.get_object()
        days = int(request.query_params.get("days", 30))
        since = timezone.now() - timedelta(days=days)

        logs = AccessLog.objects.filter(user=user, timestamp__gte=since).order_by(
            "-timestamp",
        )[:200]
        ser = AccessLogSerializer(logs, many=True)
        return Response(success_response(ser.data))

    # ── Stats ─────────────────────────────────────────────────────────────────

    @extend_schema(summary="User statistics (total, active, by group)")
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request, *args, **kwargs):
        total = User.objects.count()
        active = User.objects.filter(is_active=True).count()
        inactive = total - active
        deleted = User.all_objects.filter(is_deleted=True).count()
        by_group = list(
            User.objects.values("groups__name").annotate(count=Count("id")).order_by("-count"),
        )
        return Response(
            success_response(
                {
                    "total": total,
                    "active": active,
                    "inactive": inactive,
                    "deleted": deleted,
                    "by_group": by_group,
                },
            ),
        )


# ─── Permission ViewSet (read-only) ───────────────────────────────────────────


class PermissionViewSet(BaseReadOnlyViewSet):
    """
    Read-only ViewSet for Django's built-in Permission model.

    GET /api/permissions/                          → all permissions (paginated)
    GET /api/permissions/?content_type__app_label=x → filtered by app
    GET /api/permissions/{id}/                      → single permission
    GET /api/permissions/by_app/                    → grouped by app_label
    """

    lookup_field = "pk"
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = {"content_type__app_label": ["exact"]}
    search_fields = ["codename", "name"]

    def get_queryset(self):
        return Permission.objects.select_related("content_type").order_by(
            "content_type__app_label",
            "codename",
        )

    def get_serializer_class(self):
        return PermissionSerializer

    def retrieve(self, request, *args, **kwargs):
        pk = self.kwargs.get("pk")
        try:
            perm = Permission.objects.select_related("content_type").get(pk=pk)
        except (Permission.DoesNotExist, ValueError) as err:
            raise ResourceNotFound from err
        return Response(success_response(PermissionSerializer(perm).data))

    @extend_schema(summary="Permissions grouped by app label")
    @action(detail=False, methods=["get"], url_path="by_app")
    def by_app(self, request, *args, **kwargs):
        """Return permissions grouped by content_type.app_label."""
        permissions = self.get_queryset()
        grouped = {}
        for perm in permissions:
            app = perm.content_type.app_label
            if app not in grouped:
                grouped[app] = []
            grouped[app].append(PermissionSerializer(perm).data)
        return Response(success_response(grouped))


# ─── Group ViewSet (CRUD) ─────────────────────────────────────────────────────


class GroupViewSet(viewsets.ModelViewSet):
    """
    Full CRUD ViewSet for Django's built-in Group model (used as Roles).

    Django's Group model does NOT have uuid, soft-delete, or audit fields,
    so we inherit from ModelViewSet directly instead of BaseModelViewSet.
    """

    queryset = Group.objects.all().prefetch_related("permissions")
    serializer_class = GroupSerializer
    pagination_class = StandardPagination
    permission_classes = [IsAuthenticated, IsAdminUser]
    lookup_field = "pk"
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_fields = {
        "name": ["exact", "icontains"],
    }
    search_fields = ["name"]
    ordering_fields = ["id", "name"]
    ordering = ["name"]

    def list(self, request, *args, **kwargs):
        qs = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(qs)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(qs, many=True)
        return Response(success_response(serializer.data))

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return Response(success_response(serializer.data))

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            success_response(serializer.data, message="Group created successfully."),
            status=status.HTTP_201_CREATED,
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            success_response(serializer.data, message="Group updated successfully."),
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        instance.delete()
        return Response(
            success_response(message="Group deleted successfully."),
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get"])
    def users(self, request, pk=None):
        """Get all users in this group."""
        group = self.get_object()
        users = group.user_set.all()

        serializer = UserListSerializer(users, many=True)
        return Response(success_response(serializer.data))

    @action(detail=True, methods=["post"])
    def add_permissions(self, request, pk=None):
        """
        Add permissions to a group.

        Body: {"permission_ids": [1, 2, 3]}
        """
        group = self.get_object()
        permission_ids = request.data.get("permission_ids", [])

        permissions = Permission.objects.filter(id__in=permission_ids)
        group.permissions.add(*permissions)

        serializer = self.get_serializer(group)
        return Response(success_response(serializer.data, message="Permissions added."))

    @action(detail=True, methods=["post"])
    def remove_permissions(self, request, pk=None):
        """
        Remove permissions from a group.

        Body: {"permission_ids": [1, 2, 3]}
        """
        group = self.get_object()
        permission_ids = request.data.get("permission_ids", [])

        permissions = Permission.objects.filter(id__in=permission_ids)
        group.permissions.remove(*permissions)

        serializer = self.get_serializer(group)
        return Response(
            success_response(serializer.data, message="Permissions removed."),
        )


class ContentTypeViewSet(BaseReadOnlyViewSet):
    """
    ViewSet for viewing ContentTypes (reference for understanding permissions).
    """

    queryset = ContentType.objects.all()
    serializer_class = ContentTypeSerializer
    permission_classes = [IsAuthenticated, IsAdminUser]
    lookup_field = "pk"
    filterset_fields = {
        "app_label": ["exact"],
        "model": ["exact", "icontains"],
    }
    search_fields = ["app_label", "model"]
    ordering_fields = ["id", "app_label", "model"]
    ordering = ["app_label", "model"]
