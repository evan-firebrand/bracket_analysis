"""Tests for core/superlatives.py — pure business logic, no Streamlit."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import load_entries, load_results, load_tournament
from core.models import GameResult, PlayerEntry, Results, TournamentStructure
from core.superlatives import (
    Superlative,
    _chaos_agent,
    _contrarian_king,
    _biggest_bust,
    _crystal_ball,
    _hot_finisher,
    _most_accurate,
    _most_heartbreaks,
    _mr_chalk,
    _pick_winner,
    _pool_champion,
    _sharpest_round_one,
    compute_superlatives,
    player_award_summary,
)
from core.comparison import chalk_score


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
def results_no_championship(results):
    """Results with championship game still pending."""
    filtered = {k: v for k, v in results.results.items() if k != "championship"}
    return Results(last_updated=results.last_updated, results=filtered)


def _get_entry(entries, name):
    return next(e for e in entries if e.player_name == name)


# ---------------------------------------------------------------------------
# _pick_winner
# ---------------------------------------------------------------------------


class TestPickWinner:
    def test_single_winner(self):
        winner, runner_up, is_tie, runner_up_val = _pick_winner(
            {"Alice": 100, "Bob": 80, "Charlie": 60}
        )
        assert winner == "Alice"
        assert runner_up == "Bob"
        assert runner_up_val == 80
        assert not is_tie

    def test_tie(self):
        winner, runner_up, is_tie, runner_up_val = _pick_winner(
            {"Alice": 100, "Bob": 100, "Charlie": 60}
        )
        assert "Alice" in winner and "Bob" in winner
        assert is_tie
        assert runner_up == "Charlie"
        assert runner_up_val == 60

    def test_all_tied(self):
        winner, runner_up, is_tie, runner_up_val = _pick_winner(
            {"Alice": 50, "Bob": 50}
        )
        assert is_tie
        assert runner_up is None
        assert runner_up_val is None

    def test_empty(self):
        winner, runner_up, is_tie, runner_up_val = _pick_winner({})
        assert winner == "(none)"
        assert not is_tie


# ---------------------------------------------------------------------------
# Pool Champion
# ---------------------------------------------------------------------------


class TestPoolChampion:
    def test_winner_is_highest_scorer(self, entries, tournament, results):
        # Charlie picks all R1 correct (4*10=40) + R2 correct (20) = 60
        award = _pool_champion(entries, tournament, results)
        assert award.title == "Pool Champion"
        assert award.winner == "Charlie"
        assert "60" in award.value

    def test_runner_up_present(self, entries, tournament, results):
        award = _pool_champion(entries, tournament, results)
        assert award.runner_up is not None


# ---------------------------------------------------------------------------
# Most Accurate
# ---------------------------------------------------------------------------


class TestMostAccurate:
    def test_charlie_is_most_accurate(self, entries, tournament, results):
        # Charlie: 5/5 correct in played games
        award = _most_accurate(entries, tournament, results)
        assert award.winner == "Charlie"
        assert "100.0%" in award.value

    def test_value_includes_fraction(self, entries, tournament, results):
        award = _most_accurate(entries, tournament, results)
        assert "/" in award.value


# ---------------------------------------------------------------------------
# Sharpest in Round 1
# ---------------------------------------------------------------------------


class TestSharpestRoundOne:
    def test_charlie_wins_round_one(self, entries, tournament, results):
        # Charlie: duke✓, gonzaga✓, houston✓, alabama✓ = 40 pts
        award = _sharpest_round_one(entries, tournament, results)
        assert award.winner == "Charlie"
        assert "40" in award.value

    def test_value_shows_correct_out_of_total(self, entries, tournament, results):
        award = _sharpest_round_one(entries, tournament, results)
        assert "/4" in award.value  # 4 R1 games in fixture


# ---------------------------------------------------------------------------
# Crystal Ball
# ---------------------------------------------------------------------------


class TestCrystalBall:
    def test_returns_none_when_championship_not_played(
        self, entries, tournament, results_no_championship
    ):
        award = _crystal_ball(entries, tournament, results_no_championship)
        assert award is None

    def test_returns_superlative_when_championship_played(
        self, entries, tournament, results
    ):
        # Add championship result: duke wins. Alice and Dave both picked duke.
        new_results = dict(results.results)
        new_results["championship"] = GameResult(winner="duke", loser="houston")
        r = Results(last_updated="", results=new_results)
        award = _crystal_ball(entries, tournament, r)
        assert award is not None
        assert award.title == "Crystal Ball"
        assert "Alice" in award.winner or "Dave" in award.winner

    def test_nobody_picked_champion(self, entries, tournament, results_no_championship):
        # Add a championship result that nobody picked
        new_results = dict(results_no_championship.results)
        new_results["championship"] = GameResult(winner="purdue", loser="houston")
        r = Results(last_updated="", results=new_results)
        award = _crystal_ball(entries, tournament, r)
        assert award is not None
        assert award.winner == "Nobody"


# ---------------------------------------------------------------------------
# Mr. Chalk / Chaos Agent
# ---------------------------------------------------------------------------


class TestChalkAndChaos:
    def test_alice_and_dave_are_chalk(self, entries, tournament):
        # Alice and Dave both picked all higher seeds in R1 → chalk_score = 1.0
        chalks = chalk_score(entries, tournament)
        assert chalks["Alice"] == 1.0
        assert chalks["Dave"] == 1.0

    def test_bob_and_eve_are_chaos(self, entries, tournament):
        # Bob and Eve both picked all lower seeds in R1 → chalk_score = 0.0
        chalks = chalk_score(entries, tournament)
        assert chalks["Bob"] == 0.0
        assert chalks["Eve"] == 0.0

    def test_mr_chalk_winner(self, entries, tournament):
        chalks = chalk_score(entries, tournament)
        award = _mr_chalk(entries, chalks)
        assert award.title == "Mr. Chalk"
        # Alice and Dave are tied at 1.0
        assert "Alice" in award.winner or "Dave" in award.winner
        assert award.is_tie  # both at 1.0

    def test_chaos_agent_winner(self, entries, tournament):
        chalks = chalk_score(entries, tournament)
        award = _chaos_agent(entries, chalks)
        assert award.title == "Chaos Agent"
        # Bob and Eve are tied at 0.0
        assert "Bob" in award.winner or "Eve" in award.winner
        assert award.is_tie


# ---------------------------------------------------------------------------
# Contrarian King
# ---------------------------------------------------------------------------


class TestContrarianKing:
    def test_returns_superlative(self, entries, tournament, results):
        award = _contrarian_king(entries, tournament, results)
        assert isinstance(award, Superlative)
        assert award.title == "Contrarian King"

    def test_winner_is_player_name(self, entries, tournament, results):
        award = _contrarian_king(entries, tournament, results)
        all_names = {e.player_name for e in entries}
        winners = {w.strip() for w in award.winner.split(",")}
        assert winners.issubset(all_names) or award.winner == "(none)"


# ---------------------------------------------------------------------------
# Biggest Bust
# ---------------------------------------------------------------------------


class TestBiggestBust:
    def test_returns_superlative(self, entries, tournament, results):
        award = _biggest_bust(entries, tournament, results)
        assert isinstance(award, Superlative)
        assert award.title == "Biggest Bust"

    def test_value_reflects_points(self, entries, tournament, results):
        award = _biggest_bust(entries, tournament, results)
        # The bust value should mention points lost (from POINTS_PER_ROUND)
        assert "pts" in award.value or "Lost" in award.value

    def test_bust_is_incorrect_pick(self, entries, tournament, results):
        # The winner must have at least one incorrect pick
        from core.scoring import score_entry
        award = _biggest_bust(entries, tournament, results)
        winner_name = award.winner.split(", ")[0]
        winner_entry = next(e for e in entries if e.player_name == winner_name)
        se = score_entry(winner_entry, tournament, results)
        assert len(se.incorrect_picks) > 0


# ---------------------------------------------------------------------------
# Most Heartbreaks
# ---------------------------------------------------------------------------


class TestMostHeartbreaks:
    def test_returns_superlative(self, entries, tournament, results):
        award = _most_heartbreaks(entries, tournament, results)
        assert isinstance(award, Superlative)
        assert award.title == "Most Heartbreaks"

    def test_counts_top_three_seeds_that_lost(self, entries, tournament, results):
        # In fixture: unc (seed 2) lost, tennessee (seed 2) lost
        # Alice and Dave picked unc AND tennessee (both seed 2) = 2 heartbreaks each
        # Bob picked purdue (seed 4) and arizona (seed 4) → 0 heartbreaks (seed > 3)
        award = _most_heartbreaks(entries, tournament, results)
        assert "Alice" in award.winner or "Dave" in award.winner
        assert "2" in award.value


# ---------------------------------------------------------------------------
# Hot Finisher
# ---------------------------------------------------------------------------


class TestHotFinisher:
    def test_returns_superlative(self, entries, tournament, results):
        award = _hot_finisher(entries, tournament, results)
        assert isinstance(award, Superlative)
        assert award.title == "Hot Finisher"

    def test_winner_is_valid_player(self, entries, tournament, results):
        award = _hot_finisher(entries, tournament, results)
        all_names = {e.player_name for e in entries}
        winners = {w.strip() for w in award.winner.split(",")}
        assert winners.issubset(all_names)


# ---------------------------------------------------------------------------
# compute_superlatives — integration
# ---------------------------------------------------------------------------


class TestComputeSuperlatives:
    def test_returns_list_of_superlatives(self, entries, tournament, results):
        awards = compute_superlatives(entries, tournament, results)
        assert isinstance(awards, list)
        assert len(awards) > 0
        assert all(isinstance(a, Superlative) for a in awards)

    def test_includes_crystal_ball_when_championship_played(
        self, entries, tournament, results
    ):
        # Add championship result so Crystal Ball is awarded
        new_results = dict(results.results)
        new_results["championship"] = GameResult(winner="duke", loser="houston")
        r = Results(last_updated="", results=new_results)
        awards = compute_superlatives(entries, tournament, r)
        titles = [a.title for a in awards]
        assert "Crystal Ball" in titles

    def test_omits_crystal_ball_when_championship_pending(
        self, entries, tournament, results_no_championship
    ):
        awards = compute_superlatives(entries, tournament, results_no_championship)
        titles = [a.title for a in awards]
        assert "Crystal Ball" not in titles

    def test_expected_award_titles_present(self, entries, tournament, results):
        awards = compute_superlatives(entries, tournament, results)
        titles = {a.title for a in awards}
        expected = {
            "Pool Champion",
            "Most Accurate",
            "Sharpest in Round 1",
            "Sweet Sixteen Savant",
            "Final Four Prophet",
            "Mr. Chalk",
            "Chaos Agent",
            "Contrarian King",
            "Biggest Bust",
            "Most Heartbreaks",
            "Hot Finisher",
        }
        assert expected.issubset(titles)


# ---------------------------------------------------------------------------
# player_award_summary
# ---------------------------------------------------------------------------


class TestPlayerAwardSummary:
    def test_all_players_present(self, entries, tournament, results):
        awards = compute_superlatives(entries, tournament, results)
        summary = player_award_summary(entries, awards)
        all_names = {e.player_name for e in entries}
        assert set(summary.keys()) == all_names

    def test_values_are_lists(self, entries, tournament, results):
        awards = compute_superlatives(entries, tournament, results)
        summary = player_award_summary(entries, awards)
        for name, titles in summary.items():
            assert isinstance(titles, list)

    def test_award_titles_appear_in_summary(self, entries, tournament, results):
        awards = compute_superlatives(entries, tournament, results)
        summary = player_award_summary(entries, awards)
        all_awarded_titles = [title for titles in summary.values() for title in titles]
        award_titles = {a.title for a in awards}
        for title in all_awarded_titles:
            assert title in award_titles
