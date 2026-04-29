"""
Conftest for integration tests.
Re-exports fixtures from pms_api.conftest for use in tests/ directory.
"""

# Import all fixtures from the main conftest
from pms_api.conftest import admin_client
from pms_api.conftest import api_client
from pms_api.conftest import authenticated_client
from pms_api.conftest import department
from pms_api.conftest import group_with_permissions
from pms_api.conftest import location
from pms_api.conftest import project_type
from pms_api.conftest import staff_client
from pms_api.conftest import staff_user
from pms_api.conftest import superuser
from pms_api.conftest import user

# Re-export fixtures so they're available in tests/ directory
__all__ = [
    "admin_client",
    "api_client",
    "authenticated_client",
    "department",
    "group_with_permissions",
    "location",
    "project_type",
    "staff_client",
    "staff_user",
    "superuser",
    "user",
]
