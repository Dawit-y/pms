"""End-to-end tests for the CachedManager + version-based invalidation."""

import pytest
from django.core.cache import cache

from pms_api.core.cache import get_model_version
from pms_api.core.cache import make_query_key
from pms_api.lookups.models import LookupType


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


# transaction=True so the post_save / post_delete `on_commit` callbacks that
# bump the cache version actually fire. With pytest-django's default wrapping
# transaction they'd be rolled back and never run.
@pytest.mark.django_db(transaction=True)
class TestCachedManager:
    def test_save_bumps_version(self):
        v0 = get_model_version(LookupType)
        LookupType.objects.create(code="cm_a", name_en="A")
        v1 = get_model_version(LookupType)
        assert v1 > v0

    def test_cached_filter_populates_then_hits_cache(self):
        LookupType.objects.create(code="cm_b", name_en="B")
        # First call: miss → DB → populate
        first = LookupType.objects.cached_filter(code="cm_b")
        assert len(first) == 1
        key = make_query_key(LookupType, "filter", code="cm_b")
        assert cache.get(key) is not None  # present in cache

    def test_save_invalidates_existing_cache_entry(self):
        lt = LookupType.objects.create(code="cm_c", name_en="C")
        first = LookupType.objects.cached_filter(code="cm_c")
        key_before = make_query_key(LookupType, "filter", code="cm_c")
        assert cache.get(key_before) is not None

        # Mutate -> bumps version -> key_before is now orphaned
        lt.name_en = "C updated"
        lt.save()

        key_after = make_query_key(LookupType, "filter", code="cm_c")
        assert key_after != key_before

        # Next cached read fetches the fresh value
        second = LookupType.objects.cached_filter(code="cm_c")
        assert second[0].name_en == "C updated"
        assert first[0].name_en == "C"  # confirms first was the pre-update value

    def test_hard_delete_bumps_version(self):
        lt = LookupType.objects.create(code="cm_d", name_en="D")
        v_before = get_model_version(LookupType)
        lt.hard_delete()
        v_after = get_model_version(LookupType)
        assert v_after > v_before

    def test_cached_get_or_none_returns_none_for_missing(self):
        result = LookupType.objects.cached_get_or_none(code="never_exists_xyz")
        assert result is None

    def test_cached_get_raises_for_missing(self):
        with pytest.raises(LookupType.DoesNotExist):
            LookupType.objects.cached_get(code="never_exists_xyz_2")

    def test_cached_count_matches_db(self):
        # Wipe so the count is deterministic regardless of prior fixtures
        LookupType.objects.all().hard_delete() if False else None
        before = LookupType.objects.cached_count()
        LookupType.objects.create(code="cm_e", name_en="E")
        after = LookupType.objects.cached_count()
        assert after == before + 1

    def test_cached_exists(self):
        LookupType.objects.create(code="cm_f", name_en="F")
        assert LookupType.objects.cached_exists(code="cm_f") is True
        assert LookupType.objects.cached_exists(code="not_a_real_code_xyz") is False

    def test_manual_invalidate_bumps_version(self):
        v_before = get_model_version(LookupType)
        LookupType.objects.invalidate()
        v_after = get_model_version(LookupType)
        assert v_after > v_before

    def test_soft_delete_excludes_from_cached_results(self):
        lt = LookupType.objects.create(code="cm_g", name_en="G")
        # Cache an "exists" answer
        assert LookupType.objects.cached_exists(code="cm_g") is True
        # Soft delete (uses .save under the hood -> bumps version)
        lt.delete()
        # Fresh read should reflect the soft delete
        assert LookupType.objects.cached_exists(code="cm_g") is False
