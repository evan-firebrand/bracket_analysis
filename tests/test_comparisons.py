"""Tests for comparison logic used by head_to_head and group_picks plugins."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import AnalysisContext
from core.loader import load_entries, load_results, load_tournament
from core.scoring import POINTS_PER_ROUND


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


class TestHeadToHead:
    def test_identical_brackets_agree_on_all(self, tournament, entries):
        """A player compared to themselves should agree on all picks."""
        alice = _get_entry(entries, "Alice")
        agree = [
            slot_id for slot_id in tournament.slot_order
            if alice.picks.get(slot_id) == alice.picks.get(slot_id)
        ]
        assert len(agree) == len(tournament.slot_order)

    def test_alice_dave_similar(self, tournament, entries):
        """Alice and Dave have the same R1 picks, differ on R2 West and Championship."""
        alice = _get_entry(entries, "Alice")
        dave = _get_entry(entries, "Dave")

        agree = []
        disagree = []
        for slot_id in tournament.slot_order:
            if alice.picks.get(slot_id) == dave.picks.get(slot_id):
                agree.append(slot_id)
            else:
                disagree.append(slot_id)

        # Same: r1_east_1v4(duke), r1_east_2v3(unc), r1_west_1v4(houston),
        #        r1_west_2v3(tennessee), r2_east_1(duke)
        # Different: r2_west_1 (houston vs tennessee), championship (duke vs tennessee)
        assert len(agree) == 5
        assert len(disagree) == 2

    def test_alice_bob_very_different(self, tournament, entries):
        """Alice (chalk) and Bob (upsets) should disagree on most picks."""
        alice = _get_entry(entries, "Alice")
        bob = _get_entry(entries, "Bob")

        disagree = [
            slot_id for slot_id in tournament.slot_order
            if alice.picks.get(slot_id) != bob.picks.get(slot_id)
        ]
        # They disagree on every single R1 pick and cascade from there
        assert len(disagree) >= 6  # at least 6 of 7


class TestPickPopularity:
    def test_champion_pick_distribution(self, tournament, entries):
        """Check champion pick distribution across 5 players."""
        from collections import Counter

        # Find championship slot
        champ_slot = next(
            sid for sid, s in tournament.slots.items()
            if s.feeds_into is None
        )

        counts = Counter(e.picks[champ_slot] for e in entries)
        # Alice=duke, Bob=alabama, Charlie=houston, Dave=tennessee, Eve=gonzaga
        # Each player picked a different champion
        assert len(counts) == 5
        assert all(c == 1 for c in counts.values())

    def test_popular_r1_pick(self, tournament, entries):
        """Duke in r1_east_1v4 should be picked by 3 players (Alice, Charlie, Dave)."""
        from collections import Counter

        counts = Counter(e.picks["r1_east_1v4"] for e in entries)
        assert counts["duke"] == 3
        assert counts["purdue"] == 2


class TestTeamExposure:
    def test_eliminated_teams_no_exposure(self, tournament, results, entries):
        """Eliminated teams should not show up in exposure calculations."""
        from analyses.group_picks import _team_exposure
        from core.context import AnalysisContext

        ctx = AnalysisContext(data_dir=Path(__file__).parent.parent / "data")
        exposure = _team_exposure(ctx)

        # gonzaga, purdue, unc, arizona, tennessee are eliminated
        assert "gonzaga" not in exposure
        assert "purdue" not in exposure
        assert "unc" not in exposure
        assert "arizona" not in exposure
        assert "tennessee" not in exposure

    def test_alive_teams_have_exposure(self, tournament, results, entries):
        """Alive teams with pending picks should have exposure."""
        from analyses.group_picks import _team_exposure
        from core.context import AnalysisContext

        ctx = AnalysisContext(data_dir=Path(__file__).parent.parent / "data")
        exposure = _team_exposure(ctx)

        # houston and alabama are alive and picked by multiple players in pending games
        assert "houston" in exposure
        assert exposure["houston"] > 0
        assert "alabama" in exposure
        assert exposure["alabama"] > 0


class TestContrarianPicks:
    def test_contrarian_detection(self, tournament, entries):
        """Picks made by only 1 player (20% of 5) should be flagged as contrarian."""
        from collections import Counter

        from analyses.group_picks import _contrarian_picks, _pick_popularity
        from core.context import AnalysisContext

        ctx = AnalysisContext(data_dir=Path(__file__).parent.parent / "data")
        popularity = _pick_popularity(ctx)
        contrarian = _contrarian_picks(ctx, popularity, threshold=0.25)

        # Every championship pick is unique (1/5 = 20% < 25% threshold)
        # So every player should have at least 1 contrarian pick
        for player_name, picks in contrarian.items():
            assert len(picks) >= 1, f"{player_name} should have contrarian picks"
