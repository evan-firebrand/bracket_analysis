#!/usr/bin/env python3
"""Validate all data files for structural correctness.

Checks:
- All required fields present in each data file
- All team slugs consistent across files
- All slot_ids in results/entries exist in tournament.json
- Player bracket picks form valid bracket trees
- Winner/loser in results are valid teams
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text())


def main():
    data_dir = Path(__file__).parent.parent / "data"
    errors: list[str] = []

    # --- Tournament ---
    print("Loading tournament structure...")
    tournament = load_json(data_dir / "tournament.json")
    if tournament is None:
        errors.append("tournament.json: FILE NOT FOUND")
        print("  NOT FOUND")
        _report(errors)
        return

    teams = tournament.get("teams", {})
    slots = tournament.get("slots", [])
    slot_ids = {s["slot_id"] for s in slots}
    slots_by_id = {s["slot_id"]: s for s in slots}
    print(f"  {len(teams)} teams, {len(slots)} game slots")

    # Validate tournament fields
    if "year" not in tournament:
        errors.append("tournament.json: missing 'year'")
    for slug, info in teams.items():
        for field in ["name", "seed", "region"]:
            if field not in info:
                errors.append(f"tournament.json: team '{slug}' missing '{field}'")

    for slot in slots:
        for field in ["slot_id", "round", "region", "position", "feeds_into"]:
            if field not in slot:
                errors.append(f"tournament.json: slot missing '{field}'")
        if slot.get("round") == 1:
            for tf in ["top_team", "bottom_team"]:
                t = slot.get(tf)
                if t and t not in teams:
                    errors.append(f"tournament.json: slot '{slot.get('slot_id')}' unknown {tf} '{t}'")
        fi = slot.get("feeds_into")
        if fi is not None and fi not in slot_ids:
            errors.append(f"tournament.json: slot '{slot.get('slot_id')}' feeds_into unknown '{fi}'")

    # Check round counts
    round_counts: dict[int, int] = {}
    for s in slots:
        r = s.get("round", 0)
        round_counts[r] = round_counts.get(r, 0) + 1
    expected = {1: 32, 2: 16, 3: 8, 4: 4, 5: 2, 6: 1}
    for r, exp in expected.items():
        actual = round_counts.get(r, 0)
        if actual != exp:
            errors.append(f"tournament.json: round {r} has {actual} slots, expected {exp}")

    # --- Results ---
    print("Loading results...")
    results_data = load_json(data_dir / "results.json")
    if results_data is None:
        print("  NOT FOUND (ok if tournament hasn't started)")
    else:
        if "last_updated" not in results_data:
            errors.append("results.json: missing 'last_updated'")
        results = results_data.get("results", {})
        print(f"  {len(results)} games completed")

        for slot_id, result in results.items():
            if slot_id not in slot_ids:
                errors.append(f"results.json: unknown slot_id '{slot_id}'")
            for field in ["winner", "loser"]:
                val = result.get(field)
                if val is None:
                    errors.append(f"results.json: slot '{slot_id}' missing '{field}'")
                elif val not in teams:
                    errors.append(f"results.json: slot '{slot_id}' {field} '{val}' not a valid team")
            if result.get("winner") == result.get("loser"):
                errors.append(f"results.json: slot '{slot_id}' winner == loser")

    # --- Player Brackets ---
    print("Loading player brackets...")
    brackets_data = load_json(data_dir / "entries" / "player_brackets.json")
    if brackets_data is None:
        print("  NOT FOUND (ok if brackets not yet collected)")
    else:
        entries = brackets_data.get("entries", [])
        print(f"  {len(entries)} entries")
        names: set[str] = set()

        for entry in entries:
            name = entry.get("player_name", "<unknown>")
            entry_errors: list[str] = []

            if name in names:
                entry_errors.append(f"duplicate player_name '{name}'")
            names.add(name)

            picks = entry.get("picks", {})

            # Check pick count
            if len(picks) != 63:
                entry_errors.append(f"has {len(picks)} picks, expected 63")

            # Check slot_ids and team slugs
            for slot_id, team_slug in picks.items():
                if slot_id not in slot_ids:
                    entry_errors.append(f"unknown slot_id '{slot_id}'")
                if team_slug not in teams:
                    entry_errors.append(f"slot '{slot_id}' unknown team '{team_slug}'")

            # Check missing slots
            missing = slot_ids - set(picks.keys())
            if missing:
                entry_errors.append(f"missing {len(missing)} slot(s): {sorted(missing)[:3]}...")

            # Check bracket tree consistency
            for slot in slots:
                sid = slot["slot_id"]
                if slot["round"] <= 1 or sid not in picks:
                    continue
                pick = picks[sid]
                feeders = [s["slot_id"] for s in slots if s.get("feeds_into") == sid]
                feeder_picks = [picks.get(f) for f in feeders if f in picks]
                if pick not in feeder_picks:
                    entry_errors.append(
                        f"tree violation at '{sid}': picked '{pick}' but feeders have {feeder_picks}"
                    )

            status = "OK" if not entry_errors else f"{len(entry_errors)} error(s)"
            print(f"    {name}: {status}")
            for e in entry_errors:
                errors.append(f"player_brackets.json [{name}]: {e}")

    # --- Odds ---
    print("Loading odds...")
    odds_data = load_json(data_dir / "odds.json")
    if odds_data is None:
        print("  NOT FOUND (app falls back to seed-based rates)")
    else:
        if "source" not in odds_data:
            errors.append("odds.json: missing 'source'")
        if "last_updated" not in odds_data:
            errors.append("odds.json: missing 'last_updated'")
        if "rounds" in odds_data:
            total = sum(len(g) for g in odds_data["rounds"].values())
            print(f"  {total} game lines across {len(odds_data['rounds'])} rounds")
        elif "teams" in odds_data:
            print(f"  {len(odds_data['teams'])} team probabilities")
        elif "games" in odds_data:
            print(f"  {len(odds_data['games'])} game lines")
        else:
            errors.append("odds.json: no recognized data key")

    _report(errors)


def _report(errors: list[str]):
    print()
    if errors:
        print(f"VALIDATION FAILED — {len(errors)} error(s):")
        for err in errors:
            print(f"  - {err}")
        sys.exit(1)
    else:
        print("VALIDATION PASSED — all data files are valid.")
        sys.exit(0)


if __name__ == "__main__":
    main()
