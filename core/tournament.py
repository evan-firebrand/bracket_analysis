"""Tournament structure utilities.

Game tree traversal, alive teams, remaining slots, team paths.
Pure business logic — no Streamlit imports.
"""

from __future__ import annotations

from core.models import Results, TournamentStructure


def get_remaining_slots(
    tournament: TournamentStructure,
    results: Results,
) -> list[str]:
    """Get slot_ids for games not yet played, in round/position order."""
    return [
        sid for sid in tournament.slot_order
        if not results.is_complete(sid)
    ]


def get_participants_for_slot(
    tournament: TournamentStructure,
    results: Results,
    slot_id: str,
) -> tuple[str | None, str | None]:
    """Determine who plays in a given slot based on current results.

    For Round 1 slots, returns (top_team, bottom_team) directly.
    For later rounds, traces back through feeder slots to find winners.
    Returns None for a position if the feeder game hasn't been played yet.
    """
    slot = tournament.slots[slot_id]

    if slot.round == 1:
        return (slot.top_team, slot.bottom_team)

    feeders = tournament.get_feeder_slots(slot_id)
    if len(feeders) != 2:
        return (None, None)

    team_a = results.winner_of(feeders[0])
    team_b = results.winner_of(feeders[1])
    return (team_a, team_b)


def get_remaining_games(
    tournament: TournamentStructure,
    results: Results,
) -> list[dict]:
    """Get remaining games with their two possible participants.

    Returns list of dicts with:
        slot_id: str
        round: int
        team_a: str | None  (None if feeder game not played)
        team_b: str | None
    """
    remaining = []
    for slot_id in get_remaining_slots(tournament, results):
        slot = tournament.slots[slot_id]
        team_a, team_b = get_participants_for_slot(tournament, results, slot_id)
        remaining.append({
            "slot_id": slot_id,
            "round": slot.round,
            "region": slot.region,
            "team_a": team_a,
            "team_b": team_b,
        })
    return remaining


def get_team_path(
    tournament: TournamentStructure,
    team_slug: str,
) -> list[str]:
    """Get the sequence of slot_ids a team must win to become champion.

    Returns slot_ids from Round 1 through Championship.
    """
    path = []

    # Find the team's Round 1 slot
    r1_slot = None
    for sid, slot in tournament.slots.items():
        if slot.round == 1 and (slot.top_team == team_slug or slot.bottom_team == team_slug):
            r1_slot = sid
            break

    if not r1_slot:
        return []

    # Walk up the feeds_into chain
    current = r1_slot
    while current:
        path.append(current)
        slot = tournament.slots[current]
        current = slot.feeds_into

    return path
