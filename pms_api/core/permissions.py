import logging

from rest_framework.permissions import SAFE_METHODS
from rest_framework.permissions import BasePermission
from rest_framework.permissions import DjangoModelPermissions

logger = logging.getLogger(__name__)


# ─── 1. Strict model permissions (adds GET → view_<model>) ───────────────────


class StrictDjangoModelPermissions(DjangoModelPermissions):
    """
    DRF's built-in DjangoModelPermissions does NOT enforce view permission
    on GET requests (it maps GET → []). This subclass fixes that by
    requiring `<app>.view_<model>` for read operations.

    Maps to Django's auto-generated permissions:
        GET    → view_<model>
        POST   → add_<model>
        PUT    → change_<model>
        PATCH  → change_<model>
        DELETE → delete_<model>
    """

    perms_map = {
        "GET": ["%(app_label)s.view_%(model_name)s"],
        "OPTIONS": [],
        "HEAD": [],
        "POST": ["%(app_label)s.add_%(model_name)s"],
        "PUT": ["%(app_label)s.change_%(model_name)s"],
        "PATCH": ["%(app_label)s.change_%(model_name)s"],
        "DELETE": ["%(app_label)s.delete_%(model_name)s"],
    }


# ─── 2. Custom codename permission (for business actions) ────────────────────


def permission_required(*codenames):
    """
    Factory that returns a permission class checking custom codenames.

    For custom business-logic permissions that don't map to standard CRUD.
    The codenames should be registered on the model's Meta.permissions
    or created manually.

    Usage:
        action_permissions = {
            'approve': [permission_required('projects.approve_project')],
            'manage':  [permission_required('accounts.manage_user')],
        }
    """

    class _Perm(BasePermission):
        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            return all(request.user.has_perm(c) for c in codenames)

        def has_object_permission(self, request, view, obj):
            return self.has_permission(request, view)

    _Perm.__name__ = f"HasPermission({'_'.join(codenames)})"
    return _Perm


# ─── 3. Owner-level row security ─────────────────────────────────────────────


class IsOwnerOrAdmin(BasePermission):
    """
    Object-level. Allows access only to the record owner or superusers/staff.
    The model must have an `owner` FK (provided by RowLevelSecurityMixin).
    """

    message = "You do not own this resource."

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_staff:
            return True
        owner = getattr(obj, "owner", None)
        return owner is not None and owner == request.user


# ─── 4. Department-level row security ────────────────────────────────────────


class IsDepartmentMemberOrAdmin(BasePermission):
    """
    Object-level. Grants access if the record's `department` is the user's
    department or an ancestor/descendant (uses MPTT tree queries).
    """

    message = "This resource belongs to a department you don't have access to."

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser or request.user.is_staff:
            return True
        record_dept = getattr(obj, "department", None)
        user_dept = getattr(request.user, "department", None)
        if not record_dept or not user_dept:
            return False
        # Allow access if user's dept is the same or a parent dept
        return (
            record_dept == user_dept
            or record_dept.is_descendant_of(user_dept)
            or record_dept.is_ancestor_of(user_dept)
        )


# ─── 5. Super-admin only ─────────────────────────────────────────────────────


class IsSuperAdmin(BasePermission):
    message = "Only super-admins can perform this action."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser,
        )


# ─── 6. Staff or read-only ───────────────────────────────────────────────────


class IsStaffOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return bool(request.user and request.user.is_staff)


# ─── 7. Action-aware permission mixin for ViewSets ───────────────────────────


class ActionPermissionMixin:
    """
    Mixin for ViewSets. Define `action_permissions` dict mapping action names
    to lists of permission classes. Falls back to `permission_classes` for
    any action NOT listed in the dict.

    This is how standard CRUD + custom actions coexist:
    - Standard CRUD (list/create/update/destroy) → handled by permission_classes
      (e.g. StrictDjangoModelPermissions — auto-checks view/add/change/delete)
    - Custom actions (restore/approve/set-password) → override via action_permissions
      (e.g. IsSuperAdmin, permission_required('projects.approve_project'))

    Example:
        class ProjectViewSet(BaseModelViewSet):
            permission_classes = [StrictDjangoModelPermissions]
            action_permissions = {
                'approve':  [permission_required('projects.approve_project')],
                'restore':  [IsSuperAdmin],
            }
    """

    action_permissions: dict = {}

    def get_permissions(self):
        perms = self.action_permissions.get(self.action)
        if perms is not None:
            return [p() if isinstance(p, type) else p for p in perms]
        return super().get_permissions()
