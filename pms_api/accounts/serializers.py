from djoser.serializers import UserCreateSerializer as DjoserUserCreateSerializer
from djoser.serializers import UserSerializer as DjoserUserSerializer
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Permission
from .models import Role
from .models import User


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "module", "description"]


class RoleSerializer(serializers.ModelSerializer):
    permissions = PermissionSerializer(many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Permission.objects.all(),
        write_only=True,
        source="permissions",
    )

    class Meta:
        model = Role
        fields = ["id", "uuid", "name", "description", "permissions", "permission_ids"]


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """
    Injects user permissions directly into the JWT payload.
    The frontend decodes the token to know what to show/hide.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["permissions"] = user.get_permissions()
        token["role"] = user.role.name if user.role else None
        token["uuid"] = str(user.uuid)  # Keep UUID in token without breaking 'user_id'
        token["full_name"] = f"{user.first_name} {user.last_name}"
        token["email"] = user.email
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Also return permissions and user info in the HTTP response body
        data["permissions"] = self.user.get_permissions()
        data["role"] = self.user.role.name if self.user.role else None
        data["user"] = {
            "id": self.user.id,
            "uuid": str(self.user.uuid),
            "email": self.user.email,
            "first_name": self.user.first_name,
            "last_name": self.user.last_name,
        }
        return data


class UserSerializer(DjoserUserSerializer):
    """Extended Djoser user serializer with custom fields."""

    permissions = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta(DjoserUserSerializer.Meta):
        model = User
        fields = [
            "id",
            "uuid",
            "email",
            "first_name",
            "last_name",
            "phone",
            "is_active",
            "role",
            "role_name",
            "permissions",
            "created_at",
        ]
        read_only_fields = ["uuid", "created_at", "permissions"]

    def get_permissions(self, obj):
        return obj.get_permissions()


class UserCreateSerializer(DjoserUserCreateSerializer):
    """Custom user creation serializer."""

    class Meta(DjoserUserCreateSerializer.Meta):
        model = User
        fields = [
            "id",
            "email",
            "password",
            "first_name",
            "last_name",
            "phone",
        ]
