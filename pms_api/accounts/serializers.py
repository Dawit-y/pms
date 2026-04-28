from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.auth.password_validation import validate_password
from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from pms_api.core.serializers import BaseModelSerializer
from pms_api.core.serializers import SoftDeleteSerializer

User = get_user_model()


# ─── Permission ───────────────────────────────────────────────────────────────


class PermissionSerializer(serializers.ModelSerializer):
    app_label = serializers.CharField(source="content_type.app_label", read_only=True)

    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "content_type", "app_label"]


class ContentTypeSerializer(serializers.ModelSerializer):
    """Serializer for ContentType to show app and model info."""

    class Meta:
        model = ContentType
        fields = ["id", "app_label", "model"]


class GroupSerializer(serializers.ModelSerializer):
    """Serializer for Django's Group model (used as Roles)."""

    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.all(),
        source="permissions",
        write_only=True,
        required=False,
    )
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "permissions",
            "permission_ids",
            "user_count",
        ]

    def get_user_count(self, obj) -> int:
        """Get count of users in this group."""
        return obj.user_set.count()


# ─── User list (lightweight) ──────────────────────────────────────────────────


class UserListSerializer(BaseModelSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "uuid",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "is_staff",
            "groups",
            "created_at",
        ]

    def get_full_name(self, obj) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()


# ─── User detail (admin view, full data) ─────────────────────────────────────


class UserDetailSerializer(SoftDeleteSerializer):
    groups = GroupSerializer(many=True, read_only=True)
    permissions = serializers.SerializerMethodField()
    full_name = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            "id",
            "uuid",
            "email",
            "full_name",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "permissions",
            "created_at",
            "updated_at",
            "created_by_email",
            "updated_by_email",
            "is_deleted",
            "deleted_at",
            "deleted_by_email",
            "last_login",
        ]
        read_only_fields = [
            "uuid",
            "created_at",
            "updated_at",
            "last_login",
            "permissions",
            "is_deleted",
            "deleted_at",
        ]

    def get_full_name(self, obj) -> str:
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_permissions(self, obj) -> list[str]:
        return list(obj.get_all_permissions_list())


# ─── User create (admin) ──────────────────────────────────────────────────────


class UserCreateSerializer(BaseModelSerializer):
    password = serializers.CharField(write_only=True, validators=[validate_password])
    confirm_password = serializers.CharField(write_only=True)
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Group.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "email",
            "first_name",
            "last_name",
            "phone",
            "is_staff",
            "is_active",
            "password",
            "confirm_password",
            "group_ids",
        ]

    def validate(self, data):
        if data["password"] != data.pop("confirm_password"):
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."},
            )
        return data

    def create(self, validated_data):
        groups = validated_data.pop("group_ids", [])
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        if groups:
            user.groups.set(groups)
        return user


# ─── User update (admin) ──────────────────────────────────────────────────────


class UserUpdateSerializer(BaseModelSerializer):
    group_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Group.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "phone",
            "is_staff",
            "is_active",
            "group_ids",
        ]

    def update(self, instance, validated_data):
        groups = validated_data.pop("group_ids", None)
        instance = super().update(instance, validated_data)
        if groups is not None:
            instance.groups.set(groups)
        return instance


# ─── User self-update (own profile) ──────────────────────────────────────────


class UserSelfSerializer(BaseModelSerializer):
    """User can update their own non-sensitive profile fields."""

    permissions = serializers.SerializerMethodField()
    groups = GroupSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            "uuid",
            "email",
            "first_name",
            "last_name",
            "phone",
            "groups",
            "permissions",
            "created_at",
            "last_login",
        ]
        read_only_fields = ["uuid", "email", "groups", "created_at", "last_login"]

    def get_permissions(self, obj) -> list[str]:
        return list(obj.get_all_permissions())


# ─── Password management ──────────────────────────────────────────────────────


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."},
            )
        return data

    def validate_old_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            msg = "Current password is incorrect."
            raise serializers.ValidationError(msg)
        return value


class AdminSetPasswordSerializer(serializers.Serializer):
    new_password = serializers.CharField(
        write_only=True,
        validators=[validate_password],
    )
    confirm_password = serializers.CharField(write_only=True)

    def validate(self, data):
        if data["new_password"] != data["confirm_password"]:
            raise serializers.ValidationError(
                {"confirm_password": "Passwords do not match."},
            )
        return data


# ─── JWT with permissions in payload ─────────────────────────────────────────


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        return token


# ─── Access log / activity serializer ────────────────────────────────────────


class AccessLogSerializer(serializers.ModelSerializer):
    user_email = serializers.SerializerMethodField()

    class Meta:
        fields = [
            "id",
            "user",
            "user_email",
            "method",
            "endpoint",
            "ip_address",
            "user_agent",
            "response_status",
            "duration_ms",
            "timestamp",
        ]

    def __init__(self, *args, **kwargs):
        from pms_api.core.models.access_log import AccessLog  # noqa: PLC0415

        self.__class__.Meta.model = AccessLog
        super().__init__(*args, **kwargs)

    def get_user_email(self, obj) -> str | None:
        return obj.user.email if obj.user_id else None
