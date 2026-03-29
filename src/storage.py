"""Save and load JSON data files.

Data contract: see docs/DATA_CONTRACT.md for exact schemas.

File locations:
  data/tournament.json                  - Tournament structure (written once)
  data/results.json                     - Game results (updated after games)
  data/odds.json                        - Vegas odds (updated 2x/day)
  data/entries/player_brackets.json     - All player bracket picks (written once)
"""

import json
from pathlib import Path


def _ensure_dir(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)


def save_tournament(data: dict, data_dir: str = "data") -> str:
    """Save tournament structure to data/tournament.json."""
    filepath = Path(data_dir) / "tournament.json"
    _ensure_dir(filepath)
    filepath.write_text(json.dumps(data, indent=2))
    print(f"Saved tournament structure: {filepath}")
    return str(filepath)


def save_results(data: dict, data_dir: str = "data") -> str:
    """Save game results to data/results.json.

    Expected format:
    {
        "last_updated": "ISO timestamp",
        "results": { "slot_id": {"winner": "slug", "loser": "slug", "score": "78-65"}, ... }
    }
    """
    filepath = Path(data_dir) / "results.json"
    _ensure_dir(filepath)
    filepath.write_text(json.dumps(data, indent=2))
    print(f"Saved results: {filepath}")
    return str(filepath)


def save_odds(data: dict, data_dir: str = "data") -> str:
    """Save odds to data/odds.json.

    Expected format:
    {
        "last_updated": "ISO timestamp",
        "source": "ESPN/DraftKings",
        "teams": { "slug": {"championship": 0.15, "round_probs": {...}}, ... }
    }
    """
    filepath = Path(data_dir) / "odds.json"
    _ensure_dir(filepath)
    filepath.write_text(json.dumps(data, indent=2))
    print(f"Saved odds: {filepath}")
    return str(filepath)


def save_brackets(data: dict, data_dir: str = "data") -> str:
    """Save player brackets to data/entries/player_brackets.json.

    Expected format:
    {
        "entries": [
            {"player_name": "...", "entry_name": "...", "picks": {"slot_id": "team_slug", ...}},
            ...
        ]
    }
    """
    filepath = Path(data_dir) / "entries" / "player_brackets.json"
    _ensure_dir(filepath)
    filepath.write_text(json.dumps(data, indent=2))
    print(f"Saved brackets: {filepath}")
    return str(filepath)


def add_bracket_entry(entry: dict, data_dir: str = "data") -> str:
    """Add a single player's bracket entry to the player_brackets file.

    If the file exists, appends to the entries array (replacing if same player_name).
    If not, creates a new file.
    """
    filepath = Path(data_dir) / "entries" / "player_brackets.json"
    _ensure_dir(filepath)

    if filepath.exists():
        existing = json.loads(filepath.read_text())
    else:
        existing = {"entries": []}

    # Replace existing entry for same player, or append
    entries = [e for e in existing["entries"] if e.get("player_name") != entry.get("player_name")]
    entries.append(entry)
    existing["entries"] = entries

    filepath.write_text(json.dumps(existing, indent=2))
    print(f"Saved bracket entry for {entry.get('player_name')}: {filepath}")
    return str(filepath)


def load_json(filepath: str) -> dict | None:
    """Load a JSON data file. Returns None if file doesn't exist."""
    path = Path(filepath)
    if not path.exists():
        return None
    return json.loads(path.read_text())


def load_tournament(data_dir: str = "data") -> dict | None:
    return load_json(str(Path(data_dir) / "tournament.json"))


def load_results(data_dir: str = "data") -> dict | None:
    return load_json(str(Path(data_dir) / "results.json"))


def load_odds(data_dir: str = "data") -> dict | None:
    return load_json(str(Path(data_dir) / "odds.json"))


def load_brackets(data_dir: str = "data") -> dict | None:
    return load_json(str(Path(data_dir) / "entries" / "player_brackets.json"))
