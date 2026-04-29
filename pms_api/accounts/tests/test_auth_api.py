"""
Tests for authentication API endpoints.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status

User = get_user_model()


@pytest.mark.django_db
class TestAuthenticationAPI:
    def test_login_success(self, api_client, user):
        """Test successful login returns tokens and user data."""
        url = reverse("api:accounts:login")
        data = {
            "email": "user@example.com",
            "password": "testpass123",
        }
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK
        assert "access" in response.data
        assert "user" in response.data
        assert "permissions" in response.data
        assert response.data["user"]["email"] == "user@example.com"

    def test_login_invalid_credentials(self, api_client, user):
        """Test login with invalid credentials fails."""
        url = reverse("api:accounts:login")
        data = {
            "email": "user@example.com",
            "password": "wrongpassword",
        }
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_login_inactive_user(self, api_client, user):
        """Test login with inactive user fails."""
        user.is_active = False
        user.save()

        url = reverse("api:accounts:login")
        data = {
            "email": "user@example.com",
            "password": "testpass123",
        }
        response = api_client.post(url, data)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_me_endpoint_authenticated(self, authenticated_client, user):
        """Test /me endpoint returns current user data."""
        url = reverse("api:accounts:me")
        response = authenticated_client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["email"] == user.email

    def test_me_endpoint_unauthenticated(self, api_client):
        """Test /me endpoint requires authentication."""
        url = reverse("api:accounts:me")
        response = api_client.get(url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_change_password_success(self, authenticated_client, user):
        """Test changing password with valid data."""
        url = reverse("api:accounts:change-password")
        data = {
            "old_password": "testpass123",
            "new_password": "newpass456",
            "confirm_password": "newpass456",
        }
        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_200_OK

        # Verify password was changed
        user.refresh_from_db()
        assert user.check_password("newpass456")

    def test_change_password_wrong_old_password(self, authenticated_client):
        """Test changing password with wrong old password fails."""
        url = reverse("api:accounts:change-password")
        data = {
            "old_password": "wrongpass",
            "new_password": "newpass456",
        }
        response = authenticated_client.post(url, data)

        assert response.status_code == status.HTTP_400_BAD_REQUEST
