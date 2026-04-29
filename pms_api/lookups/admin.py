from django.contrib import admin

from pms_api.core.admin import BaseSoftDeleteAdmin

from .models import Department
from .models import Location
from .models import Lookup
from .models import LookupType


@admin.register(LookupType)
class LookupTypeAdmin(BaseSoftDeleteAdmin):
    """Admin for LookupType with soft-delete support."""

    list_display = ["code", "name_en", "is_active", "created_at"]
    list_filter = ["is_active", "created_at", "is_deleted"]
    search_fields = ["code", "name_en", "name_am", "name_or"]


@admin.register(Lookup)
class LookupAdmin(BaseSoftDeleteAdmin):
    """Admin for Lookup with soft-delete support."""

    list_display = ["code", "name_en", "lookup_type", "sort_order", "is_active"]
    list_filter = ["lookup_type", "is_active", "created_at", "is_deleted"]
    search_fields = ["code", "name_en", "name_am", "name_or"]


@admin.register(Department)
class DepartmentAdmin(BaseSoftDeleteAdmin):
    """Admin for Department with soft-delete support."""

    list_display = ["code", "name_en", "parent", "created_at"]
    list_filter = ["created_at", "is_deleted"]
    search_fields = ["code", "name_en", "name_am", "name_or"]


@admin.register(Location)
class LocationAdmin(BaseSoftDeleteAdmin):
    """Admin for Location with soft-delete support."""

    list_display = ["code", "name_en", "parent", "location_type", "created_at"]
    list_filter = ["location_type", "created_at", "is_deleted"]
    search_fields = ["code", "name_en", "name_am", "name_or"]
