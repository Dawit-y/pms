from django.contrib.auth.models import AbstractBaseUser
from django.contrib.auth.models import BaseUserManager
from django.contrib.auth.models import Permission
from django.contrib.auth.models import PermissionsMixin
from django.db import models

from pms_api.core.models.base import BaseModel

from .exceptions import UserEmailRequiredException


class UserManager(BaseUserManager):
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
    Custom user model using Django's built-in Permission and Group models.

    - user_permissions: Direct permissions assigned to the user
    - groups: Groups the user belongs to (each group has permissions)
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

    class Meta:
        verbose_name = "User"
        verbose_name_plural = "Users"

    def __str__(self):
        return self.email

    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def get_short_name(self):
        return self.first_name

    def get_all_permissions_list(self):
        """
        Get all permissions for the user (from groups and direct permissions).
        Returns list of permission codenames in format: 'app_label.codename'
        """
        if self.is_superuser:
            return list(
                Permission.objects.values_list(
                    "content_type__app_label",
                    "codename",
                ).distinct(),
            )

        # Get permissions from groups and direct user permissions
        perms = self.get_all_permissions()
        return list(perms)
