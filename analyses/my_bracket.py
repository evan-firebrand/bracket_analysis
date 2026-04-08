"""My Bracket plugin — personal bracket viewer with color coding."""

from __future__ import annotations

import streamlit as st

from core.context import AnalysisContext
from core.narrative import describe_max_possible, ordinal
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES

TITLE = "My Bracket"
DESCRIPTION = "See how your bracket is doing"
CATEGORY = "my_bracket"
ORDER = 10
ICON = "\U0001f4cb"  # clipboard


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    # Player selector
    player = st.selectbox(
        "Select a player",
        ctx.player_names(),
        key="my_bracket_player",
    )

    if not player:
        return

    entry = ctx.get_entry(player)
    scored = ctx.get_scored(player)
    if not entry or not scored:
        st.error(f"No bracket found for {player}")
        return

    # --- Headline ---
    ai_summary = ctx.generate_copy("player_summary", "my_bracket", viewer=player)
    if ai_summary is None:
        ai_summary = ctx.get_ai_player_summary(player)  # fall back to static
    if ai_summary:
        st.markdown(f"*{ai_summary}*")
    else:
        rank_row = ctx.leaderboard[ctx.leaderboard["Player"] == player]
        if len(rank_row) > 0:
            rank = int(rank_row["Rank"].iloc[0])
            st.markdown(
                f"**{player}** is in **{ordinal(rank)} place** with "
                f"**{scored.total_points} pts**. "
                f"{describe_max_possible(scored.total_points, scored.max_possible)}"
            )

    # --- Summary metrics ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Points", scored.total_points)
    with col2:
        st.metric("Max Possible", scored.max_possible)
    with col3:
        st.metric("Correct Picks", len(scored.correct_picks))
    with col4:
        st.metric("Pending", len(scored.pending_picks))

    # --- Region-by-region bracket view ---
    regions = sorted(set(
        slot.region for slot in ctx.tournament.slots.values()
        if slot.region not in ("Final Four",)
    ))

    # Add Final Four tab if applicable
    tabs = regions + ["Final Four"]
    tab_objects = st.tabs(tabs)

    for tab, region_name in zip(tab_objects, tabs):
        with tab:
            _render_region(ctx, entry, scored, region_name)


def _render_region(
    ctx: AnalysisContext,
    entry,
    scored,
    region_name: str,
):
    """Render a single region's bracket picks."""
    # Get slots for this region, grouped by round
    region_slots = [
        slot for slot in ctx.tournament.slots.values()
        if slot.region == region_name
    ]
    if not region_slots:
        st.info(f"No games in {region_name}")
        return

    rounds_in_region = sorted(set(s.round for s in region_slots))

    for round_num in rounds_in_region:
        round_slots = sorted(
            [s for s in region_slots if s.round == round_num],
            key=lambda s: s.position,
        )

        st.markdown(f"**{ROUND_NAMES.get(round_num, f'Round {round_num}')}** "
                     f"({POINTS_PER_ROUND.get(round_num, 0)} pts each)")

        for slot in round_slots:
            pick = entry.picks.get(slot.slot_id)
            if not pick:
                continue

            pick_name = ctx.team_name(pick)
            seed = ctx.team_seed(pick)
            seed_str = f"({seed}) " if seed else ""
            points_value = POINTS_PER_ROUND.get(slot.round, 0)

            if slot.slot_id in scored.correct_picks:
                # Correct pick — green
                st.markdown(
                    f":green[**\u2705 {seed_str}{pick_name}** +{points_value} pts]"
                )
            elif slot.slot_id in scored.incorrect_picks:
                # Wrong pick — red
                actual_winner = ctx.results.winner_of(slot.slot_id)
                actual_name = ctx.team_name(actual_winner) if actual_winner else "?"
                st.markdown(
                    f":red[**\u274c {seed_str}{pick_name}** — "
                    f"lost to {actual_name}]"
                )
            else:
                # Pending — check if team is still alive
                if ctx.is_alive(pick):
                    st.markdown(
                        f":gray[**\u23f3 {seed_str}{pick_name}** — "
                        f"still alive ({points_value} pts)]"
                    )
                else:
                    st.markdown(
                        f":orange[**\U0001f4a8 {seed_str}{pick_name}** — "
                        f"eliminated (lost {points_value} pts)]"
                    )

        st.divider()


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # Per-player, no single summary
