from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from djoser.serializers import UserCreateSerializer as BaseUserCreateSerializer
from djoser.serializers import UserSerializer as BaseUserSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class UserCreateSerializer(BaseUserCreateSerializer):
    class Meta(BaseUserCreateSerializer.Meta):
        fields = [
            "id",
            "password",
            "email",
            "first_name",
            "last_name",
            "phone",
            "is_staff",
        ]


class UserSerializer(BaseUserSerializer):
    class Meta(BaseUserSerializer.Meta):
        fields = ["id", "uuid", "email", "first_name", "last_name", "phone"]
        ref_name = "user_serializer"


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["email"] = user.email
        return token


class ContentTypeSerializer(serializers.ModelSerializer):
    """Serializer for ContentType to show app and model info."""

    class Meta:
        model = ContentType
        fields = ["id", "app_label", "model"]


class PermissionSerializer(serializers.ModelSerializer):
    """Serializer for Django's Permission model."""

    content_type = ContentTypeSerializer(read_only=True)
    content_type_id = serializers.PrimaryKeyRelatedField(
        queryset=ContentType.objects.all(),
        source="content_type",
        write_only=True,
        required=False,
    )

    class Meta:
        model = Permission
        fields = [
            "id",
            "name",
            "codename",
            "content_type",
            "content_type_id",
        ]
        read_only_fields = ["id"]


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

    def get_user_count(self, obj):
        return obj.user_set.count()
