"""Tests for the AI content cache."""
from __future__ import annotations

import json
import os
import time

from core.ai.cache import ContentCache, _cache_key, compute_data_hash


def _seed_data_dir(tmp_path):
    """Create a minimal fake data directory matching the expected layout."""
    (tmp_path / "tournament.json").write_text('{"teams": []}')
    (tmp_path / "results.json").write_text('{"games": []}')
    entries_dir = tmp_path / "entries"
    entries_dir.mkdir()
    (entries_dir / "player_brackets.json").write_text('{"players": []}')
    (tmp_path / "odds.json").write_text('{"odds": []}')


class TestComputeDataHash:
    def test_stable_across_calls_when_files_unchanged(self, tmp_path):
        _seed_data_dir(tmp_path)

        h1 = compute_data_hash(tmp_path)
        h2 = compute_data_hash(tmp_path)

        assert h1 == h2
        assert isinstance(h1, str)
        assert len(h1) == 16  # short hex digest

    def test_changes_when_file_mtime_changes(self, tmp_path):
        _seed_data_dir(tmp_path)
        h1 = compute_data_hash(tmp_path)

        # Bump the mtime on one of the data files.
        target = tmp_path / "results.json"
        new_mtime = time.time() + 10
        os.utime(target, (new_mtime, new_mtime))

        h2 = compute_data_hash(tmp_path)
        assert h1 != h2

    def test_changes_when_file_size_changes(self, tmp_path):
        _seed_data_dir(tmp_path)
        h1 = compute_data_hash(tmp_path)

        (tmp_path / "results.json").write_text('{"games": [{"id": 1}]}')
        h2 = compute_data_hash(tmp_path)

        assert h1 != h2

    def test_handles_missing_files_without_raising(self, tmp_path):
        # Empty dir — no files present
        h = compute_data_hash(tmp_path)
        assert isinstance(h, str)
        assert len(h) == 16

    def test_missing_vs_present_yield_different_hashes(self, tmp_path):
        empty_hash = compute_data_hash(tmp_path)
        _seed_data_dir(tmp_path)
        populated_hash = compute_data_hash(tmp_path)

        assert empty_hash != populated_hash


class TestCacheKey:
    def test_different_lens_produces_different_key(self):
        k1 = _cache_key("headline", "Alice", "abc123")
        k2 = _cache_key("recap", "Alice", "abc123")
        assert k1 != k2

    def test_different_viewer_produces_different_key(self):
        k1 = _cache_key("headline", "Alice", "abc123")
        k2 = _cache_key("headline", "Bob", "abc123")
        assert k1 != k2

    def test_different_data_hash_produces_different_key(self):
        k1 = _cache_key("headline", "Alice", "abc123")
        k2 = _cache_key("headline", "Alice", "def456")
        assert k1 != k2

    def test_none_viewer_is_stable(self):
        k1 = _cache_key("headline", None, "abc123")
        k2 = _cache_key("headline", None, "abc123")
        assert k1 == k2


class TestContentCache:
    def test_get_returns_none_on_miss(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        assert cache.get("headline", "Alice", "abc123") is None

    def test_put_then_get_round_trips(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        cache.put(
            lens="headline",
            viewer="Alice",
            data_hash="abc123",
            content="Alice leads the pool!",
            evidence={"tool_calls": [{"name": "get_pool_state"}]},
        )

        entry = cache.get("headline", "Alice", "abc123")
        assert entry is not None
        assert entry["lens"] == "headline"
        assert entry["viewer"] == "Alice"
        assert entry["data_hash"] == "abc123"
        assert entry["content"] == "Alice leads the pool!"
        assert entry["evidence"] == {"tool_calls": [{"name": "get_pool_state"}]}

    def test_put_without_evidence_defaults_to_none(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        cache.put("headline", "Alice", "abc123", "hello")

        entry = cache.get("headline", "Alice", "abc123")
        assert entry is not None
        assert entry["evidence"] is None

    def test_get_returns_none_on_corrupt_json(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        # Write garbage to the file path we'd expect for this key.
        key = _cache_key("headline", "Alice", "abc123")
        (tmp_path / f"{key}.json").write_text("{not-valid-json")

        assert cache.get("headline", "Alice", "abc123") is None

    def test_different_keys_do_not_collide(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        cache.put("headline", "Alice", "h1", "A content")
        cache.put("headline", "Bob", "h1", "B content")
        cache.put("recap", "Alice", "h1", "recap A")
        cache.put("headline", "Alice", "h2", "A newer")

        assert cache.get("headline", "Alice", "h1")["content"] == "A content"
        assert cache.get("headline", "Bob", "h1")["content"] == "B content"
        assert cache.get("recap", "Alice", "h1")["content"] == "recap A"
        assert cache.get("headline", "Alice", "h2")["content"] == "A newer"

    def test_invalidate_all_clears_and_returns_count(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        cache.put("headline", "Alice", "h1", "1")
        cache.put("headline", "Bob", "h1", "2")
        cache.put("recap", "Alice", "h1", "3")

        count = cache.invalidate_all()

        assert count == 3
        assert cache.get("headline", "Alice", "h1") is None
        assert list(tmp_path.glob("*.json")) == []

    def test_invalidate_all_on_empty_returns_zero(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        assert cache.invalidate_all() == 0

    def test_init_creates_cache_dir(self, tmp_path):
        target = tmp_path / "nested" / "cache"
        assert not target.exists()

        ContentCache(cache_dir=target)

        assert target.exists()

    def test_put_writes_valid_json_file(self, tmp_path):
        cache = ContentCache(cache_dir=tmp_path)
        path = cache.put("headline", "Alice", "abc", "hello")

        assert path.exists()
        with open(path) as f:
            payload = json.load(f)
        assert payload["content"] == "hello"
