from django.db import models

from .mixins import AuditMixin
from .mixins import RowLevelSecurityMixin
from .mixins import SignalMixin
from .mixins import SoftDeleteMixin
from .mixins import TimestampMixin
from .mixins import UUIDMixin


class BaseModel(
    UUIDMixin,
    TimestampMixin,
    AuditMixin,
    SoftDeleteMixin,
    RowLevelSecurityMixin,
    SignalMixin,
    models.Model,
):
    """
    Inherit from this for all domain models.
    Provides: uuid, timestamps, audit trail, soft delete, row-level security, signals.
    """

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
