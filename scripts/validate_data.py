#!/usr/bin/env python3
"""Validate all data files for structural correctness."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import load_entries, load_results, load_tournament, validate_entry


def main():
    data_dir = Path(__file__).parent.parent / "data"
    errors: list[str] = []

    # Load tournament
    print("Loading tournament structure...")
    try:
        tournament = load_tournament(data_dir / "tournament.json")
        print(f"  {len(tournament.teams)} teams, {len(tournament.slots)} game slots")
    except Exception as e:
        errors.append(f"tournament.json: {e}")
        print(f"  ERROR: {e}")
        # Can't continue without tournament structure
        _report(errors)
        return

    # Validate slot feeds_into references
    for slot_id, slot in tournament.slots.items():
        if slot.feeds_into and slot.feeds_into not in tournament.slots:
            errors.append(
                f"Slot {slot_id} feeds_into '{slot.feeds_into}' which doesn't exist"
            )

    # Load results
    print("Loading results...")
    try:
        results = load_results(data_dir / "results.json")
        print(f"  {results.completed_count()} games completed")
    except Exception as e:
        errors.append(f"results.json: {e}")
        print(f"  ERROR: {e}")
        results = None

    # Validate result slot_ids exist in tournament
    if results:
        for slot_id in results.results:
            if slot_id not in tournament.slots:
                errors.append(
                    f"results.json: slot_id '{slot_id}' not in tournament"
                )

        # Validate winner/loser are valid teams
        for slot_id, result in results.results.items():
            if result.winner not in tournament.teams:
                errors.append(
                    f"results.json: winner '{result.winner}' in {slot_id} not a valid team"
                )
            if result.loser not in tournament.teams:
                errors.append(
                    f"results.json: loser '{result.loser}' in {slot_id} not a valid team"
                )

    # Load entries
    print("Loading player brackets...")
    try:
        entries = load_entries(data_dir / "entries" / "player_brackets.json")
        print(f"  {len(entries)} entries")
    except Exception as e:
        errors.append(f"player_brackets.json: {e}")
        print(f"  ERROR: {e}")
        entries = []

    # Validate each entry
    for entry in entries:
        entry_errors = validate_entry(entry, tournament)
        errors.extend(entry_errors)
        status = "OK" if not entry_errors else f"{len(entry_errors)} errors"
        print(f"  {entry.player_name}: {status}")

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
