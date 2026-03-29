"""Save and load JSON data files."""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _ensure_dir(path: Path):
    path.mkdir(parents=True, exist_ok=True)


def save_bracket(data: dict | list, source: str, entry_id: str, data_dir: str = "data") -> str:
    """Save bracket data to a timestamped JSON file.

    Returns the path to the saved file.
    """
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    out_dir = Path(data_dir) / "brackets"
    _ensure_dir(out_dir)

    filename = f"{source}_{entry_id}_{ts}.json"
    filepath = out_dir / filename

    envelope = {
        "source": source,
        "entry_id": entry_id,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    filepath.write_text(json.dumps(envelope, indent=2))
    print(f"Saved bracket: {filepath}")
    return str(filepath)


def save_results(data: dict | list, data_dir: str = "data") -> str:
    """Save game results to a timestamped JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    out_dir = Path(data_dir) / "results"
    _ensure_dir(out_dir)

    filename = f"results_{ts}.json"
    filepath = out_dir / filename

    envelope = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    filepath.write_text(json.dumps(envelope, indent=2))
    print(f"Saved results: {filepath}")
    return str(filepath)


def save_odds(data: dict | list, data_dir: str = "data") -> str:
    """Save odds data to a timestamped JSON file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    out_dir = Path(data_dir) / "odds"
    _ensure_dir(out_dir)

    filename = f"odds_{ts}.json"
    filepath = out_dir / filename

    envelope = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }

    filepath.write_text(json.dumps(envelope, indent=2))
    print(f"Saved odds: {filepath}")
    return str(filepath)


def load_latest(directory: str, prefix: str = "") -> dict | None:
    """Load the most recent JSON file from a directory.

    Args:
        directory: Path to the directory to search.
        prefix: Optional filename prefix filter.

    Returns:
        Parsed JSON data, or None if no files found.
    """
    dir_path = Path(directory)
    if not dir_path.exists():
        return None

    files = sorted(
        [f for f in dir_path.glob("*.json") if f.name.startswith(prefix) or not prefix],
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )

    if not files:
        return None

    return json.loads(files[0].read_text())
