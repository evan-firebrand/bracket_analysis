"""Content cache for generated AI copy.

Keyed on sha256(lens + viewer + data_hash). Data hash reflects the mtimes of
tournament/results/entries/odds files — invalidated automatically when data changes.
Chat responses are never cached.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


def compute_data_hash(data_dir: Path | str = "data") -> str:
    """Compute a hash of the mtimes of all data files we care about.

    Returns a short hex digest. Used as part of the cache key so cache
    automatically invalidates when any data file is rewritten.
    """
    data_dir = Path(data_dir)
    files = [
        data_dir / "tournament.json",
        data_dir / "results.json",
        data_dir / "entries" / "player_brackets.json",
        data_dir / "odds.json",
    ]
    h = hashlib.sha256()
    for f in files:
        if f.exists():
            stat = f.stat()
            h.update(f"{f.name}:{stat.st_mtime_ns}:{stat.st_size}".encode())
        else:
            h.update(f"{f.name}:missing".encode())
    return h.hexdigest()[:16]


def _cache_key(lens: str, viewer: str | None, data_hash: str) -> str:
    raw = f"{lens}|{viewer or 'all'}|{data_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class ContentCache:
    cache_dir: Path

    def __post_init__(self) -> None:
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get(self, lens: str, viewer: str | None, data_hash: str) -> dict | None:
        """Return cached entry dict or None if miss."""
        key = _cache_key(lens, viewer, data_hash)
        path = self.cache_dir / f"{key}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def put(
        self,
        lens: str,
        viewer: str | None,
        data_hash: str,
        content: str,
        evidence: dict | None = None,
    ) -> Path:
        """Write a cache entry. Returns the path written."""
        key = _cache_key(lens, viewer, data_hash)
        path = self.cache_dir / f"{key}.json"
        payload = {
            "lens": lens,
            "viewer": viewer,
            "data_hash": data_hash,
            "content": content,
            "evidence": evidence,
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        return path

    def invalidate_all(self) -> int:
        """Delete all cached entries. Returns count deleted."""
        count = 0
        for path in self.cache_dir.glob("*.json"):
            path.unlink()
            count += 1
        return count
