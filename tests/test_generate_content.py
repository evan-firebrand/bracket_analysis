"""Tests for scripts/generate_content.py.

Tests cover the non-API logic only: context assembly, prompt building,
schema validation, and dry-run behaviour. The Claude API call itself
is mocked to avoid network dependencies.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure project root is on the path so imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.generate_content import (
    build_prompt,
    build_prompt_context,
    main,
    validate_schema,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ctx():
    """Load AnalysisContext from test fixtures."""
    from core.context import AnalysisContext

    return AnalysisContext(data_dir=str(FIXTURES_DIR))


# ---------------------------------------------------------------------------
# build_prompt_context
# ---------------------------------------------------------------------------


def test_build_prompt_context_shape():
    """build_prompt_context returns a dict with all required top-level keys."""
    ctx = _make_ctx()
    summary = build_prompt_context(ctx)

    expected_keys = {
        "year",
        "current_round",
        "current_round_name",
        "games_completed",
        "games_remaining",
        "leaderboard",
        "upsets",
        "alive_teams",
    }
    assert expected_keys <= set(summary.keys()), (
        f"Missing keys: {expected_keys - set(summary.keys())}"
    )

    # Leaderboard rows have the expected shape
    assert isinstance(summary["leaderboard"], list)
    assert len(summary["leaderboard"]) > 0
    first = summary["leaderboard"][0]
    for field in ("rank", "player", "total", "max_possible", "correct"):
        assert field in first, f"leaderboard row missing '{field}'"

    # Games counts are non-negative integers
    assert summary["games_completed"] >= 0
    assert summary["games_remaining"] >= 0


def test_build_prompt_context_upset_detection():
    """build_prompt_context detects games where winner seed > loser seed by >=4."""
    ctx = _make_ctx()
    # Fixture: r1_east_2v3 — gonzaga (seed 3) beat unc (seed 2), diff=1 → not an upset.
    # No fixture game has seed diff >=4, so upsets should be empty.
    summary = build_prompt_context(ctx)
    assert isinstance(summary["upsets"], list)
    # All detected upsets must have winner_seed < loser_seed (winner was the underdog)
    for u in summary["upsets"]:
        assert u["winner_seed"] > u["loser_seed"] or (
            u["loser_seed"] - u["winner_seed"] >= 4
        ), f"Unexpected upset entry: {u}"


# ---------------------------------------------------------------------------
# build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_contains_players():
    """Player names from the context appear in the generated prompt string."""
    ctx = _make_ctx()
    summary = build_prompt_context(ctx)
    prompt = build_prompt(summary)

    for row in summary["leaderboard"]:
        assert row["player"] in prompt, (
            f"Player '{row['player']}' not found in prompt"
        )


def test_build_prompt_contains_schema_hint():
    """The prompt instructs Claude to return JSON with the correct schema keys."""
    ctx = _make_ctx()
    summary = build_prompt_context(ctx)
    prompt = build_prompt(summary)

    for key in ("headline", "stories", "recap", "player_summaries"):
        assert key in prompt, f"Schema key '{key}' missing from prompt"


# ---------------------------------------------------------------------------
# validate_schema
# ---------------------------------------------------------------------------


def _valid_payload(player_names: list[str] | None = None) -> dict:
    """Return a minimal valid approved.json payload."""
    players = player_names or ["alice", "bob"]
    return {
        "headline": "Duke is running away with it.",
        "stories": [
            {"title": "On top", "body": "Duke leads by 40 points."},
            {"title": "Hanging in", "body": "Bob still alive. Barely."},
            {"title": "Bracket chaos", "body": "Three upsets in the West."},
        ],
        "recap": "Duke is up 40. Alice is cruising. Bob needs miracles.",
        "player_summaries": {p: f"{p.title()} is doing fine." for p in players},
    }


def test_validate_schema_passes():
    """A correctly structured dict passes validation without raising."""
    validate_schema(_valid_payload())  # should not raise


def test_validate_schema_missing_headline():
    """Missing 'headline' field raises ValueError."""
    data = _valid_payload()
    del data["headline"]
    with pytest.raises(ValueError, match="headline"):
        validate_schema(data)


def test_validate_schema_missing_field():
    """Any missing required field raises ValueError."""
    for field in ("headline", "stories", "recap", "player_summaries"):
        data = _valid_payload()
        del data[field]
        with pytest.raises(ValueError):
            validate_schema(data)


def test_validate_schema_stories_structure():
    """A story missing 'body' raises ValueError."""
    data = _valid_payload()
    data["stories"] = [{"title": "No body here"}]  # missing 'body'
    with pytest.raises(ValueError, match="body"):
        validate_schema(data)


def test_validate_schema_empty_stories():
    """An empty stories list raises ValueError."""
    data = _valid_payload()
    data["stories"] = []
    with pytest.raises(ValueError, match="stories"):
        validate_schema(data)


# ---------------------------------------------------------------------------
# main() — dry run
# ---------------------------------------------------------------------------


def test_main_dry_run(tmp_path, capsys):
    """--dry-run prints context and prompt without writing files or calling the API."""
    # Patch the Anthropic client to ensure it is never instantiated
    with patch("scripts.generate_content.anthropic.Anthropic") as mock_client:
        main([
            "--data-dir", str(FIXTURES_DIR),
            "--dry-run",
        ])
        mock_client.assert_not_called()

    captured = capsys.readouterr()
    assert "CONTEXT SUMMARY" in captured.out
    assert "PROMPT" in captured.out

    # No file should have been written under fixtures
    assert not (FIXTURES_DIR / "content" / "approved.json").exists()
