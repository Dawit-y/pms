"""
Fixtures for projects tests.
"""

import pytest

from pms_api.lookups.models import Department
from pms_api.lookups.models import Location
from pms_api.lookups.models import Lookup
from pms_api.lookups.models import LookupType


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
