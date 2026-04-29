"""
Tests for User API endpoints.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

from pms_api.accounts.tests.factories import GroupFactory
from pms_api.accounts.tests.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestUserAPI:
    def test_list_users_as_admin(self, admin_client):
        """Test listing users as admin."""
        UserFactory.create_batch(3)
        url = reverse("api:accounts:user-list")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 3

    def test_list_users_as_regular_user_forbidden(self, authenticated_client):
        """Test regular users cannot list users."""
        url = reverse("api:accounts:user-list")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_user_as_admin(self, admin_client):
        """Test creating a user as admin."""
        url = reverse("api:accounts:user-list")
        data = {
            "email": "newuser@example.com",
            "password": "newpass123",
            "confirm_password": "newpass123",
            "first_name": "New",
            "last_name": "User",
        }
        response = admin_client.post(url, data)

        assert response.status_code == status.HTTP_201_CREATED
        assert User.objects.filter(email="newuser@example.com").exists()

    def test_retrieve_user_detail(self, admin_client, user):
        """Test retrieving user detail."""
        url = reverse("api:accounts:user-detail", kwargs={"uuid": user.uuid})
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["email"] == user.email

    def test_update_user(self, admin_client, user):
        """Test updating user information."""
        url = reverse("api:accounts:user-detail", kwargs={"uuid": user.uuid})
        data = {"first_name": "Updated"}
        response = admin_client.patch(url, data)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.first_name == "Updated"

    def test_activate_user(self, admin_client, user):
        """Test activating a user."""
        user.is_active = False
        user.save()

        url = reverse("api:accounts:user-activate", kwargs={"uuid": user.uuid})
        response = admin_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_active is True

    def test_deactivate_user(self, admin_client, user):
        """Test deactivating a user."""
        url = reverse("api:accounts:user-deactivate", kwargs={"uuid": user.uuid})
        response = admin_client.post(url)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_active is False

    def test_cannot_deactivate_self(self, admin_client, superuser):
        """Test admin cannot deactivate their own account."""
        url = reverse("api:accounts:user-deactivate", kwargs={"uuid": superuser.uuid})
        response = admin_client.post(url)

        # DRF returns 422 for business rule violations
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_assign_groups_to_user(self, admin_client, user):
        """Test assigning groups to a user."""
        group1 = GroupFactory()
        group2 = GroupFactory()

        url = reverse("api:accounts:user-assign-groups", kwargs={"uuid": user.uuid})
        data = {"group_ids": [group1.id, group2.id]}
        response = admin_client.post(url, data, format="json")

        assert response.status_code == status.HTTP_200_OK
        assert user.groups.count() == 2

    def test_soft_delete_user(self, admin_client, user):
        """Test soft deleting a user."""
        url = reverse("api:accounts:user-detail", kwargs={"uuid": user.uuid})
        response = admin_client.delete(url)

        assert response.status_code == status.HTTP_200_OK
        user.refresh_from_db()
        assert user.is_deleted is True

    def test_user_stats(self, admin_client):
        """Test user statistics endpoint."""
        UserFactory.create_batch(5)
        url = reverse("api:accounts:user-stats")
        response = admin_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert "total" in response.data["data"]
        assert "active" in response.data["data"]
