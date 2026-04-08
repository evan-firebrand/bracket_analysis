"""Scenario engines for bracket analysis.

Two engines, same output format:
- Brute-force: enumerates all 2^N outcomes (for <=15 remaining games)
- Monte Carlo: simulates 100K outcomes weighted by odds (for >15 games)

Both resolve games round-by-round, propagating winners through the bracket
tree so that later-round games (including the championship) are properly
simulated.

Both return ScenarioResults.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from core.models import GameResult, PlayerEntry, Results, TournamentStructure
from core.scoring import score_entry
from core.tournament import get_remaining_slots


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

    # Pairwise finish tracking: (player_a, player_b) -> scenarios where a finishes ahead of b
    pairwise_wins: dict[tuple[str, str], int] = field(default_factory=dict)


@dataclass
class GameProbability:
    """Win probability with transparency about its source."""

    team_a: str
    team_b: str
    prob_a: float  # probability team_a wins (0.0 to 1.0)
    source: str  # "moneyline", "spread", "seed_historical", "coin_flip"
    raw_value: str | None  # e.g. "-130/+110", "-6.5", "1v16", None
    confidence: str  # "high", "medium", "low", "none"


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


def _get_remaining_slots_by_round(
    tournament: TournamentStructure,
    results: Results,
) -> list[list[str]]:
    """Get remaining slots grouped and sorted by round.

    Returns a list of lists: each inner list contains slot_ids for one round,
    in ascending round order. This is needed to resolve games round-by-round
    so that winners propagate correctly to later rounds.
    """
    remaining = get_remaining_slots(tournament, results)
    rounds: dict[int, list[str]] = {}
    for slot_id in remaining:
        rnd = tournament.slots[slot_id].round
        rounds.setdefault(rnd, []).append(slot_id)
    return [rounds[r] for r in sorted(rounds)]


def _resolve_participants(
    tournament: TournamentStructure,
    hypo_results: dict[str, GameResult],
    slot_id: str,
) -> tuple[str | None, str | None]:
    """Determine who plays in a slot using hypothetical results.

    Like tournament.get_participants_for_slot but works with a dict of
    hypothetical GameResults rather than a Results object.
    """
    slot = tournament.slots[slot_id]
    if slot.round == 1:
        return (slot.top_team, slot.bottom_team)

    feeders = tournament.get_feeder_slots(slot_id)
    if len(feeders) != 2:
        return (None, None)

    r0 = hypo_results.get(feeders[0])
    r1 = hypo_results.get(feeders[1])
    return (r0.winner if r0 else None, r1.winner if r1 else None)


def _simulate_tournament_brute_force(
    tournament: TournamentStructure,
    results: Results,
    rounds_of_slots: list[list[str]],
) -> list[dict[str, GameResult]]:
    """Enumerate all possible outcomes by resolving games round-by-round.

    For each round, we determine which games are actionable (both participants
    known from previous round results), then enumerate all 2^K outcomes for
    those K games. Games where a participant is unknown (e.g. feeder game had
    an unknown participant itself) are skipped.

    Returns a list of complete hypothetical result dicts (one per scenario).
    """
    # Start with one scenario: the current results
    scenarios = [dict(results.results)]

    for round_slots in rounds_of_slots:
        next_scenarios = []
        for hypo in scenarios:
            # Determine actionable games in this round for this scenario
            actionable = []
            for slot_id in round_slots:
                team_a, team_b = _resolve_participants(tournament, hypo, slot_id)
                if team_a and team_b:
                    actionable.append((slot_id, team_a, team_b))

            if not actionable:
                next_scenarios.append(hypo)
                continue

            # Enumerate all 2^K outcomes for this round's actionable games
            n = len(actionable)
            for bits in range(2 ** n):
                new_hypo = dict(hypo)
                for i, (slot_id, team_a, team_b) in enumerate(actionable):
                    if (bits >> i) & 1:
                        new_hypo[slot_id] = GameResult(winner=team_a, loser=team_b)
                    else:
                        new_hypo[slot_id] = GameResult(winner=team_b, loser=team_a)
                next_scenarios.append(new_hypo)

        scenarios = next_scenarios

    return scenarios


# --- Brute Force Engine ---


def brute_force_scenarios(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> ScenarioResults:
    """Enumerate all possible outcomes and score every player against each.

    Resolves games round-by-round so that later-round matchups (which depend
    on earlier results) are properly simulated. Only feasible for <=15 total
    remaining games (2^15 = 32,768 scenarios).
    """
    rounds_of_slots = _get_remaining_slots_by_round(tournament, results)
    if not rounds_of_slots:
        return _empty_results("brute_force", entries, [])

    # Generate all complete scenarios
    all_scenarios = _simulate_tournament_brute_force(
        tournament, results, rounds_of_slots
    )
    total = len(all_scenarios)

    if total == 0:
        return _empty_results("brute_force", entries, [])

    # Collect all slots that were actually simulated (for critical game tracking)
    all_remaining = []
    for round_slots in rounds_of_slots:
        all_remaining.extend(round_slots)

    # Initialize counters
    win_counts: dict[str, int] = {e.player_name: 0 for e in entries}
    finish_dist: dict[str, dict[int, int]] = {
        e.player_name: {} for e in entries
    }
    pairwise_wins: dict[tuple[str, str], int] = {}

    # For critical game analysis: track wins per player when each game goes each way
    # slot_id -> {team_slug: {player: win_count}}
    game_win_splits: dict[str, dict[str, dict[str, int]]] = {}

    for hypo_results in all_scenarios:
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

        # Record pairwise finishes
        for i, (name_i, _) in enumerate(scores):
            for j, (name_j, _) in enumerate(scores):
                if i < j:
                    key = (name_i, name_j)
                    pairwise_wins[key] = pairwise_wins.get(key, 0) + 1

        # Record for critical game splits
        for slot_id in all_remaining:
            result = hypo_results.get(slot_id)
            if not result:
                continue
            if slot_id not in game_win_splits:
                game_win_splits[slot_id] = {}
            team = result.winner
            if team not in game_win_splits[slot_id]:
                game_win_splits[slot_id][team] = {e.player_name: 0 for e in entries}
            game_win_splits[slot_id][team][winner_name] += 1

    # Build critical games from splits
    critical = _build_critical_games_from_splits(
        game_win_splits, total, entries, tournament
    )

    # Elimination
    eliminated = {name: count == 0 for name, count in win_counts.items()}

    # Build remaining games info for the result
    remaining_games = []
    for slot_id in all_remaining:
        slot = tournament.slots[slot_id]
        remaining_games.append({
            "slot_id": slot_id,
            "round": slot.round,
            "region": slot.region,
            "team_a": None,
            "team_b": None,
        })

    return ScenarioResults(
        engine="brute_force",
        total_scenarios=total,
        remaining_games=remaining_games,
        win_counts=win_counts,
        finish_distributions=finish_dist,
        is_eliminated=eliminated,
        critical_games=critical,
        pairwise_wins=pairwise_wins,
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

    Resolves games round-by-round so that later-round matchups (which depend
    on earlier results) are properly simulated.

    Args:
        odds: Optional odds data. If None, uses seed-based historical rates.
        n_simulations: Number of simulations to run.
        seed: Random seed for reproducibility.
    """
    if seed is not None:
        random.seed(seed)

    rounds_of_slots = _get_remaining_slots_by_round(tournament, results)
    if not rounds_of_slots:
        return _empty_results("monte_carlo", entries, [])

    all_remaining = []
    for round_slots in rounds_of_slots:
        all_remaining.extend(round_slots)

    # Initialize counters
    win_counts: dict[str, int] = {e.player_name: 0 for e in entries}
    finish_dist: dict[str, dict[int, int]] = {
        e.player_name: {} for e in entries
    }
    pairwise_wins: dict[tuple[str, str], int] = {}
    game_win_splits: dict[str, dict[str, dict[str, int]]] = {}

    # Run simulations
    for _ in range(n_simulations):
        hypo_results = dict(results.results)

        # Resolve games round-by-round, propagating winners
        for round_slots in rounds_of_slots:
            for slot_id in round_slots:
                team_a, team_b = _resolve_participants(
                    tournament, hypo_results, slot_id
                )
                if not team_a or not team_b:
                    continue

                prob_a = _get_win_probability(
                    team_a, team_b, tournament, odds, slot_id
                )
                if random.random() < prob_a:
                    winner, loser = team_a, team_b
                else:
                    winner, loser = team_b, team_a
                hypo_results[slot_id] = GameResult(winner=winner, loser=loser)

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

        # Record pairwise finishes
        for i, (name_i, _) in enumerate(scores):
            for j, (name_j, _) in enumerate(scores):
                if i < j:
                    key = (name_i, name_j)
                    pairwise_wins[key] = pairwise_wins.get(key, 0) + 1

        # Record for critical game splits
        for slot_id in all_remaining:
            result = hypo_results.get(slot_id)
            if not result:
                continue
            if slot_id not in game_win_splits:
                game_win_splits[slot_id] = {}
            team = result.winner
            if team not in game_win_splits[slot_id]:
                game_win_splits[slot_id][team] = {e.player_name: 0 for e in entries}
            game_win_splits[slot_id][team][winner_name] += 1

    critical = _build_critical_games_from_splits(
        game_win_splits, n_simulations, entries, tournament
    )
    eliminated = {name: count == 0 for name, count in win_counts.items()}

    remaining_games = []
    for slot_id in all_remaining:
        slot = tournament.slots[slot_id]
        remaining_games.append({
            "slot_id": slot_id,
            "round": slot.round,
            "region": slot.region,
            "team_a": None,
            "team_b": None,
        })

    return ScenarioResults(
        engine="monte_carlo",
        total_scenarios=n_simulations,
        remaining_games=remaining_games,
        win_counts=win_counts,
        finish_distributions=finish_dist,
        is_eliminated=eliminated,
        critical_games=critical,
        pairwise_wins=pairwise_wins,
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
    remaining = get_remaining_slots(tournament, results)

    if len(remaining) <= brute_force_threshold:
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


def get_game_probability(
    team_a: str,
    team_b: str,
    tournament: TournamentStructure,
    odds: dict | None,
    slot_id: str | None = None,
) -> GameProbability:
    """Get win probability with full transparency about the source.

    Priority order:
    1. Per-game moneyline from odds["rounds"] (high confidence)
    2. Per-game spread from odds["rounds"] (medium confidence)
    3. Per-team round advancement odds from odds["teams"] (medium confidence)
    4. Seed-based historical win rates (low confidence)
    5. 0.5 coin flip (no confidence)

    This is the public API — plugins use this to show users where
    probabilities come from.
    """
    if odds:
        if "rounds" in odds:
            game_odds = _find_game_odds(odds, team_a, team_b, slot_id)
            if game_odds:
                # Try moneyline first
                ml_a = game_odds.get("moneyline_team1")
                ml_b = game_odds.get("moneyline_team2")
                if ml_a is not None and ml_b is not None:
                    prob = _moneyline_to_probability(
                        ml_a, ml_b, game_odds.get("team1"), team_a
                    )
                    if prob is not None:
                        return GameProbability(
                            team_a=team_a, team_b=team_b, prob_a=prob,
                            source="moneyline",
                            raw_value=f"{ml_a}/{ml_b:+d}" if ml_b >= 0 else f"{ml_a}/{ml_b}",
                            confidence="high",
                        )

                # Try spread
                spread = game_odds.get("spread")
                if spread is not None:
                    prob = _spread_to_probability(
                        spread, game_odds.get("team1"), team_a
                    )
                    if prob is not None:
                        return GameProbability(
                            team_a=team_a, team_b=team_b, prob_a=prob,
                            source="spread",
                            raw_value=f"{spread:+.1f}",
                            confidence="medium",
                        )

        # Try per-team format
        if "teams" in odds:
            odds_a = odds["teams"].get(team_a, {})
            odds_b = odds["teams"].get(team_b, {})
            rp_a = odds_a.get("round_probs", {})
            rp_b = odds_b.get("round_probs", {})

            for key in ("winner", "championship", "ff", "r4", "r3", "r2"):
                pa = rp_a.get(key)
                pb = rp_b.get(key)
                if pa is not None and pb is not None and (pa + pb) > 0:
                    return GameProbability(
                        team_a=team_a, team_b=team_b,
                        prob_a=pa / (pa + pb),
                        source="round_advancement",
                        raw_value=f"{pa:.3f}/{pb:.3f}",
                        confidence="medium",
                    )

    # Fallback: seed-based historical win rates
    t_a = tournament.teams.get(team_a)
    t_b = tournament.teams.get(team_b)
    if t_a and t_b:
        high_seed = min(t_a.seed, t_b.seed)
        low_seed = max(t_a.seed, t_b.seed)
        rate = SEED_WIN_RATES.get((high_seed, low_seed))
        if rate is not None:
            prob = rate if t_a.seed <= t_b.seed else 1 - rate
            return GameProbability(
                team_a=team_a, team_b=team_b, prob_a=prob,
                source="seed_historical",
                raw_value=f"({high_seed}) vs ({low_seed})",
                confidence="low",
            )

    return GameProbability(
        team_a=team_a, team_b=team_b, prob_a=0.5,
        source="coin_flip",
        raw_value=None,
        confidence="none",
    )


def _get_win_probability(
    team_a: str,
    team_b: str,
    tournament: TournamentStructure,
    odds: dict | None,
    slot_id: str | None = None,
) -> float:
    """Internal shortcut — returns just the float for engine use."""
    return get_game_probability(team_a, team_b, tournament, odds, slot_id).prob_a


def _find_game_odds(
    odds: dict, team_a: str, team_b: str, slot_id: str | None
) -> dict | None:
    """Find the odds entry for a specific game from the per-game format."""
    for _round_name, games in odds.get("rounds", {}).items():
        for game in games:
            # Match by slot_id if available
            if slot_id and game.get("slot_id") == slot_id:
                return game
            # Match by team names
            t1, t2 = game.get("team1"), game.get("team2")
            if {t1, t2} == {team_a, team_b}:
                return game
    return None


def _moneyline_to_probability(
    ml_team1: int, ml_team2: int, team1_slug: str, target_team: str
) -> float | None:
    """Convert American moneylines to implied probability for target_team.

    American odds: negative = favorite, positive = underdog.
    -130 means bet $130 to win $100 → implied prob = 130/(130+100) = 56.5%
    +110 means bet $100 to win $110 → implied prob = 100/(100+110) = 47.6%
    """
    def _ml_to_implied(ml: int) -> float:
        if ml < 0:
            return abs(ml) / (abs(ml) + 100)
        else:
            return 100 / (ml + 100)

    implied_1 = _ml_to_implied(ml_team1)
    implied_2 = _ml_to_implied(ml_team2)

    # Remove vig by normalizing
    total = implied_1 + implied_2
    if total <= 0:
        return None

    prob_1 = implied_1 / total
    return prob_1 if target_team == team1_slug else 1 - prob_1


def _spread_to_probability(
    spread: float, team1_slug: str, target_team: str
) -> float | None:
    """Convert point spread to approximate win probability.

    Uses the empirical relationship: each point of spread ≈ 3% win probability.
    Spread of -5.5 → ~68% win probability for the favorite.
    """
    if spread == 0:
        return 0.5

    # spread is negative for team1 favorite (e.g., -5.5)
    # Convert to probability: 50% + (abs(spread) * 3%), capped at 99%
    prob_1 = 0.5 + (abs(spread) * 0.03)
    prob_1 = min(prob_1, 0.99)

    # If spread is negative, team1 is favored
    if spread < 0:
        return prob_1 if target_team == team1_slug else 1 - prob_1
    else:
        return (1 - prob_1) if target_team == team1_slug else prob_1


def _build_critical_games_from_splits(
    game_win_splits: dict[str, dict[str, dict[str, int]]],
    total_scenarios: int,
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
) -> list[CriticalGame]:
    """Build CriticalGame objects from slot-id-keyed win split data."""
    critical = []

    for slot_id, splits in game_win_splits.items():
        teams = list(splits.keys())
        if len(teams) != 2:
            continue

        team_a, team_b = teams[0], teams[1]

        # Count scenarios where each team won this game
        a_total = sum(splits[team_a].values())
        b_total = sum(splits[team_b].values())

        swings: dict[str, tuple[float, float]] = {}
        max_swing = 0.0

        for entry in entries:
            name = entry.player_name
            win_if_a = splits[team_a].get(name, 0) / a_total if a_total > 0 else 0
            win_if_b = splits[team_b].get(name, 0) / b_total if b_total > 0 else 0
            swings[name] = (win_if_a, win_if_b)
            swing = abs(win_if_a - win_if_b)
            if swing > max_swing:
                max_swing = swing

        critical.append(CriticalGame(
            slot_id=slot_id,
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
