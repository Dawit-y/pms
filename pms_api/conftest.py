"""
Root conftest for pytest.
Provides shared fixtures for all test modules.
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from rest_framework.test import APIClient

from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.lookups.models import Lookup
from pms_api.lookups.models import LookupType

User = get_user_model()


@pytest.fixture
def api_client():
    """Unauthenticated API client."""
    return APIClient()


@pytest.fixture
def user(db):
    """Regular user without special permissions."""
    return User.objects.create_user(
        email="user@example.com",
        password="testpass123",
        first_name="Test",
        last_name="User",
    )


@pytest.fixture
def staff_user(db):
    """Staff user with basic staff access."""
    return User.objects.create_user(
        email="staff@example.com",
        password="testpass123",
        first_name="Staff",
        last_name="User",
        is_staff=True,
    )


@pytest.fixture
def superuser(db):
    """Superuser with all permissions."""
    return User.objects.create_superuser(
        email="admin@example.com",
        password="testpass123",
        first_name="Admin",
        last_name="User",
    )


@pytest.fixture
def authenticated_client(api_client, user):
    """API client authenticated as regular user."""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def staff_client(api_client, staff_user):
    """API client authenticated as staff user."""
    api_client.force_authenticate(user=staff_user)
    return api_client


@pytest.fixture
def admin_client(api_client, superuser):
    """API client authenticated as superuser."""
    api_client.force_authenticate(user=superuser)
    return api_client


@pytest.fixture
def group_with_permissions(db):
    """Create a group with some permissions."""
    group = Group.objects.create(name="Test Group")
    # Add view user permission
    perm = Permission.objects.filter(codename="view_user").first()
    if perm:
        group.permissions.add(perm)
    return group


# Project-related fixtures
@pytest.fixture
def project_type(db):
    """Create a project type lookup."""
    lookup_type, _ = LookupType.objects.get_or_create(
        code="project_type",
        name_en="Project Type",
    )
    project_type_lookup, _ = Lookup.objects.get_or_create(
        lookup_type=lookup_type,
        code="road",
        name_en="Road Construction",
    )
    return project_type_lookup


@pytest.fixture
def document_type(db):
    """Create a document type lookup."""
    lookup_type, _ = LookupType.objects.get_or_create(
        code="document_type",
        name_en="Document Type",
    )
    document_type_lookup, _ = Lookup.objects.get_or_create(
        lookup_type=lookup_type,
        code="pdf",
        name_en="PDF",
    )
    return document_type_lookup


@pytest.fixture
def location(db):
    """Create a location."""
    location, _ = Location.objects.get_or_create(
        code="AA",
        name_en="Addis Ababa",
        location_type="city",
    )
    return location


@pytest.fixture
def department(db):
    """Create a department."""
    dept, _ = Department.objects.get_or_create(
        code="DEPT001",
        name_en="Engineering Department",
    )
    return dept
