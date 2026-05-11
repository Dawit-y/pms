"""
Cache primitives backing the CachedManager.

Strategy: version-based invalidation.
    - Each model has a "version" counter at `cache_version:<app>.<Model>` in Redis.
    - Cached query keys embed that version: `q:<app>.<Model>:v=<N>:<digest>`.
    - On save/delete, we bump the version. All keys with the old version
      become unreachable in O(1); Redis evicts them as their TTL expires.
    - No need to track which keys belong to which model.

Failure mode: if Redis is unreachable, django-redis (IGNORE_EXCEPTIONS=True)
returns the default for `cache.get`, so reads fall through to the database
and writes are dropped silently. The app stays up; it just runs uncached.
"""

import hashlib
import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import transaction

logger = logging.getLogger(__name__)


DEFAULT_TIMEOUT: int = getattr(settings, "CACHE_DEFAULT_TIMEOUT", 60 * 15)
VERSION_KEY_PREFIX = "cache_version"
QUERY_KEY_PREFIX = "q"

# Sentinel that distinguishes "not in cache" from "cached value is None".
MISS = object()


def _version_key(model) -> str:
    return f"{VERSION_KEY_PREFIX}:{model._meta.label}"  # noqa: SLF001


def get_model_version(model) -> int:
    """Return the current cache version for `model`, initialising to 1 if absent."""
    key = _version_key(model)
    version = cache.get(key)
    if version is None:
        cache.set(key, 1, timeout=None)
        return 1
    return int(version)


def bump_model_version(model) -> int:
    """Atomically increment the cache version, orphaning every prior cached query."""
    key = _version_key(model)
    try:
        return cache.incr(key)
    except ValueError:
        # Key didn't exist yet — initialise past 1 so any concurrent reader
        # that just set v=1 still sees a higher number.
        cache.set(key, 2, timeout=None)
        return 2


def invalidate_model(model) -> None:
    """
    Public hook: bump the version after the surrounding transaction commits.
    If called outside a transaction, the bump happens immediately.
    """
    transaction.on_commit(lambda: bump_model_version(model))


def make_query_key(model, op: str, *args, **kwargs) -> str:
    """Build a stable, version-scoped cache key for a query."""
    version = get_model_version(model)
    payload = repr((op, args, sorted(kwargs.items())))
    digest = hashlib.md5(payload.encode()).hexdigest()[:16]  # noqa: S324
    return f"{QUERY_KEY_PREFIX}:{model._meta.label}:v={version}:{digest}"  # noqa: SLF001


def cache_get(key: str) -> Any:
    """Return the cached value, or the MISS sentinel if absent."""
    return cache.get(key, MISS)


def cache_set(key: str, value: Any, timeout: int = DEFAULT_TIMEOUT) -> None:
    cache.set(key, value, timeout=timeout)


def cache_query(queryset, *, op_hint: str = "qs", timeout: int = DEFAULT_TIMEOUT) -> list:
    """
    Cache the evaluation of an arbitrary queryset. Returns a list.

    Works with any chained queryset — select_related, filter, order_by, etc.
    The cache key is derived from the compiled SQL + params so identical
    queries collapse onto the same key.

        qs = Lookup.objects.select_related("lookup_type").filter(is_active=True)
        items = cache_query(qs, timeout=3600)
    """
    sql, params = queryset.query.sql_with_params()
    payload = f"{op_hint}|{sql}|{params!r}"
    digest = hashlib.md5(payload.encode()).hexdigest()[:16]  # noqa: S324
    version = get_model_version(queryset.model)
    key = f"{QUERY_KEY_PREFIX}:{queryset.model._meta.label}:v={version}:{digest}"  # noqa: SLF001
    cached = cache_get(key)
    if cached is MISS:
        cached = list(queryset)
        cache_set(key, cached, timeout)
    return cached


def cache_value(key: str, producer, *, timeout: int = DEFAULT_TIMEOUT, namespace=None) -> Any:
    """
    Get-or-set a single computed value, optionally namespaced under a model's
    version so it auto-invalidates with that model.

        data = cache_value(
            "location:tree",
            producer=lambda: build_tree(),
            timeout=3600,
            namespace=Location,
        )
    """
    if namespace is not None:
        version = get_model_version(namespace)
        full_key = f"v:{namespace._meta.label}:v={version}:{key}"  # noqa: SLF001
    else:
        full_key = f"v:{key}"
    cached = cache_get(full_key)
    if cached is MISS:
        cached = producer()
        cache_set(full_key, cached, timeout)
    return cached
