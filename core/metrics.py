"""Derived competitive metrics for bracket intelligence.

Goes beyond raw scoring to quantify competitive position:
- Separation Index: fraction of remaining upside unique to one player
- Threat classification: which other brackets pose the biggest risk
- Outcome labels: classifying each game outcome by strategic type

Pure business logic — no Streamlit imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from core.models import PlayerEntry, Results, TournamentStructure
from core.scenarios import ScenarioResults
from core.scoring import POINTS_PER_ROUND, ScoredEntry, get_alive_teams


class OutcomeLabel(str, Enum):
    FATAL = "fatal"              # this outcome eliminates the user's path to 1st
    SURVIVAL = "survival"        # this outcome reopens the user's path to 1st
    SEPARATION = "separation"    # distinctly helps user more than the field
    SHARED_NEUTRAL = "shared_neutral"  # helps but doesn't differentiate
    BLOCKING = "blocking"        # benefits a rival significantly more than the user


@dataclass
class OutcomeEffect:
    """Effect of one specific game outcome on a specific player."""
    slot_id: str
    team: str            # the team that wins in this outcome
    opponent: str        # the team that loses
    win_equity_delta: float  # change in pool-win probability if this team wins
    label: OutcomeLabel
    note: str            # plain-English explanation


@dataclass
class ThreatProfile:
    """How threatening another player's bracket is to a target user."""
    other_player: str
    threat_type: str     # "Direct Threat", "Shadow Twin", "Fragile Leader", "Long-Shot Disruptor"
    score_gap: int       # positive = they lead user, negative = user leads them
    overlap_pct: float   # fraction of live picks that match the user's
    separation: float    # their separation index (0-1)
    p_beats_user: float  # probability they finish ahead of user (from scenarios)
    threat_level: float  # composite 0-1


# --- Separation Index ---

