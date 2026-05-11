"""
CachedManager — drop-in soft-delete manager with transparent query caching.

Usage:
    from pms_api.core.managers import CachedManager

    class Lookup(BaseModel):
        objects = CachedManager()        # default TTL
        # or
        objects = CachedManager(timeout=60 * 60)   # 1 hour

Reads:
    Lookup.objects.cached_get(code="road")
    Lookup.objects.cached_filter(is_active=True)
    Lookup.objects.cached_all()
    Lookup.objects.cached_count()
    Lookup.objects.cached_exists(code="road")

Writes (any of these auto-invalidate the cache for the model):
    instance.save()        — fires post_save → bump_model_version
    instance.delete()      — soft delete → save → post_save
    instance.hard_delete() — fires post_delete → bump_model_version

Note on bulk operations:
    QuerySet.update() and QuerySet.bulk_create() bypass signals and therefore
    bypass invalidation. Call `Model.objects.invalidate()` manually after
    those, or use `instance.save()` per row.
"""

import logging

from django.db.models.signals import post_delete
from django.db.models.signals import post_save

from pms_api.core.cache import DEFAULT_TIMEOUT
from pms_api.core.cache import MISS
from pms_api.core.cache import bump_model_version
from pms_api.core.cache import cache_get
from pms_api.core.cache import cache_set
from pms_api.core.cache import invalidate_model
from pms_api.core.cache import make_query_key
from pms_api.core.models.mixins import SoftDeleteManager

logger = logging.getLogger(__name__)


def _invalidate_receiver(sender, **kwargs):
    """Bump the model's cache version after the surrounding transaction commits."""
    invalidate_model(sender)


class CachedManager(SoftDeleteManager):
    """
    Soft-delete-aware manager that caches common read patterns in Redis and
    auto-invalidates on any post_save / post_delete for the model.

    Caching is opt-in per call (`cached_get`, `cached_filter`, …) so existing
    `Model.objects.filter(…)` callers keep their database semantics unchanged.
    """

    timeout: int = DEFAULT_TIMEOUT

    def __init__(self, *args, timeout: int | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        if timeout is not None:
            self.timeout = timeout

    # Django calls this once per model when the manager is attached; we use
    # the hook to wire up invalidation signals scoped to this specific model.
    def contribute_to_class(self, model, name):
        super().contribute_to_class(model, name)
        post_save.connect(
            _invalidate_receiver,
            sender=model,
            dispatch_uid=f"cached_manager_save_{model._meta.label}",  # noqa: SLF001
            weak=False,
        )
        post_delete.connect(
            _invalidate_receiver,
            sender=model,
            dispatch_uid=f"cached_manager_delete_{model._meta.label}",  # noqa: SLF001
            weak=False,
        )

    # ── Cached reads ──────────────────────────────────────────────────────

    def cached_get(self, *args, **kwargs):
        """
        Like `.get(…)`, but cached. Raises `DoesNotExist` on miss, same as `.get`.

        A "definitely doesn't exist" answer is cached too (stored as `None`),
        so repeated lookups for missing rows don't pound the DB.
        """
        key = make_query_key(self.model, "get", *args, **kwargs)
        cached = cache_get(key)
        if cached is MISS:
            try:
                obj = super().get_queryset().get(*args, **kwargs)
            except self.model.DoesNotExist:
                obj = None
            cache_set(key, obj, self.timeout)
            cached = obj
        if cached is None:
            msg = f"{self.model._meta.label} matching query does not exist."  # noqa: SLF001
            raise self.model.DoesNotExist(msg)
        return cached

    def cached_get_or_none(self, *args, **kwargs):
        """Cached `.get(…)` that returns `None` instead of raising on a miss."""
        try:
            return self.cached_get(*args, **kwargs)
        except self.model.DoesNotExist:
            return None

    def cached_filter(self, *args, **kwargs) -> list:
        """Cached `.filter(…)`. Returns a list (queryset is fully evaluated)."""
        key = make_query_key(self.model, "filter", *args, **kwargs)
        cached = cache_get(key)
        if cached is MISS:
            cached = list(super().get_queryset().filter(*args, **kwargs))
            cache_set(key, cached, self.timeout)
        return cached

    def cached_all(self) -> list:
        """Cached `.all()`. Returns a list."""
        return self.cached_filter()

    def cached_count(self, *args, **kwargs) -> int:
        key = make_query_key(self.model, "count", *args, **kwargs)
        cached = cache_get(key)
        if cached is MISS:
            qs = super().get_queryset()
            if args or kwargs:
                qs = qs.filter(*args, **kwargs)
            cached = qs.count()
            cache_set(key, cached, self.timeout)
        return cached

    def cached_exists(self, *args, **kwargs) -> bool:
        key = make_query_key(self.model, "exists", *args, **kwargs)
        cached = cache_get(key)
        if cached is MISS:
            cached = super().get_queryset().filter(*args, **kwargs).exists()
            cache_set(key, cached, self.timeout)
        return cached

    # ── Manual invalidation (for bulk_update / raw SQL paths) ─────────────

    def invalidate(self) -> None:
        """Bump the model's cache version immediately. Use after bulk_update/raw SQL."""
        bump_model_version(self.model)
