"""Tests for core/comparison.py — pure business logic, no Streamlit."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.comparison import (
    agreement_matrix,
    chalk_score,
    compare_counterfactual,
    contrarian_picks,
    counterfactual_entry,
    group_chalk_score,
    head_to_head,
    pick_popularity,
    team_exposure,
)
from core.loader import load_entries, load_results, load_tournament


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


def _get_entry(entries, name):
    return next(e for e in entries if e.player_name == name)


class TestHeadToHead:
    def test_alice_dave_similar(self, tournament, results, entries):
        """Alice and Dave share R1 picks, differ on R2 West and Championship."""
        alice = _get_entry(entries, "Alice")
        dave = _get_entry(entries, "Dave")
        h2h = head_to_head(alice, dave, tournament, results)

        assert len(h2h.agree) == 5
        assert h2h.total_disagree == 2
        assert len(h2h.disagree_pending) == 2  # r2_west_1, championship

    def test_alice_bob_very_different(self, tournament, results, entries):
        """Chalk vs upset brackets should disagree on almost everything."""
        alice = _get_entry(entries, "Alice")
        bob = _get_entry(entries, "Bob")
        h2h = head_to_head(alice, bob, tournament, results)

        assert h2h.total_disagree >= 6

    def test_pending_points_calculated(self, tournament, results, entries):
        """Pending points should sum point values of unresolved disagreements."""
        alice = _get_entry(entries, "Alice")
        dave = _get_entry(entries, "Dave")
        h2h = head_to_head(alice, dave, tournament, results)

        # r2_west_1 = 20 pts, championship = 320 pts
        assert h2h.pending_points == 340

    def test_both_wrong_category(self, tournament, results, entries):
        """When both players pick differently and both are wrong."""
        alice = _get_entry(entries, "Alice")
        bob = _get_entry(entries, "Bob")
        h2h = head_to_head(alice, bob, tournament, results)

        # r1_east_2v3: Alice picked UNC, Bob picked Gonzaga, Gonzaga won
        # So Bob was right, not "both wrong"
        # r2_east_1: Alice picked Duke, Bob picked Gonzaga, Duke won
        # So Alice was right
        # No "both wrong" cases in this data
        assert len(h2h.disagree_both_wrong) == 0


class TestAgreementMatrix:
    def test_symmetric(self, tournament, entries):
        """Matrix should be symmetric: (a,b) == (b,a)."""
        matrix = agreement_matrix(entries, tournament)
        for (a, b), count in matrix.items():
            assert matrix.get((b, a)) == count

    def test_alice_dave_agreement_count(self, tournament, entries):
        """Alice and Dave agree on 5 of 7 picks."""
        matrix = agreement_matrix(entries, tournament)
        assert matrix[("Alice", "Dave")] == 5


class TestPickPopularity:
    def test_champion_all_different(self, tournament, entries):
        """All 5 players picked different champions."""
        popularity = pick_popularity(entries, tournament)
        champ_slot = next(
            sid for sid, s in tournament.slots.items() if s.feeds_into is None
        )
        counts = popularity[champ_slot]
        assert len(counts) == 5
        assert all(c == 1 for c in counts.values())

    def test_duke_popular_in_r1(self, tournament, entries):
        """Duke picked by 3 of 5 in r1_east_1v4."""
        popularity = pick_popularity(entries, tournament)
        assert popularity["r1_east_1v4"]["duke"] == 3
        assert popularity["r1_east_1v4"]["purdue"] == 2


class TestTeamExposure:
    def test_eliminated_teams_excluded(self, tournament, results, entries):
        """Eliminated teams should have zero exposure."""
        exposure = team_exposure(entries, tournament, results)
        for team in ["gonzaga", "purdue", "unc", "arizona", "tennessee"]:
            assert team not in exposure

    def test_alive_teams_have_exposure(self, tournament, results, entries):
        """Houston and Alabama are alive with pending picks."""
        exposure = team_exposure(entries, tournament, results)
        assert "houston" in exposure
        assert exposure["houston"] > 0
        assert "alabama" in exposure
        assert exposure["alabama"] > 0


class TestContrarianPicks:
    def test_detects_unique_picks(self, tournament, results, entries):
        """Championship picks are 1/5 = 20%, should be flagged at 25% threshold."""
        popularity = pick_popularity(entries, tournament)
        contrarian = contrarian_picks(entries, tournament, results, popularity, threshold=0.25)

        for player_name, picks in contrarian.items():
            assert len(picks) >= 1, f"{player_name} should have contrarian picks"

    def test_correct_flag_on_resolved_picks(self, tournament, results, entries):
        """Contrarian picks for resolved games should have correct=True/False."""
        popularity = pick_popularity(entries, tournament)
        contrarian = contrarian_picks(entries, tournament, results, popularity, threshold=0.50)

        for player_name, picks in contrarian.items():
            for pick in picks:
                if results.is_complete(pick.slot_id):
                    assert pick.correct is not None


class TestChalkScore:
    def test_alice_is_chalk(self, tournament, entries):
        """Alice picks all higher seeds in R1."""
        scores = chalk_score(entries, tournament)
        # Alice: duke(1) over purdue(4), unc(2) over gonzaga(3),
        #        houston(1) over arizona(4), tennessee(2) over alabama(3) = 4/4 = 100%
        assert scores["Alice"] == 1.0

    def test_bob_is_all_upsets(self, tournament, entries):
        """Bob picks all lower seeds in R1."""
        scores = chalk_score(entries, tournament)
        # Bob: purdue(4), gonzaga(3), arizona(4), alabama(3) = 0/4 = 0%
        assert scores["Bob"] == 0.0

    def test_charlie_is_mixed(self, tournament, entries):
        """Charlie picks 2 chalk, 2 upsets in R1."""
        scores = chalk_score(entries, tournament)
        # Charlie: duke(1)=chalk, gonzaga(3)=upset, houston(1)=chalk, alabama(3)=upset = 2/4 = 50%
        assert scores["Charlie"] == 0.5

    def test_group_chalk_is_average(self, tournament, entries):
        """Group chalk score should be the average of individual scores."""
        individual = chalk_score(entries, tournament)
        group = group_chalk_score(entries, tournament)
        expected = sum(individual.values()) / len(individual)
        assert abs(group - expected) < 0.001


class TestCounterfactualEntry:
    """Tests for counterfactual_entry() — WI-1 and WI-2."""

    def test_single_swap_no_propagation(self, tournament, entries):
        """Basic swap: change one pick, no cascading."""
        alice = _get_entry(entries, "Alice")
        cf = counterfactual_entry(alice, {"r2_west_1": "alabama"})

        assert cf.picks["r2_west_1"] == "alabama"
        assert cf.player_name == "Alice"

    def test_original_not_mutated(self, tournament, entries):
        """Original entry must be unchanged after creating counterfactual."""
        alice = _get_entry(entries, "Alice")
        original_picks = dict(alice.picks)
        counterfactual_entry(alice, {"r2_west_1": "alabama"})

        assert alice.picks == original_picks

    def test_unmodified_picks_preserved(self, tournament, entries):
        """Picks not in overrides should be unchanged."""
        alice = _get_entry(entries, "Alice")
        cf = counterfactual_entry(alice, {"r2_west_1": "alabama"})

        assert cf.picks["r1_east_1v4"] == alice.picks["r1_east_1v4"]
        assert cf.picks["championship"] == alice.picks["championship"]
        assert cf.picks["r2_east_1"] == alice.picks["r2_east_1"]

    def test_propagation_cascades_downstream(self, tournament, entries):
        """Swap r2_west_1 from houston to alabama should cascade championship
        when championship was houston (Charlie's bracket)."""
        charlie = _get_entry(entries, "Charlie")
        assert charlie.picks["r2_west_1"] == "houston"
        assert charlie.picks["championship"] == "houston"

        cf = counterfactual_entry(
            charlie, {"r2_west_1": "alabama"}, tournament, propagate=True,
        )

        assert cf.picks["r2_west_1"] == "alabama"
        assert cf.picks["championship"] == "alabama"  # cascaded

    def test_propagation_no_cascade_when_different_team(self, tournament, entries):
        """Swap r2_west_1 should NOT cascade championship when championship
        is a different team (Alice: championship=duke, not houston)."""
        alice = _get_entry(entries, "Alice")
        assert alice.picks["r2_west_1"] == "houston"
        assert alice.picks["championship"] == "duke"

        cf = counterfactual_entry(
            alice, {"r2_west_1": "alabama"}, tournament, propagate=True,
        )

        assert cf.picks["r2_west_1"] == "alabama"
        assert cf.picks["championship"] == "duke"  # unchanged

    def test_no_propagation_leaves_downstream_unchanged(self, tournament, entries):
        """Without propagate=True, downstream picks are not cascaded."""
        charlie = _get_entry(entries, "Charlie")

        cf = counterfactual_entry(
            charlie, {"r2_west_1": "alabama"}, tournament, propagate=False,
        )

        assert cf.picks["r2_west_1"] == "alabama"
        assert cf.picks["championship"] == "houston"  # not cascaded

    def test_propagation_multi_hop_cascade(self, tournament, entries):
        """Swap R1 pick should cascade through R2 and Championship.

        Charlie: r1_west_1v4=houston, r2_west_1=houston, championship=houston.
        Swapping r1_west_1v4 to arizona should cascade all three levels."""
        charlie = _get_entry(entries, "Charlie")
        assert charlie.picks["r1_west_1v4"] == "houston"
        assert charlie.picks["r2_west_1"] == "houston"
        assert charlie.picks["championship"] == "houston"

        cf = counterfactual_entry(
            charlie, {"r1_west_1v4": "arizona"}, tournament, propagate=True,
        )

        assert cf.picks["r1_west_1v4"] == "arizona"
        assert cf.picks["r2_west_1"] == "arizona"  # cascaded from R1
        assert cf.picks["championship"] == "arizona"  # cascaded from R1 through R2

    def test_multiple_overrides_round_ordered(self, tournament, entries):
        """Multiple overrides processed in round order, cascades don't collide.

        Charlie: r1_east_1v4=duke, r2_east_1=duke, r1_west_1v4=houston,
                 r2_west_1=houston, championship=houston.
        Swap both R1 games: duke->purdue (east) and houston->arizona (west).
        East cascade: r2_east_1 -> purdue (championship stays houston, not duke).
        West cascade: r2_west_1 -> arizona, championship -> arizona."""
        charlie = _get_entry(entries, "Charlie")

        cf = counterfactual_entry(
            charlie,
            {"r1_east_1v4": "purdue", "r1_west_1v4": "arizona"},
            tournament,
            propagate=True,
        )

        assert cf.picks["r1_east_1v4"] == "purdue"
        assert cf.picks["r2_east_1"] == "purdue"  # duke -> purdue cascaded
        assert cf.picks["r1_west_1v4"] == "arizona"
        assert cf.picks["r2_west_1"] == "arizona"  # houston -> arizona cascaded
        assert cf.picks["championship"] == "arizona"  # houston -> arizona cascaded

    def test_propagate_true_without_tournament_raises(self, entries):
        """propagate=True with tournament=None should raise ValueError."""
        alice = _get_entry(entries, "Alice")
        with pytest.raises(ValueError, match="tournament is required"):
            counterfactual_entry(alice, {"r2_west_1": "alabama"}, propagate=True)

    def test_scoreable_and_score_differs(self, tournament, results, entries):
        """Counterfactual entry should be scoreable, and swapping a resolved
        game pick should change the score."""
        from core.scoring import score_entry

        alice = _get_entry(entries, "Alice")
        original_scored = score_entry(alice, tournament, results)

        # Alice picked unc for r1_east_2v3, but gonzaga won.
        # Swapping to gonzaga should add 10 points.
        cf = counterfactual_entry(alice, {"r1_east_2v3": "gonzaga"})
        cf_scored = score_entry(cf, tournament, results)

        assert cf_scored.player_name == "Alice"
        assert cf_scored.total_points == original_scored.total_points + 10


class TestCompareCounterfactual:
    """Tests for compare_counterfactual() — WI-3."""

    def test_returns_comparison(self, tournament, results, entries):
        """Should return original and counterfactual win percentages."""
        result = compare_counterfactual(
            entries, "Alice", {"r2_west_1": "alabama"},
            tournament, results,
        )

        assert "original_pct" in result
        assert "counterfactual_pct" in result
        assert "delta" in result
        assert "original_results" in result
        assert "counterfactual_results" in result

    def test_delta_is_difference(self, tournament, results, entries):
        """Delta should equal counterfactual_pct - original_pct."""
        result = compare_counterfactual(
            entries, "Alice", {"r2_west_1": "alabama"},
            tournament, results,
        )

        expected_delta = result["counterfactual_pct"] - result["original_pct"]
        assert abs(result["delta"] - expected_delta) < 0.01

    def test_identical_swap_no_change(self, tournament, results, entries):
        """Swapping to the same team should produce zero delta."""
        alice = _get_entry(entries, "Alice")
        result = compare_counterfactual(
            entries, "Alice",
            {"r2_west_1": alice.picks["r2_west_1"]},
            tournament, results,
        )

        assert abs(result["delta"]) < 0.01

    def test_unknown_player_raises(self, tournament, results, entries):
        """Comparing a player not in entries should raise ValueError."""
        with pytest.raises(ValueError, match="not found in entries"):
            compare_counterfactual(
                entries, "NonexistentPlayer",
                {"r2_west_1": "alabama"},
                tournament, results,
            )
