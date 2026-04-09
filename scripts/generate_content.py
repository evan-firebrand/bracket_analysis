"""Generate AI-powered bracket commentary and save to data/content/approved.json.

Usage:
    python scripts/generate_content.py [--data-dir data] [--model claude-opus-4-6] [--dry-run]

The output file schema matches what core/context.py reads:
    {
        "headline":         str,
        "stories":          [{"title": str, "body": str}, ...],
        "recap":            str,
        "player_summaries": {"player_name_lower": str, ...}
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import anthropic

from core.context import AnalysisContext
from core.narrative import describe_elimination, describe_max_possible
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES

REQUIRED_FIELDS = {"headline", "stories", "recap", "player_summaries"}


# ---------------------------------------------------------------------------
# Context assembly
# ---------------------------------------------------------------------------


def _find_champ_slot(ctx: AnalysisContext) -> str | None:
    """Return the slot_id of the championship game (feeds_into=None)."""
    for sid, slot in ctx.tournament.slots.items():
        if slot.feeds_into is None:
            return sid
    return None


def build_prompt_context(ctx: AnalysisContext) -> dict:
    """Assemble a structured summary of the current tournament state.

    Returns a plain dict so it can be serialised, logged, and inspected
    independently of the prompt string.
    """
    completed = ctx.results.completed_count()
    total = len(ctx.tournament.slots)
    current_round = ctx.current_round()
    champ_slot = _find_champ_slot(ctx)

    # --- leaderboard rows ---
    leaderboard_rows = []
    for _, row in ctx.leaderboard.iterrows():
        name = row["Player"]
        scored = ctx.scored_entries.get(name)
        champ_pick = None
        champ_alive = False
        if champ_slot and scored:
            champ_pick_slug = scored.pending_picks and ctx.get_entry(name) and ctx.get_entry(name).picks.get(champ_slot)
            if champ_pick_slug is None and ctx.get_entry(name):
                champ_pick_slug = ctx.get_entry(name).picks.get(champ_slot)
            if champ_pick_slug:
                team = ctx.tournament.teams.get(champ_pick_slug)
                champ_pick = team.name if team else champ_pick_slug
                champ_alive = champ_pick_slug in ctx.alive_teams

        # per-round correct pick counts
        round_hits: dict[str, int] = {}
        if scored:
            for rnd, pts in scored.points_by_round.items():
                ppg = POINTS_PER_ROUND.get(rnd, 0)
                round_hits[ROUND_NAMES.get(rnd, f"Round {rnd}")] = (
                    pts // ppg if ppg else 0
                )

        # elimination status
        leader_total = int(ctx.leaderboard.iloc[0]["Total"]) if len(ctx.leaderboard) else 0
        max_poss = int(row["Max Possible"])
        elim_desc = describe_elimination(
            is_eliminated=(max_poss < leader_total),
            max_possible=max_poss,
            leader_score=leader_total,
        )
        upside_desc = describe_max_possible(int(row["Total"]), max_poss)

        leaderboard_rows.append({
            "rank": int(row["Rank"]),
            "player": name,
            "total": int(row["Total"]),
            "max_possible": max_poss,
            "correct": int(row["Correct"]),
            "champion_pick": champ_pick,
            "champion_alive": champ_alive,
            "round_hits": round_hits,
            "status": elim_desc,
            "upside": upside_desc,
        })

    # --- notable upsets ---
    upsets = []
    for slot_id, result in ctx.results.results.items():
        winner_team = ctx.tournament.teams.get(result.winner)
        loser_team = ctx.tournament.teams.get(result.loser)
        if winner_team and loser_team:
            seed_diff = loser_team.seed - winner_team.seed
            if seed_diff >= 4:  # meaningful upset
                upsets.append({
                    "slot": slot_id,
                    "winner": winner_team.name,
                    "winner_seed": winner_team.seed,
                    "loser": loser_team.name,
                    "loser_seed": loser_team.seed,
                    "score": result.score,
                })

    return {
        "year": ctx.tournament.year,
        "current_round": current_round,
        "current_round_name": ctx.round_name(current_round) if current_round > 0 else "Pre-Tournament",
        "games_completed": completed,
        "games_remaining": total - completed,
        "leaderboard": leaderboard_rows,
        "upsets": upsets,
        "alive_teams": sorted(ctx.alive_teams),
    }


# ---------------------------------------------------------------------------
# Prompt building
# ---------------------------------------------------------------------------


def _player_summary_schema(keys: list[str], names: list[str]) -> str:
    """Build the player_summaries section of the JSON schema hint."""
    lines = []
    for k, n in zip(keys, names):
        lines.append(f'    "{k}": "<one punchy sentence about {n}\'s bracket position>",')
    return "\n".join(lines)


def build_prompt(ctx_summary: dict) -> str:
    """Build the Claude prompt from the structured context summary."""
    year = ctx_summary["year"]
    rnd_name = ctx_summary["current_round_name"]
    completed = ctx_summary["games_completed"]
    remaining = ctx_summary["games_remaining"]
    players = ctx_summary["leaderboard"]
    upsets = ctx_summary["upsets"]
    alive = ctx_summary["alive_teams"]

    # Build leaderboard block
    board_lines = []
    for p in players:
        champ_info = ""
        if p.get("champion_pick"):
            alive_str = "ALIVE" if p["champion_alive"] else "ELIMINATED"
            champ_info = f", champion pick: {p['champion_pick']} ({alive_str})"
        board_lines.append(
            f"  #{p['rank']} {p['player']}: {p['total']} pts "
            f"(max possible {p['max_possible']}, {p['correct']} correct){champ_info}"
        )
    board_text = "\n".join(board_lines) if board_lines else "  (no entries)"

    # Build upsets block
    if upsets:
        upset_lines = [
            f"  • #{u['winner_seed']} {u['winner']} over #{u['loser_seed']} {u['loser']}"
            + (f" ({u['score']})" if u.get("score") else "")
            for u in upsets
        ]
        upset_text = "\n".join(upset_lines)
    else:
        upset_text = "  (no notable upsets yet)"

    # Build player names list for summaries
    player_names = [p["player"] for p in players]
    player_keys = [p["player"].lower() for p in players]

    prompt = f"""You are writing content for a private NCAA bracket pool dashboard shared among friends.
