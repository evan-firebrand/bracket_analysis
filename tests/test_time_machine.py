"""Tests for AnalysisContext view_as_of_round (Time Machine) filtering."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.context import AnalysisContext

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def full_ctx():
    """Full context with all fixture results (4 R1 + 1 R2 game)."""
    return AnalysisContext(data_dir=FIXTURES)


@pytest.fixture
def r1_ctx():
    """Context filtered to after Round 1 only."""
    return AnalysisContext(data_dir=FIXTURES, view_as_of_round=1)


class TestViewAsOfRound:
    def test_no_filter_returns_all_results(self, full_ctx):
        """Default (no filter) returns all completed games."""
        assert full_ctx.results.completed_count() == 5  # 4 R1 + 1 R2

    def test_filter_to_round_1_excludes_r2(self, r1_ctx):
        """Filtering to round 1 drops the R2 game."""
        assert r1_ctx.results.completed_count() == 4

    def test_filter_to_round_1_only_has_r1_slots(self, r1_ctx):
        """All remaining results must be round-1 slots."""
        for slot_id in r1_ctx.results.results:
            slot = r1_ctx.tournament.slots.get(slot_id)
            assert slot is not None
            assert slot.round == 1

    def test_filter_to_round_2_returns_all(self, full_ctx):
        """Filtering to round 2 when only R1+R2 exist returns all results."""
        ctx = AnalysisContext(data_dir=FIXTURES, view_as_of_round=2)
        assert ctx.results.completed_count() == 5

    def test_view_round_attribute_set(self, r1_ctx, full_ctx):
        """view_round is set correctly on the context."""
        assert r1_ctx.view_round == 1
        assert full_ctx.view_round is None

    def test_current_round_reflects_filter(self, r1_ctx, full_ctx):
        """current_round() should reflect the filtered state."""
        assert r1_ctx.current_round() == 1
        assert full_ctx.current_round() == 2

    def test_alive_teams_reflect_filter(self, r1_ctx, full_ctx):
        """Alive teams differ — teams eliminated in R1 show as alive pre-filter."""
        # In the full context someone lost in R2; in R1 view they're still "alive"
        r1_alive = r1_ctx.alive_teams
        full_alive = full_ctx.alive_teams
        # R1 view must have >= teams alive than full (no R2 eliminations yet)
        assert len(r1_alive) >= len(full_alive)

    def test_leaderboard_reflects_filter(self, r1_ctx, full_ctx):
        """Leaderboard totals are lower after filtering to R1 (R2 points excluded)."""
        r1_total = r1_ctx.leaderboard["Total"].sum()
        full_total = full_ctx.leaderboard["Total"].sum()
        assert r1_total <= full_total
