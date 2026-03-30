"""Tests for core/tournament.py and core/scenarios.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import load_entries, load_results, load_tournament
from core.scenarios import brute_force_scenarios, monte_carlo_scenarios, run_scenarios, what_if
from core.tournament import (
    get_participants_for_slot,
    get_remaining_games,
    get_remaining_slots,
    get_team_path,
)


@pytest.fixture
def data_dir():
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def tournament(data_dir):
    return load_tournament(data_dir / "tournament.json")


@pytest.fixture
def results(data_dir):
    return load_results(data_dir / "results.json")


@pytest.fixture
def entries(data_dir):
    return load_entries(data_dir / "entries" / "player_brackets.json")


# --- Tournament utility tests ---


class TestRemainingSlots:
    def test_counts_remaining(self, tournament, results):
        """With 5/7 games done, 2 should remain."""
        remaining = get_remaining_slots(tournament, results)
        assert len(remaining) == 2

    def test_remaining_slots_are_correct(self, tournament, results):
        remaining = get_remaining_slots(tournament, results)
        assert "r2_west_1" in remaining
        assert "championship" in remaining


class TestParticipants:
    def test_r1_has_seeded_teams(self, tournament, results):
        team_a, team_b = get_participants_for_slot(tournament, results, "r1_east_1v4")
        assert team_a == "duke"
        assert team_b == "purdue"

    def test_r2_has_winners(self, tournament, results):
        """R2 West should have Houston and Alabama (R1 winners)."""
        team_a, team_b = get_participants_for_slot(tournament, results, "r2_west_1")
        assert set([team_a, team_b]) == {"houston", "alabama"}

    def test_championship_partial(self, tournament, results):
        """Championship: East winner (Duke) known, West winner unknown."""
        team_a, team_b = get_participants_for_slot(tournament, results, "championship")
        # One should be duke (East winner), other None (West not played)
        participants = {team_a, team_b}
        assert "duke" in participants
        assert None in participants


class TestTeamPath:
    def test_duke_path(self, tournament):
        path = get_team_path(tournament, "duke")
        assert path[0] == "r1_east_1v4"
        assert path[-1] == "championship"
        assert len(path) == 3  # R1, R2, Championship

    def test_unknown_team_empty_path(self, tournament):
        path = get_team_path(tournament, "nonexistent")
        assert path == []


class TestRemainingGames:
    def test_remaining_games_structure(self, tournament, results):
        games = get_remaining_games(tournament, results)
        assert len(games) == 2
        for g in games:
            assert "slot_id" in g
            assert "team_a" in g
            assert "team_b" in g


# --- Brute force tests ---


class TestBruteForce:
    def test_total_scenarios(self, entries, tournament, results):
        """With 2 remaining games (1 actionable), should have correct scenario count."""
        sr = brute_force_scenarios(entries, tournament, results)
        # r2_west_1 is actionable (houston vs alabama)
        # championship depends on r2_west_1, so only 1 is actionable at first
        # Actually both teams are known for r2_west_1 (houston, alabama)
        # But championship needs r2_west_1 winner + duke — r2_west_1 not played yet
        # So championship's team_b is None -> not actionable
        # Only r2_west_1 is actionable -> 2^1 = 2 scenarios
        assert sr.total_scenarios == 2

    def test_all_players_have_win_counts(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        assert len(sr.win_counts) == len(entries)

    def test_win_counts_sum_to_total(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        assert sum(sr.win_counts.values()) == sr.total_scenarios

    def test_charlie_favored(self, entries, tournament, results):
        """Charlie has 60 pts and picked Houston for r2_west_1.
        If Houston wins: Charlie gets +20 = 80 pts.
        If Alabama wins: Charlie stays at 60 but Bob gets +20 = 40.
        Charlie leads in both scenarios.
        """
        sr = brute_force_scenarios(entries, tournament, results)
        assert sr.win_counts["Charlie"] == sr.total_scenarios  # Charlie wins all

    def test_elimination_detected(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        # If Charlie wins every scenario, everyone else is eliminated
        for name, eliminated in sr.is_eliminated.items():
            if name == "Charlie":
                assert not eliminated
            else:
                assert eliminated

    def test_has_critical_games(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        # Should have at least 1 critical game
        assert len(sr.critical_games) >= 1


# --- Monte Carlo tests ---


class TestMonteCarlo:
    def test_runs_without_error(self, entries, tournament, results):
        sr = monte_carlo_scenarios(
            entries, tournament, results,
            n_simulations=1000, seed=42,
        )
        assert sr.total_scenarios == 1000
        assert sr.engine == "monte_carlo"

    def test_win_counts_sum(self, entries, tournament, results):
        sr = monte_carlo_scenarios(
            entries, tournament, results,
            n_simulations=1000, seed=42,
        )
        assert sum(sr.win_counts.values()) == 1000

    def test_deterministic_with_seed(self, entries, tournament, results):
        sr1 = monte_carlo_scenarios(
            entries, tournament, results,
            n_simulations=500, seed=123,
        )
        sr2 = monte_carlo_scenarios(
            entries, tournament, results,
            n_simulations=500, seed=123,
        )
        assert sr1.win_counts == sr2.win_counts


# --- Auto-select engine tests ---


class TestRunScenarios:
    def test_selects_brute_force_for_small(self, entries, tournament, results):
        sr = run_scenarios(entries, tournament, results, brute_force_threshold=15)
        assert sr.engine == "brute_force"

    def test_selects_monte_carlo_when_forced(self, entries, tournament, results):
        sr = run_scenarios(entries, tournament, results, brute_force_threshold=0)
        assert sr.engine == "monte_carlo"


# --- What-if tests ---


class TestWhatIf:
    def test_adds_result(self, results):
        new = what_if(results, "r2_west_1", "houston", "alabama")
        assert new.is_complete("r2_west_1")
        assert new.winner_of("r2_west_1") == "houston"
        # Original unchanged
        assert not results.is_complete("r2_west_1")

    def test_preserves_existing(self, results):
        new = what_if(results, "r2_west_1", "houston", "alabama")
        # Existing results still there
        assert new.winner_of("r1_east_1v4") == "duke"
        assert new.completed_count() == results.completed_count() + 1