def separation_index(
    entry: PlayerEntry,
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> float:
    """Fraction of remaining live upside that no other player shares.

    1.0 = fully differentiated (all remaining picks are unique)
    0.0 = no differentiation (every remaining pick is duplicated by someone else)
    """
    alive = get_alive_teams(tournament, results)
    completed = set(results.results.keys())

    unique_pts = 0
    total_pts = 0

    for slot_id in tournament.slot_order:
        if slot_id in completed:
            continue
        team = entry.picks.get(slot_id)
        if not team or team not in alive:
            continue

        pts = POINTS_PER_ROUND.get(tournament.slots[slot_id].round, 0)
        total_pts += pts

        others_have = any(
            e.player_name != entry.player_name and e.picks.get(slot_id) == team
            for e in entries
        )
        if not others_have:
            unique_pts += pts

    return unique_pts / total_pts if total_pts > 0 else 0.0


def separation_index_all(
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> dict[str, float]:
    """Compute separation index for all players."""
    return {
        e.player_name: separation_index(e, entries, tournament, results)
        for e in entries
    }


# --- Pairwise Beat Probability ---

def pairwise_beat_probability(
    scenario_results: ScenarioResults,
    player_a: str,
    player_b: str,
) -> float:
    """Probability that player_a finishes ahead of player_b.

    Uses exact pairwise_wins tracking from the scenario engine when available.
    Falls back to finish-distribution rank approximation.
    """
    total = scenario_results.total_scenarios
    if total == 0:
        return 0.5

    if scenario_results.pairwise_wins:
        wins = scenario_results.pairwise_wins.get((player_a, player_b), 0)
        return wins / total

    # Approximation: use average rank from finish distributions
    dist_a = scenario_results.finish_distributions.get(player_a, {})
    dist_b = scenario_results.finish_distributions.get(player_b, {})

    avg_a = sum(pos * cnt for pos, cnt in dist_a.items()) / total if dist_a else 99.0
    avg_b = sum(pos * cnt for pos, cnt in dist_b.items()) / total if dist_b else 99.0

    if avg_a == avg_b:
        return 0.5
    # Lower average rank = finishes higher more often
    return avg_b / (avg_a + avg_b) if (avg_a + avg_b) > 0 else 0.5


# --- Live Overlap ---

def _live_overlap(
    entry_a: PlayerEntry,
    entry_b: PlayerEntry,
    tournament: TournamentStructure,
    results: Results,
    alive: set[str],
) -> tuple[int, int]:
    """Count (shared_live_picks, total_live_slots).

    A slot is "live" if it hasn't been played AND at least one player's pick
    for that slot is still in the tournament.
    """
    completed = set(results.results.keys())
    shared = 0
    total = 0

    for slot_id in tournament.slot_order:
        if slot_id in completed:
            continue
        pa = entry_a.picks.get(slot_id)
        pb = entry_b.picks.get(slot_id)
        a_alive = pa in alive if pa else False
        b_alive = pb in alive if pb else False
        if a_alive or b_alive:
            total += 1
        if pa and pb and pa == pb and a_alive:
            shared += 1

    return shared, total


# --- Threat Classification ---

def classify_threats(
    user_name: str,
    entries: list[PlayerEntry],
    scored_entries: dict[str, ScoredEntry],
    scenario_results: ScenarioResults,
    tournament: TournamentStructure,
    results: Results,
) -> list[ThreatProfile]:
    """Classify each other player as a threat type to the user.

    Returns list sorted by threat_level descending (most dangerous first).

    Types:
    - Shadow Twin: very similar bracket, close score — tied to your fate
    - Direct Threat: close score, divergent picks — can independently outrun you
    - Fragile Leader: ahead but low unique upside — catchable
    - Long-Shot Disruptor: behind but unique high-upside picks — late surge risk
    """
    user_entry = next(e for e in entries if e.player_name == user_name)
    user_scored = scored_entries[user_name]
    alive = get_alive_teams(tournament, results)
    separations = separation_index_all(entries, tournament, results)

    threats = []

    for other_entry in entries:
        if other_entry.player_name == user_name:
            continue

        other_name = other_entry.player_name
        other_scored = scored_entries[other_name]
        score_gap = other_scored.total_points - user_scored.total_points
        other_sep = separations[other_name]

        shared, total_live = _live_overlap(
            user_entry, other_entry, tournament, results, alive
        )
        overlap_pct = shared / total_live if total_live > 0 else 0.0

        p_beats = pairwise_beat_probability(scenario_results, other_name, user_name)

        is_ahead = score_gap > 0

        # Classify threat type
        if overlap_pct >= 0.70 and abs(score_gap) <= 100:
            threat_type = "Shadow Twin"
            # Highly similar brackets — outcomes are correlated, whoever is ahead tends to stay ahead
            base_threat = 0.65 + (0.25 * max(0.0, 1.0 - abs(score_gap) / 200))
        elif not is_ahead and other_sep > 0.45 and other_scored.max_possible > user_scored.total_points:
            threat_type = "Long-Shot Disruptor"
            # Behind but unique high-upside picks — could surge if their longshots land
            base_threat = 0.25 + (0.30 * other_sep)
        elif is_ahead and other_sep < 0.25 and other_scored.max_possible - user_scored.max_possible < 100:
            threat_type = "Fragile Leader"
            # Ahead now but limited unique upside — can be caught
            base_threat = 0.50 + (0.25 * min(1.0, score_gap / 120))
        else:
            threat_type = "Direct Threat"
            # The standard case: close enough in score to be dangerous
            base_threat = max(0.10, 0.80 - (abs(score_gap) / 400))

        # Weight base structural threat with scenario-derived probability
        threat_level = 0.55 * base_threat + 0.45 * p_beats

        threats.append(ThreatProfile(
            other_player=other_name,
            threat_type=threat_type,
            score_gap=score_gap,
            overlap_pct=overlap_pct,
            separation=other_sep,
            p_beats_user=p_beats,
            threat_level=threat_level,
        ))

    threats.sort(key=lambda t: -t.threat_level)
    return threats


# --- Outcome Labels ---

def label_outcomes(
    user_name: str,
    scenario_results: ScenarioResults,
    entries: list[PlayerEntry],
) -> list[OutcomeEffect]:
    """Label each remaining game outcome for a specific user.

    For each game in critical_games, produces two OutcomeEffect entries —
    one for each possible winner — each labeled by strategic type.
    """
    if not scenario_results.critical_games:
        return []

    total = scenario_results.total_scenarios
    if total == 0:
        return []

    user_base = scenario_results.win_counts.get(user_name, 0) / total
    n_others = len(entries) - 1

    effects = []

    for cg in scenario_results.critical_games:
        user_swings = cg.swings.get(user_name)
        if not user_swings:
            continue

        win_if_a, win_if_b = user_swings

        for team, opp, user_win_if in [
            (cg.team_a, cg.team_b, win_if_a),
            (cg.team_b, cg.team_a, win_if_b),
        ]:
            delta = user_win_if - user_base

            # Compute average and max other-player delta for this outcome
            other_deltas = []
            for name, swings in cg.swings.items():
                if name == user_name:
                    continue
                other_base = scenario_results.win_counts.get(name, 0) / total
                other_win_if = swings[0] if team == cg.team_a else swings[1]
                other_deltas.append(other_win_if - other_base)

            avg_other_delta = sum(other_deltas) / len(other_deltas) if other_deltas else 0.0
            max_rival_gain = max(other_deltas) if other_deltas else 0.0

            # Label the outcome
            if user_win_if == 0.0 and user_base > 0.0:
                label = OutcomeLabel.FATAL
                note = "Eliminates your path to 1st place"
            elif user_base == 0.0 and user_win_if > 0.0:
                label = OutcomeLabel.SURVIVAL
                note = "Reopens your path to 1st place"
            elif delta >= 0.04 and delta > avg_other_delta * 1.4:
                label = OutcomeLabel.SEPARATION
                note = "Helps you significantly more than the rest of the field"
            elif delta >= 0.02 and abs(delta - avg_other_delta) < 0.02:
                label = OutcomeLabel.SHARED_NEUTRAL
                note = "Helps you, but helps the field about as much"
            elif delta <= -0.04 and max_rival_gain > abs(delta) * 0.5:
                label = OutcomeLabel.BLOCKING
                note = "Boosts your rivals more than it hurts you directly"
            elif delta <= -0.04:
                label = OutcomeLabel.FATAL
                note = "Significantly reduces your pool-win chances"
            elif abs(delta) < 0.02:
                label = OutcomeLabel.SHARED_NEUTRAL
                note = "Minimal impact on your standing"
            else:
                label = OutcomeLabel.SHARED_NEUTRAL
                note = "Modest effect — affects the whole field similarly"

            effects.append(OutcomeEffect(
                slot_id=cg.slot_id,
                team=team,
                opponent=opp,
                win_equity_delta=delta,
                label=label,
                note=note,
            ))

    return effects


# --- Shared Upside vs Unique Upside ---

def shared_vs_unique_upside(
    entry: PlayerEntry,
    entries: list[PlayerEntry],
    tournament: TournamentStructure,
    results: Results,
) -> tuple[int, int]:
    """Return (shared_remaining_pts, unique_remaining_pts) for a player.

    Shared = remaining points from picks that at least one other player also has.
    Unique = remaining points from picks nobody else in the pool has.
    """
    alive = get_alive_teams(tournament, results)
    completed = set(results.results.keys())

    shared_pts = 0
    unique_pts = 0

    for slot_id in tournament.slot_order:
        if slot_id in completed:
            continue
        team = entry.picks.get(slot_id)
        if not team or team not in alive:
            continue

        pts = POINTS_PER_ROUND.get(tournament.slots[slot_id].round, 0)
        others_have = any(
            e.player_name != entry.player_name and e.picks.get(slot_id) == team
            for e in entries
        )
        if others_have:
            shared_pts += pts
        else:
            unique_pts += pts

    return shared_pts, unique_pts
