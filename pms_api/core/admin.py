"""
Base admin classes with soft-delete handling.

All model admins should inherit from these base classes to get
consistent audit trail display and soft-delete handling.
"""

from django.contrib import admin
from django.utils.html import format_html


class BaseSoftDeleteAdmin(admin.ModelAdmin):
    """
    Base admin class for models with soft-delete.

    Use this for models that inherit from BaseModel.

    Features:
    - Soft-delete awareness (shows deleted records)
    - Audit trail display
    - Auto-set created_by/updated_by
    - Deleted status indicator

    Usage:
        @admin.register(YourModel)
        class YourModelAdmin(BaseSoftDeleteAdmin):
            list_display = ['name', 'created_at']
            # ... your customizations
    """

    # Common readonly fields for audit trail
    readonly_fields = [
        "uuid",
        "created_at",
        "updated_at",
        "created_by",
        "updated_by",
        "deleted_at",
        "deleted_by",
    ]

    # Common list filters
    list_filter = ["created_at", "updated_at", "is_deleted"]

    # Enable date hierarchy
    date_hierarchy = "created_at"

    def get_readonly_fields(self, request, obj=None):
        """Make audit fields readonly."""
        readonly = list(self.readonly_fields)

        # Remove fields that don't exist on this model
        if obj:
            model_fields = {f.name for f in obj._meta.get_fields()}  # noqa: SLF001
            readonly = [f for f in readonly if f in model_fields]

        return readonly

    def get_list_display(self, request):
        """Add soft-delete indicator to list display."""
        list_display = list(super().get_list_display(request))

        # Add deleted indicator if not already there
        if hasattr(self.model, "is_deleted") and "deleted_status" not in list_display:
            list_display.append("deleted_status")

        return list_display

    @admin.display(
        description="Status",
    )
    def deleted_status(self, obj):
        """Display soft-delete status with color coding."""
        if not hasattr(obj, "is_deleted"):
            return "-"
        if obj.is_deleted:
            return format_html(
                '<span style="color: red; font-weight: bold;">{}</span>',
                "🗑️ DELETED",
            )
        return format_html(
            '<span style="color: green;">{}</span>',
            "✓ Active",
        )

    def get_queryset(self, request):
        """
        Include soft-deleted records in admin.
        Admins should see everything.
        """
        if hasattr(self.model, "all_objects"):
            return self.model.all_objects.all()
        return super().get_queryset(request)

    def save_model(self, request, obj, form, change):
        """Auto-set created_by and updated_by."""
        if not change:  # Creating new object
            if hasattr(obj, "created_by") and not obj.created_by:
                obj.created_by = request.user

        if hasattr(obj, "updated_by"):
            obj.updated_by = request.user

        super().save_model(request, obj, form, change)


class BaseReadOnlyAdmin(admin.ModelAdmin):
    """
    Base admin for read-only models (lookups, reference data).
    """

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser
