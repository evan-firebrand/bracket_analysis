"""Tests for core/awards.py — bracket superlatives."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.awards import Award, compute_awards
from core.loader import load_entries, load_results, load_tournament
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
def scored(tournament, results, entries):
    return {e.player_name: score_entry(e, tournament, results) for e in entries}


@pytest.fixture
def awards(entries, tournament, results, scored):
    return compute_awards(entries, tournament, results, scored)


def _award(awards: list[Award], name: str) -> Award:
    return next(a for a in awards if a.name == name)


class TestAwardStructure:
    def test_returns_list_of_awards(self, awards):
        assert isinstance(awards, list)
        assert all(isinstance(a, Award) for a in awards)

    def test_each_award_has_winner_name_emoji_blurb(self, awards):
        for award in awards:
            assert award.name
            assert award.emoji
            assert award.winner
            assert award.blurb

    def test_all_winners_are_valid_players(self, awards, entries):
        player_names = {e.player_name for e in entries}
        for award in awards:
            assert award.winner in player_names, (
                f"{award.name} winner '{award.winner}' is not a known player"
            )

    def test_empty_entries_returns_empty(self, tournament, results):
        assert compute_awards([], tournament, results, {}) == []


class TestOracleAward:
    def test_charlie_wins_oracle(self, awards):
        # Charlie got all 5 completed games right (most correct picks)
        oracle = _award(awards, "The Oracle")
        assert oracle.winner == "Charlie"

    def test_blurb_mentions_correct_count(self, awards):
        oracle = _award(awards, "The Oracle")
        assert "5" in oracle.blurb

    def test_blurb_mentions_a_team(self, awards, tournament):
        oracle = _award(awards, "The Oracle")
        # Charlie's best correct pick is r2_east_1 (round 2), team = Duke
        assert "Duke" in oracle.blurb


class TestChalkItUpAward:
    def test_alice_or_dave_wins_chalk(self, awards):
        # Alice and Dave both picked all 4 R1 favorites (100% chalk)
        chalk = _award(awards, "Chalk It Up")
        assert chalk.winner in ("Alice", "Dave")

    def test_blurb_mentions_r1_count(self, awards):
        chalk = _award(awards, "Chalk It Up")
        # "4/4" since all 4 R1 slots exist and both are 100% chalk
        assert "4/4" in chalk.blurb


class TestContrarianAward:
    def test_bob_or_eve_wins_contrarian(self, awards):
        # Bob and Eve both picked 4 R1 upsets (0% chalk)
        contrarian = _award(awards, "The Contrarian")
        assert contrarian.winner in ("Bob", "Eve")

    def test_blurb_mentions_upset_count(self, awards):
        contrarian = _award(awards, "The Contrarian")
        assert "4/4" in contrarian.blurb


class TestUpsetWhispererAward:
    def test_winner_called_r1_upsets(self, awards):
        # R1 upsets: gonzaga over unc, alabama over tennessee
        # Bob, Charlie, Eve all got both → Bob wins (first in list)
        whisper = _award(awards, "Upset Whisperer")
        assert whisper.winner in ("Bob", "Charlie", "Eve")

    def test_blurb_mentions_count_and_team(self, awards):
        whisper = _award(awards, "Upset Whisperer")
        # Winner called 2 upsets
        assert "2" in whisper.blurb
        # Blurb should name at least one underdog team
        assert "Gonzaga" in whisper.blurb or "Alabama" in whisper.blurb


class TestSafeBetAward:
    def test_charlie_wins_safe_bet(self, awards):
        # Charlie has highest average group agreement (2.5/7)
        safe = _award(awards, "Safe Bet")
        assert safe.winner == "Charlie"

    def test_blurb_mentions_agreement_fraction(self, awards):
        safe = _award(awards, "Safe Bet")
        assert "/7" in safe.blurb


class TestLoneWolfAward:
    def test_bob_or_eve_wins_lone_wolf(self, awards):
        # Bob and Eve both have lowest average agreement (1.75/7)
        wolf = _award(awards, "Lone Wolf")
        assert wolf.winner in ("Bob", "Eve")

    def test_blurb_mentions_agreement_fraction(self, awards):
        wolf = _award(awards, "Lone Wolf")
        assert "/7" in wolf.blurb


class TestAllInAward:
    def test_winner_has_alive_champion(self, awards):
        # Bob(alabama) and Charlie(houston) both have 340 pending pts on alive champ
        allin = _award(awards, "All-In")
        assert allin.winner in ("Bob", "Charlie")

    def test_blurb_mentions_points_and_team(self, awards):
        allin = _award(awards, "All-In")
        # 340 pending points (r2_west_1 = 20, championship = 320)
        assert "340" in allin.blurb
        assert "Alabama" in allin.blurb or "Houston" in allin.blurb


class TestOptimistAward:
    def test_charlie_wins_optimist(self, awards):
        # Charlie max_possible = 60 + 20 + 320 = 400 (highest)
        optimist = _award(awards, "The Optimist")
        assert optimist.winner == "Charlie"

    def test_blurb_mentions_max_possible(self, awards):
        optimist = _award(awards, "The Optimist")
        assert "400" in optimist.blurb

    def test_blurb_mentions_current_points(self, awards):
        optimist = _award(awards, "The Optimist")
        assert "60" in optimist.blurb


class TestHeartbreakHotelAward:
    def test_dave_wins_heartbreak(self, awards):
        # Dave's champion (Tennessee) was eliminated in Round 1 — the earliest exit
        heartbreak = _award(awards, "Heartbreak Hotel")
        assert heartbreak.winner == "Dave"

    def test_blurb_mentions_champion_team(self, awards):
        heartbreak = _award(awards, "Heartbreak Hotel")
        assert "Tennessee" in heartbreak.blurb

    def test_blurb_mentions_exit_round(self, awards):
        heartbreak = _award(awards, "Heartbreak Hotel")
        assert "Round of 64" in heartbreak.blurb

    def test_skipped_when_no_champion_eliminated(self, entries, tournament, scored):
        # Empty results = no champion eliminated yet
        from core.models import Results
        no_results = Results(last_updated="", results={})
        empty_scored = {e.player_name: score_entry(e, tournament, no_results) for e in entries}
        awards = compute_awards(entries, tournament, no_results, empty_scored)
        names = [a.name for a in awards]
        assert "Heartbreak Hotel" not in names


class TestCrystalBallAward:
    def test_charlie_wins_crystal_ball(self, awards):
        # Charlie got 4/4 R1 games correct — the only player with a perfect R1
        crystal = _award(awards, "Crystal Ball")
        assert crystal.winner == "Charlie"

    def test_blurb_mentions_r1_accuracy(self, awards):
        crystal = _award(awards, "Crystal Ball")
        assert "4/4" in crystal.blurb

    def test_skipped_when_no_r1_results(self, entries, tournament, scored):
        from core.models import Results
        no_results = Results(last_updated="", results={})
        empty_scored = {e.player_name: score_entry(e, tournament, no_results) for e in entries}
        awards = compute_awards(entries, tournament, no_results, empty_scored)
        names = [a.name for a in awards]
        assert "Crystal Ball" not in names
