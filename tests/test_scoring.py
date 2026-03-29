"""Tests for the scoring engine."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.loader import load_entries, load_results, load_tournament
from core.scoring import (
    build_leaderboard,
    get_alive_teams,
    score_entry,
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


def _get_entry(entries, name):
    return next(e for e in entries if e.player_name == name)


class TestAliveTeams:
    def test_eliminated_teams_not_alive(self, tournament, results):
        alive = get_alive_teams(tournament, results)
        # purdue, unc, arizona, tennessee, gonzaga are eliminated
        assert "purdue" not in alive
        assert "unc" not in alive
        assert "arizona" not in alive
        assert "tennessee" not in alive
        assert "gonzaga" not in alive

    def test_remaining_teams_alive(self, tournament, results):
        alive = get_alive_teams(tournament, results)
        # duke, houston, alabama are still alive
        assert "duke" in alive
        assert "houston" in alive
        assert "alabama" in alive


class TestScoreEntry:
    def test_charlie_perfect_so_far(self, tournament, results, entries):
        """Charlie picked all 5 completed games correctly."""
        charlie = _get_entry(entries, "Charlie")
        scored = score_entry(charlie, tournament, results)

        # R1: 4 correct * 10pts = 40, R2: 1 correct * 20pts = 20
        assert scored.total_points == 60
        assert len(scored.correct_picks) == 5
        assert len(scored.incorrect_picks) == 0
        assert len(scored.pending_picks) == 2  # r2_west_1, championship

    def test_alice_missed_two(self, tournament, results, entries):
        """Alice missed UNC (picked UNC, Gonzaga won) and Tennessee (picked Tennessee, Alabama won)."""
        alice = _get_entry(entries, "Alice")
        scored = score_entry(alice, tournament, results)

        # Correct: duke(R1), houston(R1), duke(R2) = 10+10+20 = 40
        assert scored.total_points == 40
        assert len(scored.correct_picks) == 3
        assert len(scored.incorrect_picks) == 2

    def test_bob_got_upsets(self, tournament, results, entries):
        """Bob picked Gonzaga and Alabama correctly in R1, but Purdue and Arizona wrong."""
        bob = _get_entry(entries, "Bob")
        scored = score_entry(bob, tournament, results)

        # Correct: gonzaga(R1), alabama(R1) = 10+10 = 20
        # Wrong: purdue(R1), arizona(R1), gonzaga(R2) = 3 wrong
        assert scored.total_points == 20
        assert len(scored.correct_picks) == 2
        assert len(scored.incorrect_picks) == 3

    def test_eve_eliminated_picks(self, tournament, results, entries):
        """Eve's gonzaga championship pick is dead since gonzaga lost in R2."""
        eve = _get_entry(entries, "Eve")
        scored = score_entry(eve, tournament, results)

        # Gonzaga is eliminated, so Eve's R2 and championship picks are busted
        # Her pending pick for r2_west_1 (arizona) is also eliminated
        # Max possible = current points only (20) since no alive pending picks
        assert scored.total_points == 20
        # Eve's pending picks: r2_west_1 (arizona - eliminated), championship (gonzaga - eliminated)
        # Neither team is alive, so max_possible = current
        assert scored.max_possible == 20

    def test_max_possible_charlie(self, tournament, results, entries):
        """Charlie's pending picks are houston (alive) in r2_west_1 and championship."""
        charlie = _get_entry(entries, "Charlie")
        scored = score_entry(charlie, tournament, results)

        # Charlie has: r2_west_1=houston (alive, 20pts), championship=houston (alive, 40pts)
        # max_possible = 60 + 20 + 40 = 120
        assert scored.max_possible == 60 + 20 + 40


class TestBuildLeaderboard:
    def test_leaderboard_ranking(self, tournament, results, entries):
        df = build_leaderboard(entries, tournament, results)

        # Charlie should be #1 with 60 pts
        assert df.iloc[0]["Player"] == "Charlie"
        assert df.iloc[0]["Total"] == 60

        # Verify all 5 players present
        assert len(df) == 5

        # Verify ranked in descending order
        totals = df["Total"].tolist()
        assert totals == sorted(totals, reverse=True)

    def test_leaderboard_has_round_columns(self, tournament, results, entries):
        df = build_leaderboard(entries, tournament, results)
        assert "Round of 64" in df.columns  # Our test uses rounds 1,2,3 but names map differently

    def test_leaderboard_rank_column(self, tournament, results, entries):
        df = build_leaderboard(entries, tournament, results)
        assert df.iloc[0]["Rank"] == 1
        assert df.iloc[-1]["Rank"] == 5
