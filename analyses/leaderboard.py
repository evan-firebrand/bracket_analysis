"""Leaderboard plugin — current standings, scores, round breakdown."""

from __future__ import annotations

import streamlit as st

from core.context import AnalysisContext
from core.narrative import describe_elimination, describe_max_possible, ordinal
from core.scoring import ROUND_NAMES

TITLE = "The Standings"
DESCRIPTION = "Who's winning, scores, and round breakdown"
CATEGORY = "standings"
ORDER = 10
ICON = "\U0001f3c6"  # trophy


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    # --- Headline narrative ---
    viewer = st.session_state.get("viewing_player")
    headline = ctx.generate_copy("headline", "leaderboard", viewer=viewer)
    if headline is None:
        headline = ctx.get_ai_headline()  # fall back to static approved.json
    if headline:
        st.markdown(f"*{headline}*")
    elif len(ctx.leaderboard) > 0:
        leader = ctx.leaderboard.iloc[0]
        if len(ctx.leaderboard) > 1:
            runner_up = ctx.leaderboard.iloc[1]
            gap = leader["Total"] - runner_up["Total"]
            st.markdown(
                f"**{leader['Player']}** leads with **{leader['Total']} pts**. "
                f"**{runner_up['Player']}** trails by {gap}. "
                f"{ctx.games_remaining()} games remaining."
            )
        else:
            st.markdown(f"**{leader['Player']}** leads with **{leader['Total']} pts**.")

    # --- Tournament status bar ---
    total_games = len(ctx.tournament.slots)
    completed = ctx.results.completed_count()
    if total_games > 0:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Games Played", f"{completed}/{total_games}")
        with col2:
            current = ctx.current_round()
            st.metric("Current Round", ctx.round_name(current) if current > 0 else "Not Started")
        with col3:
            alive_count = sum(
                1 for s in ctx.scored_entries.values()
                if s.max_possible >= (ctx.leaderboard.iloc[0]["Total"] if len(ctx.leaderboard) > 0 else 0)
            )
            st.metric("Still In Contention", f"{alive_count}/{len(ctx.entries)}")

    # --- Main leaderboard table ---
    if len(ctx.leaderboard) == 0:
        st.info("No entries loaded yet.")
        return

    # Style the dataframe
    display_cols = ["Rank", "Player", "Total", "Max Possible", "Correct"]
    # Add round columns for completed rounds only
    for rnd, name in ROUND_NAMES.items():
        if any(
            slot.round == rnd
            for slot in ctx.tournament.slots.values()
            if ctx.results.is_complete(slot.slot_id)
        ):
            display_cols.append(name)

    df_display = ctx.leaderboard[display_cols].copy()

    st.dataframe(
        df_display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Total": st.column_config.NumberColumn("Total Pts", format="%d"),
            "Max Possible": st.column_config.NumberColumn("Max Possible", format="%d"),
            "Correct": st.column_config.NumberColumn("Correct Picks", format="%d"),
        },
    )

    # --- Expandable details per player ---
    with st.expander("Player Details"):
        selected = st.selectbox(
            "Select a player",
            ctx.player_names(),
            key="leaderboard_detail_player",
        )
        if selected:
            scored = ctx.get_scored(selected)
            if scored:
                leader_score = ctx.leaderboard.iloc[0]["Total"]
                rank = int(ctx.leaderboard[ctx.leaderboard["Player"] == selected]["Rank"].iloc[0])

                st.markdown(f"### {selected} — {ordinal(rank)} place")
                st.markdown(
                    f"**{scored.total_points} pts** | "
                    f"Max Possible: **{scored.max_possible}** | "
                    f"{describe_max_possible(scored.total_points, scored.max_possible)}"
                )
                st.markdown(
                    describe_elimination(
                        scored.max_possible < leader_score,
                        scored.max_possible,
                        leader_score,
                    )
                )

                # Round-by-round breakdown
                round_data = {
                    ctx.round_name(rnd): pts
                    for rnd, pts in scored.points_by_round.items()
                    if pts > 0
                }
                if round_data:
                    st.bar_chart(round_data)


def summarize(ctx: AnalysisContext) -> str | None:
    if len(ctx.leaderboard) == 0:
        return None
    leader = ctx.leaderboard.iloc[0]
    return (
        f"{leader['Player']} leads with {leader['Total']} pts "
        f"({ctx.games_remaining()} games remaining)."
    )
