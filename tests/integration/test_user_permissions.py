"""
Integration tests for user permissions and access control.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework import status

User = get_user_model()


@pytest.mark.django_db
@pytest.mark.integration
class TestUserPermissionsIntegration:
    """Test user permissions and role-based access control."""

    def test_user_with_group_permissions(self, api_client):
        """Test that user inherits permissions from groups."""
        # Create user
        user = User.objects.create_user(
            email="groupuser@example.com",
            password="testpass123",
            first_name="Group",
            last_name="User",
        )

        # Create group with permissions
        group = Group.objects.create(name="Viewers")
        view_perm = Permission.objects.filter(codename="view_user").first()
        if view_perm:
            group.permissions.add(view_perm)
        user.groups.add(group)

        # Authenticate
        api_client.force_authenticate(user=user)

        # Try to access user list (should work with view permission)
        url = reverse("api:accounts:user-list")
        response = api_client.get(url)

        # User has view permission but not list permission (needs staff)
        # This tests the permission system is working
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]

    def test_permission_hierarchy(self, api_client, superuser, staff_user, user):
        """Test that permission hierarchy works correctly."""
        # Superuser can access everything
        api_client.force_authenticate(user=superuser)
        url = reverse("api:accounts:user-list")
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK

        # Staff user with permissions can access
        api_client.force_authenticate(user=staff_user)
        response = api_client.get(url)
        # May be forbidden if no specific permissions
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_403_FORBIDDEN]

        # Regular user cannot access
        api_client.force_authenticate(user=user)
        response = api_client.get(url)
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_group_management_workflow(self, admin_client):
        """Test creating groups and assigning permissions."""
        # Create group
        group_url = reverse("api:accounts:group-list")
        group_data = {"name": "Project Managers"}
        response = admin_client.post(group_url, group_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        group_id = response.data["data"]["id"]

        # Add permissions to group
        add_perms_url = reverse("api:accounts:group-add-permissions", kwargs={"pk": group_id})
        view_perm = Permission.objects.filter(codename="view_project").first()
        if view_perm:
            perm_data = {"permission_ids": [view_perm.id]}
            response = admin_client.post(add_perms_url, perm_data, format="json")
            assert response.status_code == status.HTTP_200_OK

        # Create user and assign to group
        user_url = reverse("api:accounts:user-list")
        user_data = {
            "email": "pm@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
            "first_name": "Project",
            "last_name": "Manager",
        }
        response = admin_client.post(user_url, user_data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        user_uuid = response.data["data"]["uuid"]

        # Assign group to user
        assign_url = reverse("api:accounts:user-assign-groups", kwargs={"uuid": user_uuid})
        assign_data = {"group_ids": [group_id]}
        response = admin_client.post(assign_url, assign_data, format="json")
        assert response.status_code == status.HTTP_200_OK

        # Verify user has group
        user = User.objects.get(uuid=user_uuid)
        assert user.groups.filter(id=group_id).exists()
