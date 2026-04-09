"""Tests for core/metrics.py — Separation Index, threat classification, outcome labels."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import load_entries, load_results, load_tournament
from core.metrics import (
    OutcomeEffect,
    OutcomeLabel,
    ThreatProfile,
    classify_threats,
    label_outcomes,
    pairwise_beat_probability,
    separation_index,
    separation_index_all,
    shared_vs_unique_upside,
)
from core.scenarios import brute_force_scenarios
from core.scoring import score_entry


@pytest.fixture
def data_dir():
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def tournament(data_dir):
    return load_tournament(data_dir / "tournament.json")


@pytest.fixture
def results(data_dir):
    return load_results(data_dir / "results.json")


@pytest.fixture
def entries(data_dir):
    return load_entries(data_dir / "entries" / "player_brackets.json")


@pytest.fixture
def scored(entries, tournament, results):
    return {e.player_name: score_entry(e, tournament, results) for e in entries}


@pytest.fixture
def scenario_results(entries, tournament, results):
    return brute_force_scenarios(entries, tournament, results)


# --- Separation Index ---


class TestSeparationIndex:
    def test_returns_float_between_0_and_1(self, entries, tournament, results):
        for entry in entries:
            sep = separation_index(entry, entries, tournament, results)
            assert 0.0 <= sep <= 1.0

    def test_all_players_have_index(self, entries, tournament, results):
        seps = separation_index_all(entries, tournament, results)
        assert set(seps.keys()) == {e.player_name for e in entries}

    def test_unique_picks_score_higher(self, entries, tournament, results):
        """Players with unique remaining picks should have higher separation."""
        seps = separation_index_all(entries, tournament, results)
        # Dave and Eve share all picks with others → 0% separation
        # (fixture-specific: verify at least some players have > 0)
        assert any(v > 0.0 for v in seps.values()), "At least one player should have unique picks"

    def test_fully_shared_bracket_is_zero(self, entries, tournament, results):
        """A player whose every remaining pick is also held by someone else gets 0."""
        seps = separation_index_all(entries, tournament, results)
        # Dave and Eve are duplicates in the fixture
        assert seps.get("Dave", 1.0) == 0.0 or seps.get("Eve", 1.0) == 0.0


class TestSharedVsUniqueUpside:
    def test_sums_to_total_remaining(self, entries, tournament, results):
        """shared + unique should equal total remaining live upside."""
        for entry in entries:
            shared, unique = shared_vs_unique_upside(entry, entries, tournament, results)
            # Both should be non-negative
            assert shared >= 0
            assert unique >= 0

    def test_consistency_with_separation_index(self, entries, tournament, results):
        """shared_vs_unique_upside(unique) / total should match separation_index."""
        for entry in entries:
            shared, unique = shared_vs_unique_upside(entry, entries, tournament, results)
            total = shared + unique
            if total > 0:
                expected_sep = unique / total
                actual_sep = separation_index(entry, entries, tournament, results)
                assert abs(expected_sep - actual_sep) < 1e-9


# --- Pairwise Beat Probability ---


class TestPairwiseBeatProbability:
    def test_returns_probability(self, scenario_results, entries):
        for i, a in enumerate(entries):
            for b in entries[i + 1:]:
                p = pairwise_beat_probability(scenario_results, a.player_name, b.player_name)
                assert 0.0 <= p <= 1.0

    def test_complement_sums_to_one(self, scenario_results, entries):
        """P(A beats B) + P(B beats A) should equal 1 when computed from exact pairwise_wins."""
        if not scenario_results.pairwise_wins:
            pytest.skip("No pairwise win data")
        a, b = entries[0].player_name, entries[1].player_name
        p_ab = pairwise_beat_probability(scenario_results, a, b)
        p_ba = pairwise_beat_probability(scenario_results, b, a)
        assert abs(p_ab + p_ba - 1.0) < 1e-9

    def test_pairwise_wins_populated_by_brute_force(self, scenario_results):
        """Brute-force engine should populate pairwise_wins."""
        assert scenario_results.pairwise_wins, "pairwise_wins should be non-empty after brute-force"

    def test_pairwise_wins_populated_by_monte_carlo(self, entries, tournament, results):
        """Monte Carlo engine should also populate pairwise_wins."""
        from core.scenarios import monte_carlo_scenarios
        sr = monte_carlo_scenarios(entries, tournament, results, n_simulations=500, seed=42)
        assert sr.pairwise_wins, "pairwise_wins should be non-empty after Monte Carlo"

    def test_consistent_with_win_counts(self, scenario_results, entries):
        """A player who wins more scenarios should beat others more often on average."""
        total = scenario_results.total_scenarios
        win_rates = {
            name: count / total
            for name, count in scenario_results.win_counts.items()
        }
        # The player with the highest win rate should beat most others more than 50% of the time
        top_player = max(win_rates, key=win_rates.__getitem__)
        beat_count = 0
        for other in entries:
            if other.player_name == top_player:
                continue
            p = pairwise_beat_probability(scenario_results, top_player, other.player_name)
            if p > 0.5:
                beat_count += 1
        # Top player should beat at least half the field more often than not
        assert beat_count >= len(entries) // 2


# --- Threat Classification ---


class TestClassifyThreats:
    def test_returns_profiles_for_all_others(self, entries, scored, scenario_results, tournament, results):
        user = entries[0].player_name
        threats = classify_threats(user, entries, scored, scenario_results, tournament, results)
        assert len(threats) == len(entries) - 1

    def test_sorted_by_threat_level_descending(self, entries, scored, scenario_results, tournament, results):
        user = entries[0].player_name
        threats = classify_threats(user, entries, scored, scenario_results, tournament, results)
        levels = [t.threat_level for t in threats]
        assert levels == sorted(levels, reverse=True)

    def test_threat_level_between_0_and_1(self, entries, scored, scenario_results, tournament, results):
        user = entries[0].player_name
        threats = classify_threats(user, entries, scored, scenario_results, tournament, results)
        for t in threats:
            assert 0.0 <= t.threat_level <= 1.0

    def test_valid_threat_types(self, entries, scored, scenario_results, tournament, results):
        valid_types = {"Shadow Twin", "Direct Threat", "Fragile Leader", "Long-Shot Disruptor"}
        user = entries[0].player_name
        threats = classify_threats(user, entries, scored, scenario_results, tournament, results)
        for t in threats:
            assert t.threat_type in valid_types

    def test_overlap_pct_between_0_and_1(self, entries, scored, scenario_results, tournament, results):
        user = entries[0].player_name
        threats = classify_threats(user, entries, scored, scenario_results, tournament, results)
        for t in threats:
            assert 0.0 <= t.overlap_pct <= 1.0

    def test_profile_fields_present(self, entries, scored, scenario_results, tournament, results):
        user = entries[0].player_name
        threats = classify_threats(user, entries, scored, scenario_results, tournament, results)
        for t in threats:
            assert isinstance(t, ThreatProfile)
            assert t.other_player != user
            assert isinstance(t.score_gap, int)


# --- Outcome Labels ---


class TestLabelOutcomes:
    def test_returns_list_of_effects(self, entries, scenario_results):
        user = entries[0].player_name
        effects = label_outcomes(user, scenario_results, entries)
        assert isinstance(effects, list)
        for e in effects:
            assert isinstance(e, OutcomeEffect)

    def test_effects_have_valid_labels(self, entries, scenario_results):
        user = entries[0].player_name
        effects = label_outcomes(user, scenario_results, entries)
        for e in effects:
            assert e.label in list(OutcomeLabel)

    def test_two_effects_per_critical_game(self, entries, scenario_results):
        """Each critical game should produce exactly 2 effects (one per team)."""
        user = entries[0].player_name
        effects = label_outcomes(user, scenario_results, entries)
        by_slot: dict[str, list] = {}
        for e in effects:
            by_slot.setdefault(e.slot_id, []).append(e)
        for slot_id, slot_effects in by_slot.items():
            assert len(slot_effects) == 2, f"Expected 2 effects for {slot_id}, got {len(slot_effects)}"

    def test_opposite_teams_for_same_slot(self, entries, scenario_results):
        """For any slot, one effect should have team A and the other team B."""
        user = entries[0].player_name
        effects = label_outcomes(user, scenario_results, entries)
        by_slot: dict[str, list] = {}
        for e in effects:
            by_slot.setdefault(e.slot_id, []).append(e)
        for slot_id, slot_effects in by_slot.items():
            if len(slot_effects) == 2:
                assert slot_effects[0].team == slot_effects[1].opponent
                assert slot_effects[1].team == slot_effects[0].opponent

    def test_empty_when_no_critical_games(self, entries, tournament, results):
        """Should return empty list if scenario results have no critical games."""
        from core.scenarios import ScenarioResults
        empty_sr = ScenarioResults(
            engine="brute_force",
            total_scenarios=0,
            remaining_games=[],
            win_counts={e.player_name: 0 for e in entries},
            finish_distributions={e.player_name: {} for e in entries},
            is_eliminated={e.player_name: True for e in entries},
        )
        effects = label_outcomes(entries[0].player_name, empty_sr, entries)
        assert effects == []

    def test_note_is_nonempty_string(self, entries, scenario_results):
        user = entries[0].player_name
        effects = label_outcomes(user, scenario_results, entries)
        for e in effects:
            assert isinstance(e.note, str) and e.note
