from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission
from django.utils.html import format_html

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model with soft-delete support."""

    list_display = [
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "deleted_status",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser", "is_deleted", "groups"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal Info",
            {"fields": ("first_name", "last_name", "phone", "department")},
        ),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        ("Important Dates", {"fields": ("last_login", "created_at", "updated_at")}),
        (
            "Soft Delete",
            {
                "fields": ("is_deleted", "deleted_at", "deleted_by"),
                "classes": ("collapse",),
            },
        ),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "email",
                    "first_name",
                    "last_name",
                    "password1",
                    "password2",
                ),
            },
        ),
    )

    readonly_fields = [
        "created_at",
        "updated_at",
        "last_login",
        "deleted_at",
        "deleted_by",
    ]
    filter_horizontal = ["groups", "user_permissions"]

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
        """Include soft-deleted users in admin."""
        if hasattr(self.model, "all_objects"):
            return self.model.all_objects.all()
        return super().get_queryset(request)


# Unregister the default Group admin and register with custom settings
admin.site.unregister(Group)


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    """Custom admin for Group model (used as Roles)."""

    list_display = ["name", "permission_count"]
    search_fields = ["name"]
    filter_horizontal = ["permissions"]

    @admin.display(
        description="Permissions",
    )
    def permission_count(self, obj):
        return obj.permissions.count()


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    """Custom admin for Permission model."""

    list_display = ["name", "codename", "content_type"]
    list_filter = ["content_type__app_label"]
    search_fields = ["name", "codename"]
    ordering = ["content_type__app_label", "codename"]
