"""Load and validate tournament data from JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from core.models import (
    GameResult,
    GameSlot,
    PlayerEntry,
    Results,
    Team,
    TournamentStructure,
)


def load_tournament(path: str | Path) -> TournamentStructure:
    """Load tournament structure from JSON file."""
    with open(path) as f:
        data = json.load(f)

    teams = {}
    for slug, info in data["teams"].items():
        teams[slug] = Team(
            slug=slug,
            name=info["name"],
            seed=info["seed"],
            region=info["region"],
        )

    slots = {}
    slot_order = []
    for slot_data in data["slots"]:
        slot = GameSlot(
            slot_id=slot_data["slot_id"],
            round=slot_data["round"],
            region=slot_data["region"],
            position=slot_data["position"],
            feeds_into=slot_data.get("feeds_into"),
            top_team=slot_data.get("top_team"),
            bottom_team=slot_data.get("bottom_team"),
        )
        slots[slot.slot_id] = slot
        slot_order.append(slot.slot_id)

    return TournamentStructure(
        year=data["year"],
        teams=teams,
        slots=slots,
        slot_order=slot_order,
    )


def load_results(path: str | Path) -> Results:
    """Load game results from JSON file."""
    path = Path(path)
    if not path.exists():
        return Results(last_updated="", results={})

    with open(path) as f:
        data = json.load(f)

    results = {}
    for slot_id, result_data in data.get("results", {}).items():
        results[slot_id] = GameResult(
            winner=result_data["winner"],
            loser=result_data["loser"],
            score=result_data.get("score"),
        )

    return Results(
        last_updated=data.get("last_updated", ""),
        results=results,
    )


def load_entries(path: str | Path) -> list[PlayerEntry]:
    """Load player bracket entries from JSON file."""
    with open(path) as f:
        data = json.load(f)

    entries = []
    for entry_data in data["entries"]:
        entries.append(PlayerEntry(
            player_name=entry_data["player_name"],
            entry_name=entry_data.get("entry_name", entry_data["player_name"]),
            picks=entry_data["picks"],
        ))

    return entries


def validate_entry(
    entry: PlayerEntry,
    tournament: TournamentStructure,
) -> list[str]:
    """Validate a player's bracket entry. Returns list of error messages."""
    errors = []

    # Check all slots are filled
    for slot_id in tournament.slot_order:
        if slot_id not in entry.picks:
            errors.append(f"{entry.player_name}: missing pick for {slot_id}")

    # Check all picked teams exist
    for slot_id, team_slug in entry.picks.items():
        if team_slug not in tournament.teams:
            errors.append(
                f"{entry.player_name}: unknown team '{team_slug}' in {slot_id}"
            )

    # Check bracket tree consistency — if you pick a team in round N,
    # that team must also be your pick in one of the feeder slots for round N-1
    for slot_id, picked_team in entry.picks.items():
        slot = tournament.slots.get(slot_id)
        if not slot or slot.round == 1:
            continue

        feeder_slots = tournament.get_feeder_slots(slot_id)
        if not feeder_slots:
            continue

        feeder_picks = [entry.picks.get(fs) for fs in feeder_slots]
        if picked_team not in feeder_picks:
            errors.append(
                f"{entry.player_name}: picked '{picked_team}' in {slot_id} "
                f"but didn't pick them in any feeder slot {feeder_slots}"
            )

    return errors
