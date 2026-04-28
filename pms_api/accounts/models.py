from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import Permission
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
    Custom user model with enterprise features:
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
                (
                    "Can manage user accounts "
                    "(activate, deactivate, reset password, assign groups)"
                ),
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
        Get all permissions as sorted list of strings in format: 'app_label.codename'
        """
        if self.is_superuser:
            perms = Permission.objects.values_list(
                "content_type__app_label",
                "codename",
            )
            return sorted(f"{app_label}.{codename}" for app_label, codename in perms)

        perms = self.get_all_permissions()
        return sorted(perms)


# Connect signals for the User model
User.connect_signals()
