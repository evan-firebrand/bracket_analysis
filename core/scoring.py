"""Scoring engine for NCAA bracket analysis."""

from __future__ import annotations

import pandas as pd

from core.models import (
    PlayerEntry,
    Results,
    ScoredEntry,
    TournamentStructure,
)

# ESPN Tournament Challenge default scoring
POINTS_PER_ROUND: dict[int, int] = {
    1: 10,   # Round of 64
    2: 20,   # Round of 32
    3: 40,   # Sweet 16
    4: 80,   # Elite 8
    5: 160,  # Final Four
    6: 320,  # Championship
}

ROUND_NAMES: dict[int, str] = {
    1: "Round of 64",
    2: "Round of 32",
    3: "Sweet 16",
    4: "Elite 8",
    5: "Final Four",
    6: "Championship",
}


def get_alive_teams(
    tournament: TournamentStructure,
    results: Results,
) -> set[str]:
    """Get teams that haven't been eliminated yet."""
    eliminated = {r.loser for r in results.results.values()}
    return set(tournament.teams.keys()) - eliminated


def score_entry(
    entry: PlayerEntry,
    tournament: TournamentStructure,
    results: Results,
) -> ScoredEntry:
    """Score a single player's bracket against actual results."""
    total_points = 0
    points_by_round: dict[int, int] = {r: 0 for r in POINTS_PER_ROUND}
    correct_picks: list[str] = []
    incorrect_picks: list[str] = []
    pending_picks: list[str] = []

    alive_teams = get_alive_teams(tournament, results)

    for slot_id in tournament.slot_order:
        slot = tournament.slots[slot_id]
        picked_team = entry.picks.get(slot_id)

        if not picked_team:
            continue

        if results.is_complete(slot_id):
            actual_winner = results.winner_of(slot_id)
            if picked_team == actual_winner:
                pts = POINTS_PER_ROUND[slot.round]
                total_points += pts
                points_by_round[slot.round] += pts
                correct_picks.append(slot_id)
            else:
                incorrect_picks.append(slot_id)
        else:
            pending_picks.append(slot_id)

    # Max possible = current points + points for pending picks where team is alive
    max_possible = total_points
    for slot_id in pending_picks:
        slot = tournament.slots[slot_id]
        picked_team = entry.picks.get(slot_id)
        if picked_team and picked_team in alive_teams:
            max_possible += POINTS_PER_ROUND[slot.round]

    return ScoredEntry(
        player_name=entry.player_name,
        entry_name=entry.entry_name,
        total_points=total_points,
        points_by_round=points_by_round,
        correct_picks=correct_picks,
        incorrect_picks=incorrect_picks,
        pending_picks=pending_picks,
        max_possible=max_possible,
    )


def build_leaderboard(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> pd.DataFrame:
    """Build a ranked leaderboard DataFrame from all entries."""
    rows = []
    for entry in entries:
        scored = score_entry(entry, tournament, results)
        row = {
            "Rank": 0,  # filled below
            "Player": scored.player_name,
            "Total": scored.total_points,
            "Max Possible": scored.max_possible,
            "Correct": len(scored.correct_picks),
            "Wrong": len(scored.incorrect_picks),
            "Pending": len(scored.pending_picks),
        }
        for rnd, name in ROUND_NAMES.items():
            row[name] = scored.points_by_round.get(rnd, 0)
        rows.append(row)

    df = pd.DataFrame(rows)
    df = df.sort_values(
        ["Total", "Max Possible"], ascending=[False, False]
    ).reset_index(drop=True)
    df["Rank"] = range(1, len(df) + 1)

    return df
