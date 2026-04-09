"""Threats plugin — who you need to watch and why.

Classifies every other bracket as a threat type, shows pairwise win probabilities,
similarity map, and bracket-by-bracket intelligence.

Presentation only. Business logic lives in core/metrics.py and core/scenarios.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.metrics import classify_threats
from core.narrative import describe_threat_type, ordinal
from core.scenarios import run_scenarios

TITLE = "Threats"
DESCRIPTION = "Who you need to beat and how likely you are to do it"
CATEGORY = "scenarios"
ORDER = 15
ICON = "\U0001f6a8"  # rotating light


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if len(ctx.entries) < 2:
        st.info("Need at least 2 players to analyze threats.")
        return

    names = ctx.player_names()
    player = st.selectbox("Analyze threats to:", names, key="threats_player")

    if not player:
        return

    with st.spinner("Running scenario analysis..."):
        sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)

    threats = classify_threats(
        player,
        ctx.entries,
        ctx.scored_entries,
        sr,
        ctx.tournament,
        ctx.results,
    )

    if not threats:
        st.info("No other players to analyze.")
        return

    user_win_pct = sr.win_counts.get(player, 0) / sr.total_scenarios if sr.total_scenarios > 0 else 0

    # --- Headline ---
    rank_row = ctx.leaderboard[ctx.leaderboard["Player"] == player]
    rank = int(rank_row["Rank"].iloc[0]) if not rank_row.empty else None
    rank_str = ordinal(rank) if rank else "unranked"

    top_threat = threats[0]
    st.markdown(
        f"**{player}** is {rank_str} with **{user_win_pct:.1%}** pool-win equity. "
        f"Biggest threat: **{top_threat.other_player}** ({top_threat.threat_type}) "
        f"— {top_threat.p_beats_user:.1%} chance of finishing ahead of you."
    )

    st.divider()

    # --- Threat table ---
    _render_threat_table(ctx, sr, threats, player)

    st.divider()

    # --- Threat detail cards ---
    _render_threat_details(ctx, sr, threats, player)

    st.divider()

    # --- Similarity map ---
    _render_similarity_map(ctx, threats, player)


def _render_threat_table(ctx, sr, threats, player):
    st.subheader("Threat Rankings")

    rows = []
    for t in threats:
        gap_str = f"+{t.score_gap}" if t.score_gap > 0 else str(t.score_gap)
        rows.append({
            "Player": t.other_player,
            "Type": t.threat_type,
            "Score Gap": gap_str,
            "Live Overlap": f"{t.overlap_pct:.0%}",
            "Their Separation": f"{t.separation:.0%}",
            "They Beat You": f"{t.p_beats_user:.1%}",
            "Threat Level": t.threat_level,
        })

    df = pd.DataFrame(rows)
    st.dataframe(
        df[["Player", "Type", "Score Gap", "Live Overlap", "Their Separation", "They Beat You"]],
        use_container_width=True,
        hide_index=True,
    )


def _render_threat_details(ctx, sr, threats, player):
    st.subheader("Threat Intelligence")

    for t in threats[:5]:  # show top 5 threats in detail
        other_scored = ctx.get_scored(t.other_player)
        other_win_pct = sr.win_counts.get(t.other_player, 0) / sr.total_scenarios if sr.total_scenarios > 0 else 0

        description = describe_threat_type(
            t.threat_type,
            t.other_player,
            t.score_gap,
            t.overlap_pct,
            t.separation,
        )

        with st.expander(f"{t.threat_type}: **{t.other_player}** — {t.p_beats_user:.1%} chance they beat you"):
            col1, col2, col3 = st.columns(3)
            with col1:
                gap_str = f"+{t.score_gap}" if t.score_gap > 0 else str(t.score_gap)
                st.metric("Score gap vs you", gap_str)
            with col2:
                st.metric("Their win equity", f"{other_win_pct:.1%}")
            with col3:
                st.metric("Live pick overlap", f"{t.overlap_pct:.0%}")

            st.markdown(description)

            # Their max possible
            if other_scored:
                remaining = other_scored.max_possible - other_scored.total_points
                st.caption(
                    f"{t.other_player} has {remaining} points of remaining upside "
                    f"(max possible: {other_scored.max_possible})"
                )


def _render_similarity_map(ctx, threats, player):
    st.subheader("How Similar Is Each Bracket to Yours?")
    st.caption("High overlap = your fates are correlated. Low overlap = they can run independently.")

    rows = []
    for t in threats:
        rows.append({
            "Player": t.other_player,
            "Live Pick Overlap": t.overlap_pct,
            "Their Separation": t.separation,
        })

    if not rows:
        return

    df = pd.DataFrame(rows).set_index("Player")
    st.bar_chart(df["Live Pick Overlap"])


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # Player-specific — no single pool summary
