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
from core.scoring import POINTS_PER_ROUND, get_alive_teams, score_entry
from core.tournament import get_participants_for_slot, get_remaining_slots


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


def player_critical_games(
    sr: ScenarioResults,
    player_name: str,
    top_n: int = 3,
) -> list[dict]:
    """Re-rank critical games by a single player's personal win probability swing.

    Returns list of dicts (up to top_n), sorted by the player's swing descending:
      - slot_id, team_a, team_b
      - win_if_a: player's win% if team_a wins
      - win_if_b: player's win% if team_b wins
      - swing: absolute difference
      - must_win_team: the team the player must root for (set if one outcome → 0.0%)
    """
    result = []
    for cg in sr.critical_games:
        if player_name not in cg.swings:
            continue
        win_if_a, win_if_b = cg.swings[player_name]
        swing = abs(win_if_a - win_if_b)
        if swing == 0.0:
            continue
        if win_if_b == 0.0:
            must_win_team = cg.team_a
        elif win_if_a == 0.0:
            must_win_team = cg.team_b
        else:
            must_win_team = None
        result.append({
            "slot_id": cg.slot_id,
            "team_a": cg.team_a,
            "team_b": cg.team_b,
            "win_if_a": win_if_a,
            "win_if_b": win_if_b,
            "swing": swing,
            "must_win_team": must_win_team,
        })
    result.sort(key=lambda x: x["swing"], reverse=True)
    return result[:top_n]


def clinch_scenarios(
    entries: list[PlayerEntry],
    player_name: str,
    tournament: TournamentStructure,
    results: Results,
) -> dict:
    """Detect clinch scenarios and elimination thresholds for a player.

    Returns dict with:
      - clinched: bool  (True if player has already clinched mathematically)
      - clinch_outcomes: list[dict] | None
            Each dict: {slot_id, required_winner} — outcomes that guarantee 1st
            None if no clinch scenario exists
      - can_win: bool  (False if player's ceiling can't beat the current leader)
      - min_picks_needed: int  (minimum correct picks needed for any win path)
    """
    scored = {e.player_name: score_entry(e, tournament, results) for e in entries}
    player_scored = scored.get(player_name)
    if not player_scored:
        return {"clinched": False, "clinch_outcomes": None, "can_win": False, "min_picks_needed": 0}

    player_entry = next((e for e in entries if e.player_name == player_name), None)
    if not player_entry:
        return {"clinched": False, "clinch_outcomes": None, "can_win": False, "min_picks_needed": 0}

    other_scored = [s for name, s in scored.items() if name != player_name]

    # Already clinched: current score exceeds everyone's max possible
    if other_scored and player_scored.total_points > max(s.max_possible for s in other_scored):
        return {"clinched": True, "clinch_outcomes": [], "can_win": True, "min_picks_needed": 0}

    max_other_current = max((s.total_points for s in other_scored), default=0)

    # can_win: player's ceiling can beat the current leader's score
    can_win = player_scored.max_possible > max_other_current

    if not can_win:
        return {
            "clinched": False,
            "clinch_outcomes": None,
            "can_win": False,
            "min_picks_needed": _min_picks_to_lead(player_scored, max_other_current, tournament),
        }

    # Clinch scenario: build hypothetical where player wins all alive pending picks
    alive_teams = get_alive_teams(tournament, results)
    alive_pending = [
        (slot_id, player_entry.picks[slot_id])
        for slot_id in player_scored.pending_picks
        if player_entry.picks.get(slot_id) in alive_teams
    ]
    alive_pending.sort(key=lambda x: tournament.slots[x[0]].round)

    hypo_results = results  # what_if() returns a new Results; original is never mutated
    clinch_outcomes = []
    for slot_id, pick_team in alive_pending:
        team_a, team_b = get_participants_for_slot(tournament, hypo_results, slot_id)
        if team_a is None or team_b is None:
            continue
        if pick_team == team_a:
            opponent = team_b
        elif pick_team == team_b:
            opponent = team_a
        else:
            continue
        hypo_results = what_if(hypo_results, slot_id, pick_team, opponent)
        clinch_outcomes.append({"slot_id": slot_id, "required_winner": pick_team})

    if not clinch_outcomes:
        return {
            "clinched": False,
            "clinch_outcomes": None,
            "can_win": True,
            "min_picks_needed": _min_picks_to_lead(player_scored, max_other_current, tournament),
        }

    # Re-score all players in the hypothetical
    hypo_scored = {e.player_name: score_entry(e, tournament, hypo_results) for e in entries}
    player_hypo = hypo_scored[player_name]
    other_hypo_max = max(
        (s.max_possible for name, s in hypo_scored.items() if name != player_name),
        default=0,
    )

    if player_hypo.total_points > other_hypo_max:
        return {
            "clinched": False,
            "clinch_outcomes": clinch_outcomes,
            "can_win": True,
            "min_picks_needed": len(clinch_outcomes),
        }
    return {
        "clinched": False,
        "clinch_outcomes": None,
        "can_win": True,
        "min_picks_needed": _min_picks_to_lead(player_scored, max_other_current, tournament),
    }


def _min_picks_to_lead(
    player_scored,
    max_other_current: float,
    tournament: TournamentStructure,
) -> int:
    """Minimum correct pending picks for player's score to exceed max_other_current."""
    gap = max_other_current - player_scored.total_points
    if gap <= 0:
        return 0
    pending_values = sorted(
        [POINTS_PER_ROUND[tournament.slots[sid].round]
         for sid in player_scored.pending_picks],
        reverse=True,
    )
    count = 0
    accumulated = 0
    for v in pending_values:
        accumulated += v
        count += 1
        if accumulated > gap:
            return count
    return len(pending_values) + 1  # can't close the gap


