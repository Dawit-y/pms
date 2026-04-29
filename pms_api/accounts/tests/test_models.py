"""
Tests for accounts models.
"""

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from pms_api.accounts.exceptions import UserEmailRequiredException

User = get_user_model()


@pytest.mark.django_db
class TestUserModel:
    def test_create_user_success(self):
        """Test creating a user with valid data."""
        user = User.objects.create_user(
            email="test@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User",
        )
        assert user.email == "test@example.com"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.check_password("testpass123")
        assert user.is_active is True
        assert user.is_staff is False
        assert user.is_superuser is False

    def test_create_user_without_email_fails(self):
        """Test creating user without email raises exception."""
        with pytest.raises(UserEmailRequiredException):
            User.objects.create_user(
                email="",
                password="testpass123",
            )

    def test_create_superuser(self):
        """Test creating a superuser."""
        user = User.objects.create_superuser(
            email="admin@example.com",
            password="adminpass123",
            first_name="Admin",
            last_name="User",
        )
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_email_uniqueness(self):
        """Test that email must be unique."""
        User.objects.create_user(
            email="test@example.com",
            password="pass123",
        )
        with pytest.raises(IntegrityError):
            User.objects.create_user(
                email="test@example.com",
                password="pass456",
            )

    def test_get_full_name(self):
        """Test get_full_name method."""
        user = User.objects.create_user(
            email="test@example.com",
            password="pass123",
            first_name="John",
            last_name="Doe",
        )
        assert user.get_full_name() == "John Doe"

    def test_get_short_name(self):
        """Test get_short_name method."""
        user = User.objects.create_user(
            email="test@example.com",
            password="pass123",
            first_name="John",
            last_name="Doe",
        )
        assert user.get_short_name() == "John"

    def test_soft_delete_filtering(self):
        """Test that soft-deleted users are filtered by default."""
        user = User.objects.create_user(
            email="test@example.com",
            password="pass123",
        )
        user_id = user.id

        # Soft delete
        user.is_deleted = True
        user.save()

        # Should not appear in default queryset
        assert not User.objects.filter(id=user_id).exists()

        # Should appear in all_objects
        assert User.all_objects.filter(id=user_id).exists()
