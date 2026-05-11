from django.db import models
from mptt.models import MPTTModel
from mptt.models import TreeForeignKey

from pms_api.core.managers import CachedManager
from pms_api.core.models.base import BaseModel


class LookupType(BaseModel):
    """
    Categories of lookup values: project_type, contractor_type, document_type, etc.
    Admin defines these; system uses them to populate dropdowns.
    """

    code = models.CharField(max_length=50, unique=True)  # machine key
    name_en = models.CharField(max_length=255)
    name_am = models.CharField(max_length=255, blank=True)  # Amharic
    name_or = models.CharField(max_length=255, blank=True)  # Oromiffa
    is_active = models.BooleanField(default=True)

    # Lookup data changes rarely; cache for an hour by default.
    objects = CachedManager(timeout=60 * 60)

    def __str__(self):
        return self.name_en


class Lookup(BaseModel):
    """
    Actual lookup values. A LookupType='project_type' has values
    like 'road', 'school', 'hospital', etc.
    """

    lookup_type = models.ForeignKey(
        LookupType,
        on_delete=models.CASCADE,
        related_name="lookups",
    )
    code = models.CharField(max_length=50)
    name_en = models.CharField(max_length=255)
    name_am = models.CharField(max_length=255, blank=True)
    name_or = models.CharField(max_length=255, blank=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    extra_data = models.JSONField(
        null=True,
        blank=True,
    )  # for special lookups with extra attributes

    objects = CachedManager(timeout=60 * 60)

    class Meta:
        unique_together = [("lookup_type", "code")]

    def __str__(self):
        return f"{self.lookup_type.code}: {self.name_en}"


class Location(MPTTModel, BaseModel):
    """
    Hierarchical: Region → Zone → Woreda → Kebele (depth managed by MPTT).
    Admin creates hierarchy; projects reference a leaf node.

    Note: 'location_type' stores the semantic level (region, zone, woreda, kebele).
    MPTT's internal 'level' field stores the tree depth (0, 1, 2, 3...).
    """

    name_en = models.CharField(max_length=255)
    name_am = models.CharField(max_length=255, blank=True)
    name_or = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=50, unique=True)
    location_type = models.CharField(
        max_length=50,
        blank=True,
    )  # region, zone, woreda, kebele
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    objects = CachedManager(timeout=60 * 60)

    class MPTTMeta:
        order_insertion_by = ["name_en"]

    def __str__(self):
        return self.name_en


class Department(MPTTModel, BaseModel):
    """
    Hierarchical org structure. Depth is dynamic — IT admin builds the tree.
    Used for row-level security and budget forwarding.
    """

    name_en = models.CharField(max_length=255)
    name_am = models.CharField(max_length=255, blank=True)
    name_or = models.CharField(max_length=255, blank=True)
    code = models.CharField(max_length=50, unique=True)
    parent = TreeForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )

    objects = CachedManager(timeout=60 * 60)

    class MPTTMeta:
        order_insertion_by = ["name_en"]

    def __str__(self):
        return self.name_en