def best_path(
    sr: ScenarioResults,
    player_name: str,
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    odds: dict | None = None,
) -> dict:
    """Find the outcome combination that maximizes a player's win probability.

    Returns dict with:
      - steps: list[dict]  — ordered by round ascending:
            {slot_id, round, root_for, opponent}
      - win_probability: float  — player's overall win % (unconditional)
      - path_probability: float  — probability of this specific outcome combo
      - odds_source: str  — lowest-confidence source used
    """
    total = sr.total_scenarios
    win_probability = sr.win_counts.get(player_name, 0) / total if total > 0 else 0.0

    if sr.is_eliminated.get(player_name, True):
        return {
            "steps": [],
            "win_probability": win_probability,
            "path_probability": 0.0,
            "odds_source": "coin_flip",
        }

    player_entry = next((e for e in entries if e.player_name == player_name), None)
    if not player_entry:
        return {"steps": [], "win_probability": win_probability, "path_probability": 0.0, "odds_source": "coin_flip"}

    rounds_of_slots = _get_remaining_slots_by_round(tournament, results)
    if not rounds_of_slots:
        return {"steps": [], "win_probability": win_probability, "path_probability": 1.0, "odds_source": "coin_flip"}

    # For brute-force engine (small N): enumerate all winning scenarios
    if sr.engine == "brute_force":
        return _best_path_brute_force(
            sr, player_name, entries, tournament, results, odds,
            rounds_of_slots, win_probability,
        )

    # For Monte Carlo (large N): greedy approach using per-player swings
    return _best_path_greedy(sr, player_name, tournament, results, odds, win_probability)


def _best_path_brute_force(
    sr: ScenarioResults,
    player_name: str,
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
    odds: dict | None,
    rounds_of_slots: list[list[str]],
    win_probability: float,
) -> dict:
    """Enumerate all scenarios and return the best winning path."""
    all_scenarios = _simulate_tournament_brute_force(tournament, results, rounds_of_slots)
    all_remaining = [sid for round_slots in rounds_of_slots for sid in round_slots]

    best_prob = -1.0
    best_outcome_map = None
    best_sources: list[str] = []

    for hypo_results in all_scenarios:
        hypo = Results(last_updated="", results=hypo_results)
        scores = sorted(
            [(e.player_name, score_entry(e, tournament, hypo).total_points) for e in entries],
            key=lambda x: -x[1],
        )
        if not scores or scores[0][0] != player_name:
            continue

        # Player wins this scenario — compute its probability
        path_prob = 1.0
        sources: list[str] = []
        for sid in all_remaining:
            result_gr = hypo_results.get(sid)
            if not result_gr:
                continue
            team_a, team_b = _resolve_participants(tournament, hypo_results, sid)
            if team_a is None or team_b is None:
                continue
            gp = get_game_probability(team_a, team_b, tournament, odds, sid)
            game_prob = gp.prob_a if result_gr.winner == team_a else 1.0 - gp.prob_a
            path_prob *= game_prob
            sources.append(gp.source)

        if path_prob > best_prob:
            best_prob = path_prob
            best_outcome_map = hypo_results
            best_sources = sources

    if best_outcome_map is None:
        return {"steps": [], "win_probability": win_probability, "path_probability": 0.0, "odds_source": "coin_flip"}

    steps = _build_steps(best_outcome_map, all_remaining, tournament)
    return {
        "steps": steps,
        "win_probability": win_probability,
        "path_probability": best_prob,
        "odds_source": _lowest_confidence(best_sources),
    }


def _best_path_greedy(
    sr: ScenarioResults,
    player_name: str,
    tournament: TournamentStructure,
    results: Results,
    odds: dict | None,
    win_probability: float,
) -> dict:
    """Greedy best-path for Monte Carlo: pick the favorable outcome per critical game."""
    pcg = player_critical_games(sr, player_name, top_n=15)
    steps = []
    path_prob = 1.0
    sources: list[str] = []

    for game in pcg:
        slot = tournament.slots[game["slot_id"]]
        if game["win_if_a"] >= game["win_if_b"]:
            root_for, opponent = game["team_a"], game["team_b"]
        else:
            root_for, opponent = game["team_b"], game["team_a"]
        gp = get_game_probability(game["team_a"], game["team_b"], tournament, odds, game["slot_id"])
        game_prob = gp.prob_a if root_for == game["team_a"] else 1.0 - gp.prob_a
        path_prob *= game_prob
        sources.append(gp.source)
        steps.append({
            "slot_id": game["slot_id"],
            "round": slot.round,
            "root_for": root_for,
            "opponent": opponent,
        })

    steps.sort(key=lambda s: s["round"])
    return {
        "steps": steps,
        "win_probability": win_probability,
        "path_probability": path_prob,
        "odds_source": _lowest_confidence(sources),
    }


def _build_steps(
    outcome_map: dict,
    all_remaining: list[str],
    tournament: TournamentStructure,
) -> list[dict]:
    """Build sorted step list from a scenario outcome dict."""
    steps = []
    for sid in all_remaining:
        result_gr = outcome_map.get(sid)
        if not result_gr:
            continue
        slot = tournament.slots[sid]
        steps.append({
            "slot_id": sid,
            "round": slot.round,
            "root_for": result_gr.winner,
            "opponent": result_gr.loser,
        })
    steps.sort(key=lambda s: s["round"])
    return steps


def _lowest_confidence(sources: list[str]) -> str:
    """Return the lowest-confidence probability source from a list."""
    order = ["coin_flip", "seed_historical", "spread", "moneyline"]
    if not sources:
        return "coin_flip"
    return min(sources, key=lambda s: order.index(s) if s in order else -1)


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
