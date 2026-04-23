from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.contrib.auth.models import Permission

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """Custom admin for User model."""

    list_display = [
        "email",
        "first_name",
        "last_name",
        "is_active",
        "is_staff",
        "is_superuser",
    ]
    list_filter = ["is_active", "is_staff", "is_superuser", "groups"]
    search_fields = ["email", "first_name", "last_name"]
    ordering = ["email"]

    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Personal Info", {"fields": ("first_name", "last_name", "phone")}),
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

    readonly_fields = ["created_at", "updated_at", "last_login"]
    filter_horizontal = ["groups", "user_permissions"]


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
