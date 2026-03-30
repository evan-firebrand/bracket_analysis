"""Scenario engines for bracket analysis.

Two engines, same output format:
- Brute-force: enumerates all 2^N outcomes (for <=15 remaining games)
- Monte Carlo: simulates 100K outcomes weighted by odds (for >15 games)

Both return ScenarioResults.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from core.models import GameResult, PlayerEntry, Results, TournamentStructure
from core.scoring import score_entry
from core.tournament import get_remaining_games


@dataclass
class ScenarioResults:
    """Unified output from both engines."""

    engine: str  # "brute_force" or "monte_carlo"
    total_scenarios: int
    remaining_games: list[dict]  # the games that were simulated

    # Per-player results
    win_counts: dict[str, int]  # player_name -> scenarios where they finish 1st
    finish_distributions: dict[str, dict[int, int]]  # player_name -> {position: count}
    is_eliminated: dict[str, bool]  # player_name -> True if win_count == 0

    # Per-game analysis
    critical_games: list[CriticalGame] = field(default_factory=list)


@dataclass
class CriticalGame:
    """How a single game's outcome swings each player's win probability."""

    slot_id: str
    team_a: str
    team_b: str
    # player_name -> (win% if team_a wins, win% if team_b wins)
    swings: dict[str, tuple[float, float]] = field(default_factory=dict)
    # The max absolute swing across all players
    max_swing: float = 0.0


# --- Brute Force Engine ---


def brute_force_scenarios(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> ScenarioResults:
    """Enumerate all possible outcomes and score every player against each.

    Only feasible for <=15 remaining games (2^15 = 32,768 scenarios).
    """
    remaining = get_remaining_games(tournament, results)

    # Filter to games where both participants are known
    actionable = [g for g in remaining if g["team_a"] and g["team_b"]]

    if not actionable:
        return _empty_results("brute_force", entries, remaining)

    n_games = len(actionable)
    total = 2 ** n_games

    # Initialize counters
    win_counts: dict[str, int] = {e.player_name: 0 for e in entries}
    finish_dist: dict[str, dict[int, int]] = {
        e.player_name: {} for e in entries
    }

    # For critical game analysis: track wins per player when each game goes each way
    # game_index -> {team_a_slug: {player: win_count}, team_b_slug: {player: win_count}}
    game_win_splits: dict[int, dict[str, dict[str, int]]] = {}
    for i, game in enumerate(actionable):
        game_win_splits[i] = {
            game["team_a"]: {e.player_name: 0 for e in entries},
            game["team_b"]: {e.player_name: 0 for e in entries},
        }

    # Enumerate all 2^N combinations
    for bits in range(total):
        # Build hypothetical results
        hypo_results = dict(results.results)
        outcome_winners = []

        for i, game in enumerate(actionable):
            winner = game["team_a"] if (bits >> i) & 1 else game["team_b"]
            loser = game["team_b"] if (bits >> i) & 1 else game["team_a"]
            hypo_results[game["slot_id"]] = GameResult(winner=winner, loser=loser)
            outcome_winners.append(winner)

        hypo = Results(last_updated="", results=hypo_results)

        # Score all entries
        scores = []
        for entry in entries:
            scored = score_entry(entry, tournament, hypo)
            scores.append((entry.player_name, scored.total_points))

        # Rank by points (descending)
        scores.sort(key=lambda x: -x[1])

        # Record finish positions
        for pos, (name, _pts) in enumerate(scores, 1):
            finish_dist[name][pos] = finish_dist[name].get(pos, 0) + 1

        # Record winner (position 1)
        winner_name = scores[0][0]
        win_counts[winner_name] += 1

        # Record for critical game splits
        for i, game in enumerate(actionable):
            game_winner = game["team_a"] if (bits >> i) & 1 else game["team_b"]
            game_win_splits[i][game_winner][winner_name] += 1

    # Build critical games
    critical = _build_critical_games(actionable, game_win_splits, total, entries)

    # Elimination
    eliminated = {name: count == 0 for name, count in win_counts.items()}

    return ScenarioResults(
        engine="brute_force",
        total_scenarios=total,
        remaining_games=remaining,
        win_counts=win_counts,
        finish_distributions=finish_dist,
        is_eliminated=eliminated,
        critical_games=critical,
    )


# --- Monte Carlo Engine ---


SEED_WIN_RATES = {
    (1, 16): 0.994, (2, 15): 0.943, (3, 14): 0.851, (4, 13): 0.793,
    (5, 12): 0.645, (6, 11): 0.627, (7, 10): 0.607, (8, 9): 0.517,
}


def monte_carlo_scenarios(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    odds: dict | None = None,
    n_simulations: int = 100_000,
    seed: int | None = None,
) -> ScenarioResults:
    """Run Monte Carlo simulations weighted by odds or seed-based rates.

    Args:
        odds: Optional odds data. If None, uses seed-based historical rates.
        n_simulations: Number of simulations to run.
        seed: Random seed for reproducibility.
    """
    if seed is not None:
        random.seed(seed)

    remaining = get_remaining_games(tournament, results)
    actionable = [g for g in remaining if g["team_a"] and g["team_b"]]

    if not actionable:
        return _empty_results("monte_carlo", entries, remaining)

    # Pre-compute win probabilities for each game
    game_probs = []
    for game in actionable:
        prob_a = _get_win_probability(
            game["team_a"], game["team_b"], tournament, odds
        )
        game_probs.append(prob_a)

    # Initialize counters
    win_counts: dict[str, int] = {e.player_name: 0 for e in entries}
    finish_dist: dict[str, dict[int, int]] = {
        e.player_name: {} for e in entries
    }
    game_win_splits: dict[int, dict[str, dict[str, int]]] = {}
    for i, game in enumerate(actionable):
        game_win_splits[i] = {
            game["team_a"]: {e.player_name: 0 for e in entries},
            game["team_b"]: {e.player_name: 0 for e in entries},
        }

    # Run simulations
    for _ in range(n_simulations):
        hypo_results = dict(results.results)

        for i, game in enumerate(actionable):
            if random.random() < game_probs[i]:
                winner, loser = game["team_a"], game["team_b"]
            else:
                winner, loser = game["team_b"], game["team_a"]
            hypo_results[game["slot_id"]] = GameResult(winner=winner, loser=loser)

        hypo = Results(last_updated="", results=hypo_results)

        scores = []
        for entry in entries:
            scored = score_entry(entry, tournament, hypo)
            scores.append((entry.player_name, scored.total_points))

        scores.sort(key=lambda x: -x[1])

        for pos, (name, _pts) in enumerate(scores, 1):
            finish_dist[name][pos] = finish_dist[name].get(pos, 0) + 1

        winner_name = scores[0][0]
        win_counts[winner_name] += 1

        for i, game in enumerate(actionable):
            game_winner = hypo_results[game["slot_id"]].winner
            game_win_splits[i][game_winner][winner_name] += 1

    critical = _build_critical_games(
        actionable, game_win_splits, n_simulations, entries
    )
    eliminated = {name: count == 0 for name, count in win_counts.items()}

    return ScenarioResults(
        engine="monte_carlo",
        total_scenarios=n_simulations,
        remaining_games=remaining,
        win_counts=win_counts,
        finish_distributions=finish_dist,
        is_eliminated=eliminated,
        critical_games=critical,
    )


# --- Shared Helpers ---


def run_scenarios(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    odds: dict | None = None,
    brute_force_threshold: int = 15,
) -> ScenarioResults:
    """Auto-select engine based on remaining game count."""
    remaining = get_remaining_games(tournament, results)
    actionable = [g for g in remaining if g["team_a"] and g["team_b"]]

    if len(actionable) <= brute_force_threshold:
        return brute_force_scenarios(entries, tournament, results)
    else:
        return monte_carlo_scenarios(entries, tournament, results, odds=odds)


def what_if(
    results: Results,
    slot_id: str,
    winner: str,
    loser: str,
) -> Results:
    """Create a new Results with a hypothetical outcome added."""
    new_results = dict(results.results)
    new_results[slot_id] = GameResult(winner=winner, loser=loser)
    return Results(last_updated=results.last_updated, results=new_results)


def _get_win_probability(
    team_a: str,
    team_b: str,
    tournament: TournamentStructure,
    odds: dict | None,
) -> float:
    """Get probability that team_a beats team_b.

    Uses odds data if available, otherwise falls back to seed-based rates.
    """
    if odds and "teams" in odds:
        # Try to derive from championship probabilities as a rough proxy
        prob_a = odds["teams"].get(team_a, {}).get("championship", 0.5)
        prob_b = odds["teams"].get(team_b, {}).get("championship", 0.5)
        total = prob_a + prob_b
        if total > 0:
            return prob_a / total

    # Fallback: seed-based historical win rates
    t_a = tournament.teams.get(team_a)
    t_b = tournament.teams.get(team_b)
    if t_a and t_b:
        high_seed = min(t_a.seed, t_b.seed)
        low_seed = max(t_a.seed, t_b.seed)
        rate = SEED_WIN_RATES.get((high_seed, low_seed))
        if rate is not None:
            return rate if t_a.seed <= t_b.seed else 1 - rate

    return 0.5  # true coin flip if nothing else


def _build_critical_games(
    actionable: list[dict],
    game_win_splits: dict[int, dict[str, dict[str, int]]],
    total_scenarios: int,
    entries: list[PlayerEntry],
) -> list[CriticalGame]:
    """Build CriticalGame objects from win split data."""
    critical = []

    for i, game in enumerate(actionable):
        splits = game_win_splits[i]
        team_a, team_b = game["team_a"], game["team_b"]

        # Count scenarios where each team won
        a_total = sum(splits[team_a].values())
        b_total = sum(splits[team_b].values())

        swings: dict[str, tuple[float, float]] = {}
        max_swing = 0.0

        for entry in entries:
            name = entry.player_name
            win_if_a = splits[team_a][name] / a_total if a_total > 0 else 0
            win_if_b = splits[team_b][name] / b_total if b_total > 0 else 0
            swings[name] = (win_if_a, win_if_b)
            swing = abs(win_if_a - win_if_b)
            if swing > max_swing:
                max_swing = swing

        critical.append(CriticalGame(
            slot_id=game["slot_id"],
            team_a=team_a,
            team_b=team_b,
            swings=swings,
            max_swing=max_swing,
        ))

    # Sort by max swing (most impactful first)
    critical.sort(key=lambda g: -g.max_swing)
    return critical


def _empty_results(
    engine: str,
    entries: list[PlayerEntry],
    remaining: list[dict],
) -> ScenarioResults:
    """Return results when no actionable games remain."""
    return ScenarioResults(
        engine=engine,
        total_scenarios=0,
        remaining_games=remaining,
        win_counts={e.player_name: 0 for e in entries},
        finish_distributions={e.player_name: {} for e in entries},
        is_eliminated={e.player_name: True for e in entries},
        critical_games=[],
    )
