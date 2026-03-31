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
        """With 2 remaining games resolved round-by-round, should have 4 scenarios.

        Round 2: r2_west_1 (houston vs alabama) -> 2 outcomes
        Round 3: championship (duke vs r2_west_1 winner) -> 2 outcomes each
        Total: 2 * 2 = 4 scenarios
        """
        sr = brute_force_scenarios(entries, tournament, results)
        assert sr.total_scenarios == 4

    def test_all_players_have_win_counts(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        assert len(sr.win_counts) == len(entries)

    def test_win_counts_sum_to_total(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        assert sum(sr.win_counts.values()) == sr.total_scenarios

    def test_championship_matters(self, entries, tournament, results):
        """With championship included, Alice wins when Duke wins the championship.

        Scenario breakdown (4 total):
        - Houston wins r2, Duke wins champ: Alice=100, Charlie=80 -> Alice wins
        - Houston wins r2, Houston wins champ: Charlie=120, Alice=60 -> Charlie wins
        - Alabama wins r2, Duke wins champ: Alice=80, Charlie=60 -> Alice wins
        - Alabama wins r2, Alabama wins champ: Bob=80, Charlie=60 -> Bob wins

        So: Alice=2, Charlie=1, Bob=1
        """
        sr = brute_force_scenarios(entries, tournament, results)
        assert sr.win_counts["Alice"] == 2
        assert sr.win_counts["Charlie"] == 1
        assert sr.win_counts["Bob"] == 1

    def test_elimination_detected(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        # Dave and Eve can't win any scenario
        assert sr.is_eliminated["Dave"]
        assert sr.is_eliminated["Eve"]
        # Alice, Charlie, Bob each win at least one scenario
        assert not sr.is_eliminated["Alice"]
        assert not sr.is_eliminated["Charlie"]
        assert not sr.is_eliminated["Bob"]

    def test_has_critical_games(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        # r2_west_1 has a fixed matchup so it appears as a critical game.
        # Championship matchup varies by scenario so it may not appear.
        assert len(sr.critical_games) >= 1
        assert sr.critical_games[0].slot_id == "r2_west_1"


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
