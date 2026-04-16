from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import Permission
from .models import Role
from .models import User


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "codename", "name", "module"]


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
        token["user_id"] = str(user.uuid)
        token["full_name"] = f"{user.first_name} {user.last_name}"
        return token

    def validate(self, attrs):
        data = super().validate(attrs)
        # Also return permissions in the HTTP response body for convenience
        data["permissions"] = self.user.get_permissions()
        data["role"] = self.user.role.name if self.user.role else None
        return data


class UserSerializer(serializers.ModelSerializer):
    permissions = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role.name", read_only=True)

    class Meta:
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
            "department",
            "permissions",
            "created_at",
        ]
        read_only_fields = ["uuid", "created_at", "permissions"]

    def get_permissions(self, obj):
        return obj.get_permissions()
