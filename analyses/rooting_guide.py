"""Rooting Guide plugin — plain-English game-by-game guidance.

Tells you what to root for tonight, what to fear, and what doesn't matter.
Labels every remaining game outcome as fatal/survival/separation/shared/blocking.

Presentation only. Business logic lives in core/metrics.py and core/scenarios.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.metrics import OutcomeLabel, label_outcomes
from core.narrative import describe_outcome_label
from core.scenarios import run_scenarios
from core.scoring import ROUND_NAMES
from core.tournament import get_remaining_games

TITLE = "Rooting Guide"
DESCRIPTION = "What to root for, what to fear, and what doesn't matter"
CATEGORY = "scenarios"
ORDER = 20
ICON = "\U0001f4fb"  # radio (following the game)


_LABEL_ICONS = {
    OutcomeLabel.FATAL: ":red[\u274c]",
    OutcomeLabel.SURVIVAL: ":blue[\u2665]",
    OutcomeLabel.SEPARATION: ":green[\u2b06]",
    OutcomeLabel.SHARED_NEUTRAL: ":gray[\u2014]",
    OutcomeLabel.BLOCKING: ":orange[\u26a0\ufe0f]",
}

_LABEL_HEADERS = {
    OutcomeLabel.FATAL: "Fear these — fatal outcomes",
    OutcomeLabel.SEPARATION: "Root for these — separation opportunities",
    OutcomeLabel.SURVIVAL: "Need these — survival outcomes",
    OutcomeLabel.BLOCKING: "Watch out — boosts your rivals",
    OutcomeLabel.SHARED_NEUTRAL: "Doesn't matter much — shared outcomes",
}


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    if ctx.games_remaining() == 0:
        st.success("Tournament is complete!")
        return

    names = ctx.player_names()
    player = st.selectbox("Build guide for:", names, key="rooting_guide_player")

    if not player:
        return

    with st.spinner("Calculating..."):
        sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)

    effects = label_outcomes(player, sr, ctx.entries)

    if not effects:
        st.info("No critical game data available.")
        return

    # --- Headline narrative ---
    remaining_games = get_remaining_games(ctx.tournament, ctx.results)
    _render_headline(ctx, sr, player, effects)

    st.divider()

    # --- Tonight's games (all remaining games, labeled) ---
    _render_game_guide(ctx, sr, player, effects, remaining_games)

    st.divider()

    # --- Summary table ---
    _render_summary_table(ctx, effects)


def _render_headline(ctx, sr, player, effects):
    fatal = [e for e in effects if e.label == OutcomeLabel.FATAL]

    best = max(effects, key=lambda e: e.win_equity_delta, default=None)
    worst = min(effects, key=lambda e: e.win_equity_delta, default=None)

    lines = []
    if best and best.win_equity_delta > 0.01:
        best_team = ctx.team_name(best.team)
        lines.append(f"Best case: **{best_team} wins** ({best.win_equity_delta:+.1%} win equity)")

    if worst and worst.win_equity_delta < -0.01:
        worst_team = ctx.team_name(worst.team)
        lines.append(f"Worst case: **{worst_team} wins** ({worst.win_equity_delta:+.1%} win equity)")

    if fatal:
        fatal_teams = [ctx.team_name(e.team) for e in fatal[:2]]
        lines.append(f"Fatal outcomes: {', '.join(fatal_teams)} winning would end your run")

    if lines:
        st.info("\n\n".join(lines))


def _render_game_guide(ctx, sr, player, effects, remaining_games):
    st.subheader("Tonight's Games")

    # Build slot → (team_a name, team_b name) map from remaining games
    game_info: dict[str, dict] = {}
    for g in remaining_games:
        if g["team_a"] and g["team_b"]:
            game_info[g["slot_id"]] = g

    # Group effects by slot_id
    by_slot: dict[str, list] = {}
    for e in effects:
        by_slot.setdefault(e.slot_id, []).append(e)

    # Show slots that have known participants first
    ordered_slots = list(game_info.keys()) + [
        s for s in by_slot.keys() if s not in game_info
    ]

    for slot_id in ordered_slots:
        slot_effects = by_slot.get(slot_id)
        if not slot_effects:
            continue

        slot = ctx.tournament.slots.get(slot_id)
        round_name = ROUND_NAMES.get(slot.round, "") if slot else ""

        # Get participant names
        g = game_info.get(slot_id)
        if g:
            team_a_name = ctx.team_name(g["team_a"])
            team_b_name = ctx.team_name(g["team_b"])
            matchup_str = f"**{team_a_name} vs {team_b_name}** — {round_name}"
        else:
            matchup_str = f"**{slot_id}** — {round_name}"

        with st.container():
            st.markdown(matchup_str)
            for e in sorted(slot_effects, key=lambda x: -x.win_equity_delta):
                icon = _LABEL_ICONS.get(e.label, "")
                team_name = ctx.team_name(e.team)
                delta_str = f"{e.win_equity_delta:+.1%}" if abs(e.win_equity_delta) >= 0.005 else "~0%"
                label_desc = describe_outcome_label(e.label)
                st.markdown(
                    f"{icon} **{team_name} wins** → {label_desc} ({delta_str})"
                )
            st.markdown("")  # spacer


def _render_summary_table(ctx, effects):
    st.subheader("All Outcomes — By Impact")

    rows = []
    for e in sorted(effects, key=lambda x: -x.win_equity_delta):
        slot = ctx.tournament.slots.get(e.slot_id)
        round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
        rows.append({
            "If this team wins": ctx.team_name(e.team),
            "vs": ctx.team_name(e.opponent),
            "Round": round_name,
            "Label": e.label.value,
            "Win Equity Change": e.win_equity_delta,
            "Note": e.note,
        })

    if not rows:
        return

    df = pd.DataFrame(rows)
    df["Win Equity Change"] = df["Win Equity Change"].apply(
        lambda x: f"{x:+.1%}" if abs(x) >= 0.005 else "~0%"
    )

    st.dataframe(df, use_container_width=True, hide_index=True)


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # Player-specific — no single pool summary
