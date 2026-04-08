"""AI tool library — Anthropic-compatible tool schemas and adapter functions.

Each tool has:
- A JSON schema dict (added to TOOLS list) in Anthropic tool format
- An adapter function (added to ADAPTERS dict) that calls core/ functions

All adapters take (ctx: AnalysisContext, **kwargs) and return a JSON-serializable
dict or list. The execute_tool() helper dispatches by name and returns a JSON string.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path

from core.comparison import head_to_head, pick_popularity
from core.context import AnalysisContext
from core.recap import round_recap
from core.scenarios import (
    best_path,
    clinch_scenarios,
    monte_carlo_scenarios,
    player_critical_games,
    run_scenarios,
    what_if,
)
from core.scoring import ROUND_NAMES
from core.tournament import get_participants_for_slot, get_remaining_games

# Alias builtins.round to avoid shadowing by `round` parameter names in adapters
_round = builtins.round

TOOLS: list[dict] = []
ADAPTERS: dict[str, callable] = {}


def get_tool_schemas() -> list[dict]:
    """Return all Anthropic-compatible tool schemas."""
    return TOOLS


def execute_tool(name: str, input_args: dict, ctx: AnalysisContext) -> str:
    """Execute a named tool with given arguments. Returns a JSON string."""
    adapter = ADAPTERS.get(name)
    if adapter is None:
        return json.dumps({"error": f"Unknown tool: {name}"})
    try:
        result = adapter(ctx, **input_args)
        return json.dumps(result, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 1: get_pool_state
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_pool_state",
    "description": (
        "Get the current state of the tournament pool: current round, games remaining, "
        "total players, and when data was last updated."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
})


def _get_pool_state(ctx: AnalysisContext) -> dict:
    current_round = ctx.current_round()
    return {
        "round": current_round,
        "round_name": ROUND_NAMES.get(current_round, f"Round {current_round}"),
        "games_remaining": ctx.games_remaining(),
        "total_games": len(ctx.tournament.slots),
        "total_players": len(ctx.entries),
        "last_updated": ctx.results.last_updated,
    }


ADAPTERS["get_pool_state"] = _get_pool_state


# ---------------------------------------------------------------------------
# Tool 2: get_leaderboard
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_leaderboard",
    "description": (
        "Get the current leaderboard ranked by total points. "
        "Returns player rank, score, and max possible score."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "limit": {
                "type": "integer",
                "description": "Maximum number of players to return (default: all players).",
            },
        },
        "required": [],
    },
})


def _get_leaderboard(ctx: AnalysisContext, limit: int | None = None) -> list[dict]:
    df = ctx.leaderboard
    if limit is not None:
        df = df.head(limit)
    result = []
    for _, row in df.iterrows():
        result.append({
            "rank": int(row["Rank"]),
            "player": row["Player"],
            "score": int(row["Total"]),
            "max_possible": int(row["Max Possible"]),
        })
    return result


ADAPTERS["get_leaderboard"] = _get_leaderboard


# ---------------------------------------------------------------------------
# Tool 3: get_round_results
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_round_results",
    "description": (
        "Get a recap of the most recently completed round: games played, upsets, "
        "and whether the round is complete."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "round": {
                "type": "integer",
                "description": "Round number to recap (optional; defaults to the most recent round).",
            },
        },
        "required": [],
    },
})


def _get_round_results(ctx: AnalysisContext, round: int | None = None) -> dict:
    rr = round_recap(ctx.tournament, ctx.results, ctx.entries)
    if rr is None:
        return {"round": None, "games": [], "is_complete": False, "message": "No games played yet."}

    games = []
    for g in rr.games:
        games.append({
            "slot_id": g.slot_id,
            "region": g.region,
            "winner": g.winner,
            "loser": g.loser,
            "score": g.score,
            "pick_count": g.pick_count,
            "total_players": g.total_players,
            "is_upset": g.is_upset,
        })

    return {
        "round": rr.round,
        "round_name": rr.round_name,
        "games": games,
        "total_games_in_round": rr.total_games_in_round,
        "is_complete": rr.is_complete,
    }


ADAPTERS["get_round_results"] = _get_round_results


# ---------------------------------------------------------------------------
# Tool 4: get_player
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_player",
    "description": (
        "Get a player's current standings: rank, score, max possible, and pick breakdown "
        "(correct, dead, and pending picks)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Player name (exact match).",
            },
        },
        "required": ["name"],
    },
})


def _get_player(ctx: AnalysisContext, name: str) -> dict:
    scored = ctx.get_scored(name)
    if scored is None:
        return {"error": f"Player '{name}' not found."}

    # Find rank from leaderboard
    lb = ctx.leaderboard
    row = lb[lb["Player"] == name]
    rank = int(row["Rank"].iloc[0]) if not row.empty else None

    # is_eliminated: max_possible < current leader's score
    if not lb.empty:
        leader_score = int(lb["Total"].iloc[0])
        is_eliminated = scored.max_possible < leader_score
    else:
        is_eliminated = False

    return {
        "name": name,
        "rank": rank,
        "score": scored.total_points,
        "max_possible": scored.max_possible,
        "is_eliminated": is_eliminated,
        "correct_picks": len(scored.correct_picks),
        "dead_picks": len(scored.incorrect_picks),
        "pending_picks": len(scored.pending_picks),
    }


ADAPTERS["get_player"] = _get_player


# ---------------------------------------------------------------------------
# Tool 5: get_player_bracket
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_player_bracket",
    "description": (
        "Get a player's full bracket picks with status (correct, incorrect, pending). "
        "Optionally filter to a specific round."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Player name (exact match).",
            },
            "round": {
                "type": "integer",
                "description": "Filter to this round number (optional).",
            },
        },
        "required": ["name"],
    },
})


def _get_player_bracket(
    ctx: AnalysisContext, name: str, round: int | None = None
) -> list[dict] | dict:
    entry = ctx.get_entry(name)
    if entry is None:
        return {"error": f"Player '{name}' not found."}

    scored = ctx.get_scored(name)
    correct_set = set(scored.correct_picks) if scored else set()
    incorrect_set = set(scored.incorrect_picks) if scored else set()

    picks = []
    for slot_id, team_slug in entry.picks.items():
        slot = ctx.tournament.slots.get(slot_id)
        if slot is None:
            continue
        if round is not None and slot.round != round:
            continue

        if slot_id in correct_set:
            status = "correct"
        elif slot_id in incorrect_set:
            status = "incorrect"
        else:
            status = "pending"

        picks.append({
            "slot_id": slot_id,
            "round": slot.round,
            "team_picked": team_slug,
            "alive": team_slug in ctx.alive_teams,
            "correct": status,
        })

    picks.sort(key=lambda p: (p["round"], p["slot_id"]))
    return picks


ADAPTERS["get_player_bracket"] = _get_player_bracket


# ---------------------------------------------------------------------------
# Tool 6: get_player_critical_games
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_player_critical_games",
    "description": (
        "Get the upcoming games that most affect a player's win probability. "
        "Requires scenario analysis to be available."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Player name (exact match).",
            },
            "top_n": {
                "type": "integer",
                "description": "Number of critical games to return (default: 3).",
            },
        },
        "required": ["name"],
    },
})


def _get_player_critical_games(
    ctx: AnalysisContext, name: str, top_n: int = 3
) -> list[dict] | dict:
    if ctx.scenario_results is None:
        return {"error": "Scenario results not available."}

    games = player_critical_games(ctx.scenario_results, name, top_n=top_n)
    result = []
    for g in games:
        result.append({
            "slot_id": g["slot_id"],
            "team_a": g["team_a"],
            "team_b": g["team_b"],
            "win_if_a_pct": round(g["win_if_a"] * 100, 1),
            "win_if_b_pct": round(g["win_if_b"] * 100, 1),
            "swing_pct": round(g["swing"] * 100, 1),
            "must_win_team": g.get("must_win_team"),
        })
    return result


ADAPTERS["get_player_critical_games"] = _get_player_critical_games


# ---------------------------------------------------------------------------
# Tool 7: get_player_clinch_status
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_player_clinch_status",
    "description": (
        "Check whether a player has clinched first place, can still win, "
        "or is mathematically eliminated."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Player name (exact match).",
            },
        },
        "required": ["name"],
    },
})


def _get_player_clinch_status(ctx: AnalysisContext, name: str) -> dict:
    cs = clinch_scenarios(ctx.entries, name, ctx.tournament, ctx.results)

    # Build a human-readable description
    if cs.get("clinched"):
        description = f"{name} has clinched first place — no remaining outcomes can change that."
    elif not cs.get("can_win"):
        description = f"{name} is mathematically eliminated and cannot win the pool."
    else:
        min_picks = cs.get("min_picks_needed", 0)
        description = (
            f"{name} can still win. They need at least {min_picks} correct pick(s) "
            "from their remaining games."
        )

    return {
        "clinched": cs.get("clinched", False),
        "can_win": cs.get("can_win", False),
        "is_eliminated": not cs.get("can_win", True),
        "min_picks_needed": cs.get("min_picks_needed", 0),
        "description": description,
    }


ADAPTERS["get_player_clinch_status"] = _get_player_clinch_status


# ---------------------------------------------------------------------------
# Tool 8: get_player_best_path
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_player_best_path",
    "description": (
        "Find the most likely sequence of game outcomes that gives a player their "
        "best chance of winning the pool."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Player name (exact match).",
            },
        },
        "required": ["name"],
    },
})


def _get_player_best_path(ctx: AnalysisContext, name: str) -> dict:
    if ctx.scenario_results is None:
        return {"error": "Scenario results not available."}

    bp = best_path(
        ctx.scenario_results, name, ctx.entries, ctx.tournament, ctx.results
    )

    steps = []
    for s in bp.get("steps", []):
        steps.append({
            "slot_id": s["slot_id"],
            "round": s["round"],
            "root_for_team": s["root_for"],
            "opponent": s.get("opponent"),
        })

    return {
        "steps": steps,
        "win_probability": round(bp.get("win_probability", 0.0) * 100, 1),
        "path_probability": round(bp.get("path_probability", 0.0) * 100, 1),
        "odds_source": bp.get("odds_source", "unknown"),
    }


ADAPTERS["get_player_best_path"] = _get_player_best_path


# ---------------------------------------------------------------------------
# Tool 9: compare_players
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "compare_players",
    "description": (
        "Compare two players head-to-head: shared picks, where each has an advantage, "
        "and upcoming decisive games where they differ."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "player_a": {
                "type": "string",
                "description": "First player name (exact match).",
            },
            "player_b": {
                "type": "string",
                "description": "Second player name (exact match).",
            },
        },
        "required": ["player_a", "player_b"],
    },
})


def _compare_players(ctx: AnalysisContext, player_a: str, player_b: str) -> dict:
    entry_a = ctx.get_entry(player_a)
    entry_b = ctx.get_entry(player_b)
    if entry_a is None:
        return {"error": f"Player '{player_a}' not found."}
    if entry_b is None:
        return {"error": f"Player '{player_b}' not found."}

    h2h = head_to_head(entry_a, entry_b, ctx.tournament, ctx.results)

    # Build decisive_games from disagree_pending (games where they differ and not yet played)
    decisive = []
    for slot_id in h2h.disagree_pending:
        slot = ctx.tournament.slots.get(slot_id)
        pick_a = entry_a.picks.get(slot_id)
        pick_b = entry_b.picks.get(slot_id)
        decisive.append({
            "slot_id": slot_id,
            "round": slot.round if slot else None,
            f"{player_a}_pick": pick_a,
            f"{player_b}_pick": pick_b,
        })

    return {
        "player_a": player_a,
        "player_b": player_b,
        "shared_picks": len(h2h.agree),
        "unique_to_a": len(h2h.disagree_a_right),
        "unique_to_b": len(h2h.disagree_b_right),
        "both_wrong": len(h2h.disagree_both_wrong),
        "pending_disagreements": len(h2h.disagree_pending),
        "pending_points_at_stake": h2h.pending_points,
        "decisive_games": decisive,
    }


ADAPTERS["compare_players"] = _compare_players


# ---------------------------------------------------------------------------
# Tool 10: get_team
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_team",
    "description": (
        "Look up a team by slug or name. Returns seed, region, and whether the team "
        "is still alive in the tournament."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "description": "Team slug (e.g. 'duke') or full name (e.g. 'Duke Blue Devils').",
            },
        },
        "required": ["team"],
    },
})


def _get_team(ctx: AnalysisContext, team: str) -> dict:
    # Try slug lookup first
    t = ctx.tournament.teams.get(team)

    # Fall back to case-insensitive name lookup
    if t is None:
        team_lower = team.lower()
        for candidate in ctx.tournament.teams.values():
            if candidate.name.lower() == team_lower:
                t = candidate
                break

    if t is None:
        return {"error": f"Team '{team}' not found."}

    return {
        "slug": t.slug,
        "name": t.name,
        "seed": t.seed,
        "region": t.region,
        "alive": t.slug in ctx.alive_teams,
    }


ADAPTERS["get_team"] = _get_team


# ---------------------------------------------------------------------------
# Tool 11: get_team_pickers
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_team_pickers",
    "description": (
        "Find which players picked a team to win a specific round, and what percentage "
        "of the pool picked them."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "description": "Team slug (e.g. 'duke').",
            },
            "round": {
                "type": "integer",
                "description": "Round number to check (1=Round of 64, 6=Championship).",
            },
        },
        "required": ["team", "round"],
    },
})


def _get_team_pickers(ctx: AnalysisContext, team: str, round: int) -> dict:
    round_num = round
    pickers = []
    total = len(ctx.entries)

    for slot_id in ctx.tournament.slot_order:
        slot = ctx.tournament.slots.get(slot_id)
        if slot is None or slot.round != round_num:
            continue
        for entry in ctx.entries:
            if entry.picks.get(slot_id) == team:
                pickers.append(entry.player_name)

    # Deduplicate (a player can only appear once per round)
    pickers = list(dict.fromkeys(pickers))
    pct = len(pickers) / total * 100 if total > 0 else 0.0

    return {
        "team": team,
        "round": round_num,
        "round_name": ROUND_NAMES.get(round_num, f"Round {round_num}"),
        "pickers": pickers,
        "pct_of_pool": _round(pct, 1),
        "total_entries": total,
    }


ADAPTERS["get_team_pickers"] = _get_team_pickers


# ---------------------------------------------------------------------------
# Tool 12: get_team_odds
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_team_odds",
    "description": (
        "Get betting odds / win probabilities for a team, if odds data is available. "
        "Returns empty dict if no odds data exists."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "description": "Team slug (e.g. 'duke').",
            },
        },
        "required": ["team"],
    },
})


def _get_team_odds(ctx: AnalysisContext, team: str) -> dict:
    # Try to load odds from data directory (same dir as tournament.json)
    # We infer data_dir from the context's tournament path by looking at
    # the ai_content path pattern, or try common paths.
    odds_data = _load_odds_for_ctx(ctx)
    if not odds_data:
        return {"team": team, "championship_pct": None, "round_probs": {}, "note": "No odds data available."}

    teams_odds = odds_data.get("teams", {})
    team_info = teams_odds.get(team)
    if team_info is None:
        return {"team": team, "championship_pct": None, "round_probs": {}, "note": f"No odds found for team '{team}'."}

    return {
        "team": team,
        "championship_pct": team_info.get("championship"),
        "round_probs": team_info.get("round_probs", {}),
    }


def _load_odds_for_ctx(ctx: AnalysisContext) -> dict | None:
    """Try to load odds.json from candidate data directories."""
    # Try standard locations
    for candidate in [Path("data"), Path("tests/fixtures"), Path(".")]:
        odds_path = candidate / "odds.json"
        if odds_path.exists():
            try:
                with open(odds_path) as f:
                    data = f.read()
                import json as _json
                return _json.loads(data)
            except Exception:
                continue
    return None


ADAPTERS["get_team_odds"] = _get_team_odds


# ---------------------------------------------------------------------------
# Tool 13: run_scenario
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "run_scenario",
    "description": (
        "Run a what-if scenario: assume specific game outcomes, then re-simulate "
        "the rest of the tournament to see how win probabilities change for each player."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "assumptions": {
                "type": "array",
                "description": "List of assumed game outcomes.",
                "items": {
                    "type": "object",
                    "properties": {
                        "slot_id": {
                            "type": "string",
                            "description": "The game slot ID.",
                        },
                        "winner": {
                            "type": "string",
                            "description": "Team slug of the assumed winner.",
                        },
                    },
                    "required": ["slot_id", "winner"],
                },
            },
        },
        "required": ["assumptions"],
    },
})


def _run_scenario(ctx: AnalysisContext, assumptions: list[dict]) -> dict:
    # Get baseline win probabilities
    base_sr = ctx.scenario_results
    base_total = base_sr.total_scenarios if base_sr else 0

    # Apply each assumption by chaining what_if() calls
    modified_results = ctx.results
    for assumption in assumptions:
        slot_id = assumption["slot_id"]
        winner = assumption["winner"]

        # Find the loser: whoever is NOT the winner in that slot
        team_a, team_b = get_participants_for_slot(
            ctx.tournament, modified_results, slot_id
        )
        if team_a is None and team_b is None:
            # Try from the original results structure
            slot = ctx.tournament.slots.get(slot_id)
            if slot and slot.round == 1:
                team_a, team_b = slot.top_team, slot.bottom_team

        if team_a == winner:
            loser = team_b
        elif team_b == winner:
            loser = team_a
        else:
            # Winner isn't one of the known participants — best effort
            loser = team_b if team_a == winner else team_a

        if loser is None:
            continue

        modified_results = what_if(modified_results, slot_id, winner, loser)

    # Run scenarios on the modified results.
    # Use monte_carlo_scenarios directly when we want a controlled simulation count,
    # otherwise fall back to run_scenarios (which auto-selects engine).
    from core.tournament import get_remaining_slots
    remaining = get_remaining_slots(ctx.tournament, modified_results)
    if len(remaining) > 15:
        scenario_sr = monte_carlo_scenarios(
            ctx.entries, ctx.tournament, modified_results, n_simulations=10_000
        )
    else:
        scenario_sr = run_scenarios(ctx.entries, ctx.tournament, modified_results)
    new_total = scenario_sr.total_scenarios

    players = []
    for entry in ctx.entries:
        name = entry.player_name

        win_pct_before = (
            base_sr.win_counts.get(name, 0) / base_total * 100
            if base_sr and base_total > 0
            else 0.0
        )
        win_pct_after = (
            scenario_sr.win_counts.get(name, 0) / new_total * 100
            if new_total > 0
            else 0.0
        )

        # Rank change: rank in base vs rank in scenario
        base_rank = _rank_by_wins(base_sr, name) if base_sr else None
        new_rank = _rank_by_wins(scenario_sr, name)

        players.append({
            "name": name,
            "win_pct_before": round(win_pct_before, 1),
            "win_pct_after": round(win_pct_after, 1),
            "delta_pct": round(win_pct_after - win_pct_before, 1),
            "rank_before": base_rank,
            "rank_after": new_rank,
        })

    # Sort by win_pct_after descending
    players.sort(key=lambda p: -p["win_pct_after"])

    return {
        "assumptions": assumptions,
        "engine": scenario_sr.engine,
        "total_scenarios": new_total,
        "players": players,
    }


def _rank_by_wins(sr, player_name: str) -> int | None:
    """Rank player by win_counts among all players (1 = most wins)."""
    if sr is None:
        return None
    sorted_players = sorted(sr.win_counts.items(), key=lambda x: -x[1])
    for i, (name, _) in enumerate(sorted_players, 1):
        if name == player_name:
            return i
    return None


ADAPTERS["run_scenario"] = _run_scenario


# ---------------------------------------------------------------------------
# Tool 14: get_pick_popularity
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "get_pick_popularity",
    "description": (
        "Find how popular a team pick is for a given round: who picked them and "
        "what percentage of the pool chose them."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "team": {
                "type": "string",
                "description": "Team slug (e.g. 'duke').",
            },
            "round": {
                "type": "integer",
                "description": "Round number (1=Round of 64, 6=Championship).",
            },
        },
        "required": ["team", "round"],
    },
})


def _get_pick_popularity(ctx: AnalysisContext, team: str, round: int) -> dict:
    round_num = round
    pop = pick_popularity(ctx.entries, ctx.tournament)
    total = len(ctx.entries)

    # Find all slots for this round where the team is picked
    pickers = []
    for slot_id in ctx.tournament.slot_order:
        slot = ctx.tournament.slots.get(slot_id)
        if slot is None or slot.round != round_num:
            continue
        counter = pop.get(slot_id, {})
        count = counter.get(team, 0)
        if count > 0:
            # List pickers for this slot
            for entry in ctx.entries:
                if entry.picks.get(slot_id) == team:
                    pickers.append(entry.player_name)

    pickers = list(dict.fromkeys(pickers))
    pct = len(pickers) / total * 100 if total > 0 else 0.0

    return {
        "team": team,
        "round": round_num,
        "round_name": ROUND_NAMES.get(round_num, f"Round {round_num}"),
        "pickers": pickers,
        "pct_of_pool": _round(pct, 1),
        "total_entries": total,
    }


ADAPTERS["get_pick_popularity"] = _get_pick_popularity


# ---------------------------------------------------------------------------
# Tool 15: list_players
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "list_players",
    "description": "List all player names in the pool.",
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
})


def _list_players(ctx: AnalysisContext) -> dict:
    return {"players": ctx.player_names()}


ADAPTERS["list_players"] = _list_players


# ---------------------------------------------------------------------------
# Tool 16: list_remaining_games
# ---------------------------------------------------------------------------

TOOLS.append({
    "name": "list_remaining_games",
    "description": (
        "List all games that have not yet been played. "
        "Shows slot ID, round, region, and participants (TBD if not yet determined)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
        "required": [],
    },
})


def _list_remaining_games(ctx: AnalysisContext) -> list[dict]:
    games = get_remaining_games(ctx.tournament, ctx.results)
    result = []
    for g in games:
        result.append({
            "slot_id": g["slot_id"],
            "round": g["round"],
            "round_name": ROUND_NAMES.get(g["round"], f"Round {g['round']}"),
            "region": g["region"],
            "team_a": g["team_a"] if g["team_a"] is not None else "TBD",
            "team_b": g["team_b"] if g["team_b"] is not None else "TBD",
        })
    return result


ADAPTERS["list_remaining_games"] = _list_remaining_games
