"""Round recap and standings-diff logic for the 'What Happened?' view.

Business logic only — no Streamlit imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import (
    PlayerEntry,
    Results,
    TournamentStructure,
)
from core.scoring import ROUND_NAMES, score_entry


@dataclass
class GameRecap:
    slot_id: str
    round: int
    round_name: str
    region: str
    winner: str       # team slug
    loser: str        # team slug
    score: str | None
    pick_count: int   # number of players who picked the winner
    total_players: int
    is_upset: bool    # winner was picked by fewer than half the pool


@dataclass
class RoundRecap:
    round: int
    round_name: str
    games: list[GameRecap]      # completed games this round, sorted by region/position
    total_games_in_round: int   # total slots in this round
    is_complete: bool           # all games in the round are done


@dataclass
class StandingsDiff:
    player_name: str
    points_this_round: int  # points earned in this round only
    total_points: int       # cumulative total after this round
    rank_before: int        # rank before this round
    rank_after: int         # rank after this round
    rank_change: int        # positive = moved up, negative = moved down, 0 = same
    newly_eliminated: bool  # could win before this round, cannot win after
    clinched: bool          # total > every other player's max_possible


def round_recap(
    tournament: TournamentStructure,
    results: Results,
    entries: list[PlayerEntry],
) -> RoundRecap | None:
    """Return a recap of the most recently active round.

    Returns None if no games have been played yet.
    """
    if not results.results:
        return None

    # Find the most recent round with ≥1 completed game
    completed_rounds: set[int] = set()
    for slot_id in results.results:
        slot = tournament.slots.get(slot_id)
        if slot:
            completed_rounds.add(slot.round)

    if not completed_rounds:
        return None

    latest_round = max(completed_rounds)
    round_name = ROUND_NAMES.get(latest_round, f"Round {latest_round}")

    round_slots = tournament.get_round_slots(latest_round)
    total_games_in_round = len(round_slots)
    total_players = len(entries)

    games: list[GameRecap] = []
    for slot in sorted(round_slots, key=lambda s: (s.region, s.position)):
        if not results.is_complete(slot.slot_id):
            continue

        result = results.results[slot.slot_id]
        pick_count = sum(
            1 for entry in entries
            if entry.picks.get(slot.slot_id) == result.winner
        )

        games.append(GameRecap(
            slot_id=slot.slot_id,
            round=latest_round,
            round_name=round_name,
            region=slot.region,
            winner=result.winner,
            loser=result.loser,
            score=result.score,
            pick_count=pick_count,
            total_players=total_players,
            is_upset=total_players > 0 and pick_count < total_players / 2,
        ))

    return RoundRecap(
        round=latest_round,
        round_name=round_name,
        games=games,
        total_games_in_round=total_games_in_round,
        is_complete=len(games) == total_games_in_round,
    )


def standings_diff(
    tournament: TournamentStructure,
    results: Results,
    entries: list[PlayerEntry],
    round_num: int,
) -> list[StandingsDiff]:
    """Return per-player standings changes caused by round_num.

    Compares scores from rounds < round_num (before) to rounds ≤ round_num (after).
    Results are sorted by total_points descending.
    """
    results_before = _filter_results(results, tournament, max_round=round_num - 1)
    results_after = _filter_results(results, tournament, max_round=round_num)

    scored_before = {e.player_name: score_entry(e, tournament, results_before) for e in entries}
    scored_after = {e.player_name: score_entry(e, tournament, results_after) for e in entries}

    ranks_before = _dense_rank({n: s.total_points for n, s in scored_before.items()})
    ranks_after = _dense_rank({n: s.total_points for n, s in scored_after.items()})

    pre_leader_total = max(s.total_points for s in scored_before.values()) if scored_before else 0
    post_leader_total = max(s.total_points for s in scored_after.values()) if scored_after else 0

    diffs: list[StandingsDiff] = []
    for entry in entries:
        name = entry.player_name
        before = scored_before[name]
        after = scored_after[name]

        rank_before = ranks_before[name]
        rank_after = ranks_after[name]

        # Newly eliminated: couldn't close the gap before, but can't anymore
        was_eliminated = before.max_possible < pre_leader_total
        is_eliminated = after.max_possible < post_leader_total
        newly_eliminated = is_eliminated and not was_eliminated

        # Clinched: current total exceeds every other player's max possible.
        # Strict inequality: a tie doesn't clinch — the player must be unreachable.
        clinched = all(
            after.total_points > s.max_possible
            for n, s in scored_after.items()
            if n != name
        )

        diffs.append(StandingsDiff(
            player_name=name,
            points_this_round=after.total_points - before.total_points,
            total_points=after.total_points,
            rank_before=rank_before,
            rank_after=rank_after,
            rank_change=rank_before - rank_after,
            newly_eliminated=newly_eliminated,
            clinched=clinched,
        ))

    return sorted(diffs, key=lambda d: d.total_points, reverse=True)


def _filter_results(
    results: Results,
    tournament: TournamentStructure,
    max_round: int,
) -> Results:
    """Return a Results containing only games from rounds ≤ max_round."""
    filtered = {
        slot_id: result
        for slot_id, result in results.results.items()
        if tournament.slots.get(slot_id) and tournament.slots[slot_id].round <= max_round
    }
    return Results(last_updated=results.last_updated, results=filtered)


def _dense_rank(scores: dict[str, int]) -> dict[str, int]:
    """Dense rank: ties share the same rank number."""
    sorted_unique = sorted(set(scores.values()), reverse=True)
    score_to_rank = {score: i + 1 for i, score in enumerate(sorted_unique)}
    return {name: score_to_rank[score] for name, score in scores.items()}