Tone: casual but sharp, like a friend who watches too much sports. No filler; every sentence earns its place.

## Tournament Context — {year} NCAA Tournament

Current stage: {rnd_name}
Games completed: {completed} | Games remaining: {remaining}

### Standings
{board_text}

### Notable Upsets
{upset_text}

### Teams Still Alive
{', '.join(alive) if alive else '(none)'}

---

## Your Task

Respond with **only** valid JSON — no markdown, no preamble, no explanation.
Match this exact schema:

{{
  "headline": "<one punchy sentence that captures the current drama, max 20 words>",
  "stories": [
    {{"title": "<short story title>", "body": "<2-3 sentences of narrative>"}},
    {{"title": "<short story title>", "body": "<2-3 sentences of narrative>"}},
    {{"title": "<short story title>", "body": "<2-3 sentences of narrative>"}}
  ],
  "recap": "<4-6 sentences you could paste into a group chat — casual, specific, funny if warranted>",
  "player_summaries": {{
    {_player_summary_schema(player_keys, player_names)}
  }}
}}

Rules:
- Use actual player names, team names, and scores from the context above
- stories: write exactly 3 story cards; each body is 2-3 sentences, no more
- recap: 4-6 sentences max; written as if texting the group — name names, cite scores
- player_summaries: one key per player (lowercase name), one sentence each
- No generic sports clichés ("bracket madness", "the Big Dance") unless you're being ironic
- If someone's champion pick is eliminated, mention it (once, brutally)
"""
    return prompt


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


def validate_schema(data: dict) -> None:
    """Validate the generated content matches the approved.json schema.

    Raises ValueError with a descriptive message on any violation.
    """
    missing = REQUIRED_FIELDS - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields: {missing}")

    if not isinstance(data["headline"], str) or not data["headline"].strip():
        raise ValueError("'headline' must be a non-empty string")

    stories = data["stories"]
    if not isinstance(stories, list) or len(stories) == 0:
        raise ValueError("'stories' must be a non-empty list")
    for i, story in enumerate(stories):
        if not isinstance(story, dict):
            raise ValueError(f"stories[{i}] must be a dict")
        if "title" not in story:
            raise ValueError(f"stories[{i}] missing 'title'")
        if "body" not in story:
            raise ValueError(f"stories[{i}] missing 'body'")

    if not isinstance(data["recap"], str) or not data["recap"].strip():
        raise ValueError("'recap' must be a non-empty string")

    summaries = data["player_summaries"]
    if not isinstance(summaries, dict):
        raise ValueError("'player_summaries' must be a dict")


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------


def call_claude(prompt: str, model: str) -> dict:
    """Call the Claude API and return the parsed JSON response."""
    client = anthropic.Anthropic()

    with client.messages.stream(
        model=model,
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        final = stream.get_final_message()

    text = next(
        (block.text for block in final.content if block.type == "text"),
        None,
    )
    if not text:
        raise RuntimeError("Claude returned no text content")

    # Strip potential markdown code fences
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Claude response was not valid JSON: {exc}\n\nRaw:\n{text}") from exc


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Generate AI bracket commentary and save to data/content/approved.json"
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Path to the data directory (default: data)",
    )
    parser.add_argument(
        "--model",
        default="claude-opus-4-6",
        help="Claude model ID to use (default: claude-opus-4-6)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the prompt and context summary without calling the API or writing files",
    )
    args = parser.parse_args(argv)

    try:
        ctx = AnalysisContext(data_dir=args.data_dir)
    except FileNotFoundError as exc:
        print(f"Error loading data: {exc}", file=sys.stderr)
        sys.exit(1)

    summary = build_prompt_context(ctx)
    prompt = build_prompt(summary)

    if args.dry_run:
        print("=== CONTEXT SUMMARY ===")
        print(json.dumps(summary, indent=2))
        print("\n=== PROMPT ===")
        print(prompt)
        return

    print(f"Calling {args.model}...", flush=True)
    data = call_claude(prompt, args.model)
    validate_schema(data)

    output_path = Path(args.data_dir) / "content" / "approved.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    word_count = sum(
        len(str(v).split())
        for v in [data["headline"], data["recap"]]
        + [s["body"] for s in data.get("stories", [])]
        + list(data.get("player_summaries", {}).values())
    )
    print(f"Saved to {output_path} (~{word_count} words)")


if __name__ == "__main__":
    main()
