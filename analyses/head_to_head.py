"""Head to Head plugin — compare any two brackets side by side."""

from __future__ import annotations

import streamlit as st

from core.context import AnalysisContext
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES

TITLE = "Head to Head"
DESCRIPTION = "Compare any two brackets side by side"
CATEGORY = "matchups"
ORDER = 10
ICON = "\u2694\ufe0f"  # crossed swords


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    names = ctx.player_names()
    if len(names) < 2:
        st.info("Need at least 2 players for head-to-head comparison.")
        return

    col1, col2 = st.columns(2)
    with col1:
        player_a = st.selectbox("Player A", names, index=0, key="h2h_player_a")
    with col2:
        default_b = 1 if len(names) > 1 else 0
        player_b = st.selectbox("Player B", names, index=default_b, key="h2h_player_b")

    if player_a == player_b:
        st.warning("Select two different players to compare.")
        return

    entry_a = ctx.get_entry(player_a)
    entry_b = ctx.get_entry(player_b)
    scored_a = ctx.get_scored(player_a)
    scored_b = ctx.get_scored(player_b)

    if not all([entry_a, entry_b, scored_a, scored_b]):
        st.error("Could not load bracket data for selected players.")
        return

    # Compute comparison stats
    agree, disagree_a_right, disagree_b_right, disagree_pending = [], [], [], []

    for slot_id in ctx.tournament.slot_order:
        pick_a = entry_a.picks.get(slot_id)
        pick_b = entry_b.picks.get(slot_id)

        if pick_a == pick_b:
            agree.append(slot_id)
        elif ctx.results.is_complete(slot_id):
            winner = ctx.results.winner_of(slot_id)
            if pick_a == winner:
                disagree_a_right.append(slot_id)
            elif pick_b == winner:
                disagree_b_right.append(slot_id)
        else:
            disagree_pending.append(slot_id)

    total_slots = len(ctx.tournament.slot_order)
    total_disagree = len(disagree_a_right) + len(disagree_b_right) + len(disagree_pending)

    # --- Narrative summary ---
    pending_pts = sum(
        POINTS_PER_ROUND.get(ctx.tournament.slots[s].round, 0)
        for s in disagree_pending
    )

    st.markdown(
        f"**{player_a}** and **{player_b}** agree on "
        f"**{len(agree)} of {total_slots}** picks. "
        f"They differ on **{total_disagree}** games"
        + (f" \u2014 the {len(disagree_pending)} unresolved differences "
           f"are worth up to **{pending_pts} pts**. "
           f"That's where this race gets decided."
           if disagree_pending else ".")
    )

    # --- Score comparison ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(player_a, f"{scored_a.total_points} pts")
    with col2:
        diff = scored_a.total_points - scored_b.total_points
        label = f"{player_a} +{diff}" if diff > 0 else (f"{player_b} +{-diff}" if diff < 0 else "Tied")
        st.metric("Difference", label)
    with col3:
        st.metric(player_b, f"{scored_b.total_points} pts")

    # --- Agreement / Disagreement breakdown ---
    st.subheader("Where They Differ")

    if disagree_a_right or disagree_b_right:
        st.markdown("**Resolved (one was right):**")
        for slot_id in disagree_a_right:
            slot = ctx.tournament.slots[slot_id]
            pts = POINTS_PER_ROUND.get(slot.round, 0)
            pick_a_name = ctx.team_name(entry_a.picks[slot_id])
            pick_b_name = ctx.team_name(entry_b.picks[slot_id])
            st.markdown(
                f":green[**{player_a}**] picked {pick_a_name} \u2705 vs "
                f":red[**{player_b}**] picked {pick_b_name} \u274c "
                f"\u2014 {ROUND_NAMES.get(slot.round, '')} (+{pts} pts to {player_a})"
            )
        for slot_id in disagree_b_right:
            slot = ctx.tournament.slots[slot_id]
            pts = POINTS_PER_ROUND.get(slot.round, 0)
            pick_a_name = ctx.team_name(entry_a.picks[slot_id])
            pick_b_name = ctx.team_name(entry_b.picks[slot_id])
            st.markdown(
                f":red[**{player_a}**] picked {pick_a_name} \u274c vs "
                f":green[**{player_b}**] picked {pick_b_name} \u2705 "
                f"\u2014 {ROUND_NAMES.get(slot.round, '')} (+{pts} pts to {player_b})"
            )

    if disagree_pending:
        st.markdown("**Still unresolved (swing games):**")
        for slot_id in disagree_pending:
            slot = ctx.tournament.slots[slot_id]
            pts = POINTS_PER_ROUND.get(slot.round, 0)
            pick_a_name = ctx.team_name(entry_a.picks[slot_id])
            pick_b_name = ctx.team_name(entry_b.picks[slot_id])
            a_alive = ctx.is_alive(entry_a.picks[slot_id])
            b_alive = ctx.is_alive(entry_b.picks[slot_id])
            a_status = "\U0001f7e2" if a_alive else "\U0001f534"
            b_status = "\U0001f7e2" if b_alive else "\U0001f534"
            st.markdown(
                f"{a_status} **{player_a}**: {pick_a_name} vs "
                f"{b_status} **{player_b}**: {pick_b_name} "
                f"\u2014 {ROUND_NAMES.get(slot.round, '')} ({pts} pts at stake)"
            )

    # --- Agreement list (expandable) ---
    with st.expander(f"Games they agree on ({len(agree)})"):
        for slot_id in agree:
            slot = ctx.tournament.slots[slot_id]
            pick_name = ctx.team_name(entry_a.picks[slot_id])
            result_icon = ""
            if ctx.results.is_complete(slot_id):
                if ctx.results.winner_of(slot_id) == entry_a.picks[slot_id]:
                    result_icon = "\u2705"
                else:
                    result_icon = "\u274c"
            else:
                result_icon = "\u23f3"
            st.markdown(
                f"{result_icon} {pick_name} \u2014 {ROUND_NAMES.get(slot.round, '')}"
            )


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # H2H is player-specific, no single summary
