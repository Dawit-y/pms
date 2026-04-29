"""
Tests for custom permissions.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from rest_framework.test import APIRequestFactory

from pms_api.core.permissions import IsSuperAdmin
from pms_api.core.permissions import permission_required

User = get_user_model()


@pytest.mark.django_db
class TestIsSuperAdmin:
    def test_superuser_has_permission(self, superuser):
        """Test that superuser has permission."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = superuser

        permission = IsSuperAdmin()
        assert permission.has_permission(request, None) is True

    def test_regular_user_no_permission(self, user):
        """Test that regular user doesn't have permission."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user

        permission = IsSuperAdmin()
        assert permission.has_permission(request, None) is False

    def test_staff_user_no_permission(self, staff_user):
        """Test that staff user without superuser doesn't have permission."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = staff_user

        permission = IsSuperAdmin()
        assert permission.has_permission(request, None) is False


@pytest.mark.django_db
class TestPermissionRequired:
    def test_user_with_permission(self, user):
        """Test user with specific permission."""
        # Add permission to user
        perm = Permission.objects.filter(codename="view_user").first()
        if perm:
            user.user_permissions.add(perm)

        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user

        permission_class = permission_required("accounts.view_user")
        permission = permission_class()
        assert permission.has_permission(request, None) is True

    def test_user_without_permission(self, user):
        """Test user without specific permission."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = user

        permission_class = permission_required("accounts.delete_user")
        permission = permission_class()
        assert permission.has_permission(request, None) is False

    def test_superuser_has_all_permissions(self, superuser):
        """Test that superuser has all permissions."""
        factory = APIRequestFactory()
        request = factory.get("/")
        request.user = superuser

        permission_class = permission_required("accounts.delete_user")
        permission = permission_class()
        assert permission.has_permission(request, None) is True
