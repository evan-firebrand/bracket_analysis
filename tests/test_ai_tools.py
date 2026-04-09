"""Tests for core/ai/tools.py — AI tool library.

Each test calls execute_tool() and asserts the result has the expected shape.
Uses frozen fixtures in tests/fixtures/ so tests are deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.ai.tools import execute_tool, get_tool_schemas
from core.context import AnalysisContext

FIXTURE_DIR = Path("tests/fixtures")


@pytest.fixture(scope="module")
def ctx() -> AnalysisContext:
    return AnalysisContext(FIXTURE_DIR)


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def test_get_tool_schemas_count():
    schemas = get_tool_schemas()
    assert len(schemas) == 16, f"Expected 16 tools, got {len(schemas)}"


def test_tool_schemas_have_required_keys():
    for schema in get_tool_schemas():
        assert "name" in schema, f"Missing 'name' in schema: {schema}"
        assert "description" in schema, f"Missing 'description' in {schema['name']}"
        assert "input_schema" in schema, f"Missing 'input_schema' in {schema['name']}"
        assert schema["input_schema"]["type"] == "object"


# ---------------------------------------------------------------------------
# Unknown tool
# ---------------------------------------------------------------------------


def test_unknown_tool(ctx: AnalysisContext):
    result = json.loads(execute_tool("nonexistent_tool", {}, ctx))
    assert "error" in result
    assert "nonexistent_tool" in result["error"]


# ---------------------------------------------------------------------------
# get_pool_state
# ---------------------------------------------------------------------------


def test_get_pool_state(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_pool_state", {}, ctx))
    assert "round" in result
    assert "round_name" in result
    assert "games_remaining" in result
    assert isinstance(result["games_remaining"], int)
    assert "total_games" in result
    assert "total_players" in result
    assert result["total_players"] > 0


# ---------------------------------------------------------------------------
# get_leaderboard
# ---------------------------------------------------------------------------


def test_get_leaderboard(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_leaderboard", {"limit": 3}, ctx))
    assert isinstance(result, list)
    assert len(result) <= 3
    for row in result:
        assert "rank" in row
        assert "player" in row
        assert "score" in row
        assert "max_possible" in row


def test_get_leaderboard_no_limit(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_leaderboard", {}, ctx))
    assert isinstance(result, list)
    players = ctx.player_names()
    assert len(result) == len(players)


def test_get_leaderboard_rank_ordering(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_leaderboard", {}, ctx))
    ranks = [r["rank"] for r in result]
    assert ranks == sorted(ranks)


# ---------------------------------------------------------------------------
# get_round_results
# ---------------------------------------------------------------------------


def test_get_round_results(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_round_results", {}, ctx))
    assert "round" in result
    assert "games" in result
    assert isinstance(result["games"], list)
    assert "is_complete" in result


def test_get_round_results_game_fields(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_round_results", {}, ctx))
    for game in result["games"]:
        assert "slot_id" in game
        assert "winner" in game
        assert "loser" in game
        assert "is_upset" in game


# ---------------------------------------------------------------------------
# get_player
# ---------------------------------------------------------------------------


def test_get_player(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(execute_tool("get_player", {"name": players[0]}, ctx))
    assert "rank" in result
    assert "score" in result
    assert "max_possible" in result
    assert "correct_picks" in result
    assert "dead_picks" in result
    assert "pending_picks" in result
    assert "is_eliminated" in result


def test_get_player_not_found(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_player", {"name": "Nonexistent Player"}, ctx))
    assert "error" in result


# ---------------------------------------------------------------------------
# get_player_bracket
# ---------------------------------------------------------------------------


def test_get_player_bracket(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(execute_tool("get_player_bracket", {"name": players[0]}, ctx))
    assert isinstance(result, list)
    assert len(result) > 0
    for pick in result:
        assert "slot_id" in pick
        assert "round" in pick
        assert "team_picked" in pick
        assert "alive" in pick
        assert "correct" in pick
        assert pick["correct"] in ("correct", "incorrect", "pending")


def test_get_player_bracket_round_filter(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool("get_player_bracket", {"name": players[0], "round": 1}, ctx)
    )
    assert isinstance(result, list)
    for pick in result:
        assert pick["round"] == 1


def test_get_player_bracket_not_found(ctx: AnalysisContext):
    result = json.loads(
        execute_tool("get_player_bracket", {"name": "Ghost Player"}, ctx)
    )
    assert "error" in result


# ---------------------------------------------------------------------------
# get_player_critical_games
# ---------------------------------------------------------------------------


def test_get_player_critical_games(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool("get_player_critical_games", {"name": players[0]}, ctx)
    )
    # Returns list (may be empty if no swings) or dict with error
    assert isinstance(result, (list, dict))
    if isinstance(result, list):
        for game in result:
            assert "slot_id" in game
            assert "team_a" in game
            assert "team_b" in game
            assert "swing_pct" in game


def test_get_player_critical_games_top_n(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool(
            "get_player_critical_games", {"name": players[0], "top_n": 1}, ctx
        )
    )
    assert isinstance(result, (list, dict))
    if isinstance(result, list):
        assert len(result) <= 1


# ---------------------------------------------------------------------------
# get_player_clinch_status
# ---------------------------------------------------------------------------


def test_get_player_clinch_status(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool("get_player_clinch_status", {"name": players[0]}, ctx)
    )
    assert "clinched" in result
    assert "can_win" in result
    assert "is_eliminated" in result
    assert "description" in result
    assert isinstance(result["clinched"], bool)
    assert isinstance(result["can_win"], bool)


# ---------------------------------------------------------------------------
# get_player_best_path
# ---------------------------------------------------------------------------


def test_get_player_best_path(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool("get_player_best_path", {"name": players[0]}, ctx)
    )
    assert "steps" in result or "error" in result
    if "steps" in result:
        assert isinstance(result["steps"], list)
        assert "win_probability" in result
        assert "path_probability" in result


def test_get_player_best_path_step_fields(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool("get_player_best_path", {"name": players[0]}, ctx)
    )
    if "steps" in result:
        for step in result["steps"]:
            assert "slot_id" in step
            assert "round" in step
            assert "root_for_team" in step


# ---------------------------------------------------------------------------
# compare_players
# ---------------------------------------------------------------------------


def test_compare_players(ctx: AnalysisContext):
    players = ctx.player_names()
    result = json.loads(
        execute_tool(
            "compare_players",
            {"player_a": players[0], "player_b": players[1]},
            ctx,
        )
    )
    assert "shared_picks" in result
    assert "pending_disagreements" in result
    assert "decisive_games" in result
    assert isinstance(result["decisive_games"], list)


def test_compare_players_not_found(ctx: AnalysisContext):
    result = json.loads(
        execute_tool(
            "compare_players",
            {"player_a": "Alice", "player_b": "Nobody"},
            ctx,
        )
    )
    assert "error" in result


# ---------------------------------------------------------------------------
# get_team
# ---------------------------------------------------------------------------


def test_get_team_by_slug(ctx: AnalysisContext):
    # Pick a team from the tournament
    slug = next(iter(ctx.tournament.teams))
    result = json.loads(execute_tool("get_team", {"team": slug}, ctx))
    assert "name" in result
    assert "seed" in result
    assert "region" in result
    assert "alive" in result
    assert result["slug"] == slug


def test_get_team_by_name(ctx: AnalysisContext):
    # Find a team name and search by it
    first_team = next(iter(ctx.tournament.teams.values()))
    result = json.loads(execute_tool("get_team", {"team": first_team.name}, ctx))
    assert "slug" in result
    assert result["name"] == first_team.name


def test_get_team_not_found(ctx: AnalysisContext):
    result = json.loads(execute_tool("get_team", {"team": "nonexistent_team_xyz"}, ctx))
    assert "error" in result


# ---------------------------------------------------------------------------
# get_team_pickers
# ---------------------------------------------------------------------------


def test_get_team_pickers(ctx: AnalysisContext):
    # Pick a team from round 1
    slug = next(iter(ctx.tournament.teams))
    result = json.loads(
        execute_tool("get_team_pickers", {"team": slug, "round": 1}, ctx)
    )
    assert "team" in result
    assert "pickers" in result
    assert "pct_of_pool" in result
    assert "total_entries" in result
    assert isinstance(result["pickers"], list)


# ---------------------------------------------------------------------------
# get_team_odds
# ---------------------------------------------------------------------------


def test_get_team_odds(ctx: AnalysisContext):
    slug = next(iter(ctx.tournament.teams))
    result = json.loads(execute_tool("get_team_odds", {"team": slug}, ctx))
    assert "team" in result
    # May or may not have odds — either way should not raise
    assert "championship_pct" in result or "note" in result


# ---------------------------------------------------------------------------
# run_scenario
# ---------------------------------------------------------------------------


def test_run_scenario(ctx: AnalysisContext):
    from core.tournament import get_remaining_games

    remaining = get_remaining_games(ctx.tournament, ctx.results)
    # Find first game with both participants known
    game = next(
        (g for g in remaining if g["team_a"] and g["team_b"]),
        None,
    )
    if game is None:
        pytest.skip("No games with known participants to run scenario on.")

    assumption = {"slot_id": game["slot_id"], "winner": game["team_a"]}
    result = json.loads(
        execute_tool("run_scenario", {"assumptions": [assumption]}, ctx)
    )
    assert "players" in result
    assert isinstance(result["players"], list)
    assert len(result["players"]) > 0
    for player in result["players"]:
        assert "name" in player
        assert "win_pct_before" in player
        assert "win_pct_after" in player
        assert "delta_pct" in player


def test_run_scenario_empty_assumptions(ctx: AnalysisContext):
    result = json.loads(
        execute_tool("run_scenario", {"assumptions": []}, ctx)
    )
    assert "players" in result
    assert isinstance(result["players"], list)


# ---------------------------------------------------------------------------
# get_pick_popularity
# ---------------------------------------------------------------------------


def test_get_pick_popularity(ctx: AnalysisContext):
    slug = next(iter(ctx.tournament.teams))
    result = json.loads(
        execute_tool("get_pick_popularity", {"team": slug, "round": 1}, ctx)
    )
    assert "team" in result
    assert "pickers" in result
    assert "pct_of_pool" in result
    assert "total_entries" in result
    assert isinstance(result["pickers"], list)


# ---------------------------------------------------------------------------
# list_players
# ---------------------------------------------------------------------------


def test_list_players(ctx: AnalysisContext):
    result = json.loads(execute_tool("list_players", {}, ctx))
    assert "players" in result
    assert len(result["players"]) > 0
    assert isinstance(result["players"], list)


def test_list_players_matches_context(ctx: AnalysisContext):
    result = json.loads(execute_tool("list_players", {}, ctx))
    assert set(result["players"]) == set(ctx.player_names())


# ---------------------------------------------------------------------------
# list_remaining_games
# ---------------------------------------------------------------------------


def test_list_remaining_games(ctx: AnalysisContext):
    result = json.loads(execute_tool("list_remaining_games", {}, ctx))
    assert isinstance(result, list)


def test_list_remaining_games_fields(ctx: AnalysisContext):
    result = json.loads(execute_tool("list_remaining_games", {}, ctx))
    for game in result:
        assert "slot_id" in game
        assert "round" in game
        assert "region" in game
        assert "team_a" in game
        assert "team_b" in game
        # TBD is allowed for unknown participants
        assert game["team_a"] is not None
        assert game["team_b"] is not None
