from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from pms_api.core.models.base import BaseModel

from .exceptions import UserEmailRequiredException


class UserManager(BaseUserManager):
    """
    Custom user manager that respects soft delete.
    Non-deleted users only by default.
    Use all_objects to get all records including deleted.
    """

    def get_queryset(self):
        """
        Override to filter out soft-deleted users by default.
        This fixes the MRO conflict with BaseModel's SoftDeleteManager.
        """
        return super().get_queryset().filter(is_deleted=False)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise UserEmailRequiredException
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin, BaseModel):
    """
    Custom user model with features:
    - UUID for public identification
    - Timestamps (created_at, updated_at)
    - Signal emission on changes
    - Built-in permission and group support

    Uses Django's built-in Permission and Group models for RBAC.
    """

    email = models.EmailField(unique=True)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    department = models.ForeignKey(
        "lookups.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()
    all_objects = models.Manager()

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

        permissions = [
            (
                "manage_user",
                ("Can manage user accounts (activate, deactivate, reset password, assign groups)"),
            ),
            (
                "manage_superuser",
                "Can operate on superuser accounts (deactivate/delete superusers)",
            ),
            (
                "view_deleted_records",
                "Can view soft-deleted records via ?include_deleted=true",
            ),
            (
                "bypass_row_security",
                "Can view records outside their department/ownership scope",
            ),
            (
                "restore_records",
                "Can restore soft-deleted records",
            ),
            (
                "hard_delete_records",
                "Can permanently delete records (bypass soft-delete)",
            ),
        ]

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_short_name(self):
        return self.first_name

    def get_all_permissions_list(self):
        """
        Builds permission list entirely from the prefetch cache.
        Requires the user to have been fetched with user_permissions and
        groups__permissions prefetched (select_related content_type).
        Zero extra queries.
        """
        perms = set()

        # Direct user permissions — already in prefetch cache
        for perm in self.user_permissions.all():
            perms.add(f"{perm.content_type.app_label}.{perm.codename}")

        # Group permissions — groups and their permissions already prefetched
        for group in self.groups.all():
            for perm in group.permissions.all():
                perms.add(f"{perm.content_type.app_label}.{perm.codename}")

        return sorted(perms)


# Connect signals for the User model
User.connect_signals()
