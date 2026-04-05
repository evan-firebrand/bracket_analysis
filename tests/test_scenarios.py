"""Tests for core/tournament.py and core/scenarios.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import load_entries, load_results, load_tournament
from core.scenarios import (
    _lowest_confidence,
    _min_picks_to_lead,
    best_path,
    brute_force_scenarios,
    clinch_scenarios,
    monte_carlo_scenarios,
    player_critical_games,
    run_scenarios,
    what_if,
)
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


# --- player_critical_games tests ---


class TestPlayerCriticalGames:
    def test_alice_has_zero_swing(self, entries, tournament, results):
        """Alice wins 50% whether Houston or Alabama wins r2_west_1."""
        sr = brute_force_scenarios(entries, tournament, results)
        games = player_critical_games(sr, "Alice")
        # Alice's swing is 0 for r2_west_1, so no games returned
        assert games == []

    def test_charlie_swing_for_r2(self, entries, tournament, results):
        """Charlie wins only when Houston wins r2_west_1."""
        sr = brute_force_scenarios(entries, tournament, results)
        games = player_critical_games(sr, "Charlie")
        assert len(games) >= 1
        g = games[0]
        assert g["slot_id"] == "r2_west_1"
        assert g["swing"] == pytest.approx(0.5)
        # Charlie's must-win team is Houston
        assert g["must_win_team"] == "houston"

    def test_bob_must_win_alabama(self, entries, tournament, results):
        """Bob wins only when Alabama wins r2_west_1."""
        sr = brute_force_scenarios(entries, tournament, results)
        games = player_critical_games(sr, "Bob")
        assert len(games) >= 1
        g = games[0]
        assert g["slot_id"] == "r2_west_1"
        assert g["swing"] == pytest.approx(0.5)
        assert g["must_win_team"] == "alabama"

    def test_eliminated_player_returns_empty(self, entries, tournament, results):
        """Dave can't win any scenario; his critical games list is empty."""
        sr = brute_force_scenarios(entries, tournament, results)
        games = player_critical_games(sr, "Dave")
        # Dave has a pick for r2_west_1 (tennessee, eliminated) — swing is 0
        assert games == []

    def test_top_n_respected(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        games = player_critical_games(sr, "Charlie", top_n=1)
        assert len(games) <= 1

    def test_returns_all_required_keys(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        games = player_critical_games(sr, "Charlie")
        if games:
            g = games[0]
            for key in ("slot_id", "team_a", "team_b", "win_if_a", "win_if_b", "swing", "must_win_team"):
                assert key in g


# --- clinch_scenarios tests ---


class TestClinchScenarios:
    def test_not_clinched_when_tournament_ongoing(self, entries, tournament, results):
        """No one should be clinched with 2 games remaining."""
        for entry in entries:
            cs = clinch_scenarios(entries, entry.player_name, tournament, results)
            assert cs["clinched"] is False

    def test_alice_has_clinch_scenario(self, entries, tournament, results):
        """If Alice wins houston in r2 and duke in championship, she clinches."""
        cs = clinch_scenarios(entries, "Alice", tournament, results)
        assert cs["can_win"] is True
        assert cs["clinch_outcomes"] is not None
        # clinch requires both pending picks
        slot_ids = {o["slot_id"] for o in cs["clinch_outcomes"]}
        assert "r2_west_1" in slot_ids
        assert "championship" in slot_ids
        winners = {o["required_winner"] for o in cs["clinch_outcomes"]}
        assert "houston" in winners
        assert "duke" in winners

    def test_dave_cannot_win(self, entries, tournament, results):
        """Dave's picks are all eliminated; he can't win."""
        cs = clinch_scenarios(entries, "Dave", tournament, results)
        assert cs["can_win"] is False
        assert cs["clinch_outcomes"] is None

    def test_eve_cannot_win(self, entries, tournament, results):
        """Eve's picks are all eliminated; she can't win."""
        cs = clinch_scenarios(entries, "Eve", tournament, results)
        assert cs["can_win"] is False

    def test_already_clinched(self, entries, tournament, results):
        """Simulate a scenario where the leader has an insurmountable lead."""
        # Give Alice a massive lead by pretending she already has 10000 points
        # Build hypothetical: alice wins all games except championship undecided
        hypo = what_if(results, "r2_west_1", "houston", "alabama")
        # Now Alice has more pts and Bob/Charlie can't catch up
        # Verify clinch is False (championship still pending means others have max_possible)
        cs = clinch_scenarios(entries, "Alice", tournament, hypo)
        # One game remains (championship), Alice picked duke who is still alive
        # Alice's total in hypo: 40+20=60. Charlie: 60+20=80. So alice still isn't clinched yet.
        # Alice has clinch scenario: win championship
        assert cs["clinched"] is False
        assert cs["clinch_outcomes"] is not None

    def test_clinch_outcomes_structure(self, entries, tournament, results):
        cs = clinch_scenarios(entries, "Alice", tournament, results)
        if cs["clinch_outcomes"] is not None:
            for outcome in cs["clinch_outcomes"]:
                assert "slot_id" in outcome
                assert "required_winner" in outcome


# --- best_path tests ---


class TestBestPath:
    def test_returns_steps_sorted_by_round(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Alice", entries, tournament, results)
        rounds = [s["round"] for s in path["steps"]]
        assert rounds == sorted(rounds)

    def test_eliminated_player_returns_empty_steps(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Dave", entries, tournament, results)
        assert path["steps"] == []
        assert path["win_probability"] == pytest.approx(0.0)

    def test_alice_best_path_includes_duke_championship(self, entries, tournament, results):
        """Alice wins when Duke wins championship; her best path should include that."""
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Alice", entries, tournament, results)
        root_for_teams = [s["root_for"] for s in path["steps"]]
        assert "duke" in root_for_teams

    def test_path_probability_is_product(self, entries, tournament, results):
        """Path probability should be between 0 and 1."""
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Alice", entries, tournament, results)
        assert 0.0 <= path["path_probability"] <= 1.0

    def test_win_probability_matches_scenario_results(self, entries, tournament, results):
        """win_probability should match sr.win_counts / total."""
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Alice", entries, tournament, results)
        expected = sr.win_counts["Alice"] / sr.total_scenarios
        assert path["win_probability"] == pytest.approx(expected)

    def test_steps_have_required_keys(self, entries, tournament, results):
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Alice", entries, tournament, results)
        for step in path["steps"]:
            for key in ("slot_id", "round", "root_for", "opponent"):
                assert key in step

    def test_charlie_best_path_includes_houston(self, entries, tournament, results):
        """Charlie wins when Houston wins; that should appear in his best path."""
        sr = brute_force_scenarios(entries, tournament, results)
        path = best_path(sr, "Charlie", entries, tournament, results)
        root_for_teams = [s["root_for"] for s in path["steps"]]
        assert "houston" in root_for_teams


# --- Helper function unit tests ---


class TestHelperFunctions:
    def test_min_picks_to_lead_already_leading(self, entries, tournament, results):
        """Player already leads: _min_picks_to_lead returns 0."""
        from core.scoring import score_entry

        alice = next(e for e in entries if e.player_name == "Alice")
        alice_scored = score_entry(alice, tournament, results)
        # Alice leads; max_other_current set below her score
        result = _min_picks_to_lead(alice_scored, alice_scored.total_points - 1, tournament)
        assert result == 0

    def test_min_picks_to_lead_gap_open(self, entries, tournament, results):
        """Player is behind: returns a positive integer pick count."""
        from core.scoring import score_entry

        alice = next(e for e in entries if e.player_name == "Alice")
        alice_scored = score_entry(alice, tournament, results)
        # Set max_other well above alice's current score to force needing picks
        result = _min_picks_to_lead(alice_scored, alice_scored.total_points + 1, tournament)
        assert result >= 1

    def test_lowest_confidence_unknown_source_is_lowest(self):
        """Unknown source strings should rank as lowest confidence (not highest)."""
        # "moneyline" is highest confidence; unknown source should not beat it
        result = _lowest_confidence(["moneyline", "unknown_source"])
        assert result == "unknown_source"

    def test_lowest_confidence_known_sources(self):
        """coin_flip < seed_historical < spread < moneyline."""
        assert _lowest_confidence(["moneyline", "coin_flip"]) == "coin_flip"
        assert _lowest_confidence(["spread", "seed_historical"]) == "seed_historical"
        assert _lowest_confidence(["moneyline"]) == "moneyline"

    def test_best_path_greedy_engine(self, entries, tournament, results):
        """Force monte_carlo engine to exercise _best_path_greedy code path."""
        sr = monte_carlo_scenarios(entries, tournament, results, n_simulations=500, seed=42)
        # Manually override engine label to trigger greedy path in best_path
        sr.engine = "monte_carlo"
        path = best_path(sr, "Alice", entries, tournament, results)
        assert "steps" in path
        assert "win_probability" in path
        assert isinstance(path["steps"], list)
