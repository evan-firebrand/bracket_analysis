"""Head to Head plugin — compare any two brackets side by side.

Presentation only. Business logic lives in core/comparison.py.
"""

from __future__ import annotations

import streamlit as st

from core.comparison import head_to_head
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

    # Get comparison data from core
    h2h = head_to_head(entry_a, entry_b, ctx.tournament, ctx.results)

    # --- Narrative summary ---
    total_slots = len(ctx.tournament.slot_order)
    st.markdown(
        f"**{player_a}** and **{player_b}** agree on "
        f"**{len(h2h.agree)} of {total_slots}** picks. "
        f"They differ on **{h2h.total_disagree}** games"
        + (f" \u2014 the {len(h2h.disagree_pending)} unresolved differences "
           f"are worth up to **{h2h.pending_points} pts**. "
           f"That's where this race gets decided."
           if h2h.disagree_pending else ".")
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

    # --- Where they differ ---
    st.subheader("Where They Differ")

    _render_resolved_diffs(ctx, entry_a, entry_b, h2h, player_a, player_b)
    _render_pending_diffs(ctx, entry_a, entry_b, h2h, player_a, player_b)

    # --- Agreement list (expandable) ---
    with st.expander(f"Games they agree on ({len(h2h.agree)})"):
        for slot_id in h2h.agree:
            slot = ctx.tournament.slots[slot_id]
            pick_name = ctx.team_name(entry_a.picks[slot_id])
            if ctx.results.is_complete(slot_id):
                icon = "\u2705" if ctx.results.winner_of(slot_id) == entry_a.picks[slot_id] else "\u274c"
            else:
                icon = "\u23f3"
            st.markdown(f"{icon} {pick_name} \u2014 {ROUND_NAMES.get(slot.round, '')}")


def _render_resolved_diffs(ctx, entry_a, entry_b, h2h, player_a, player_b):
    """Render games where they disagreed and the result is in."""
    resolved = h2h.disagree_a_right + h2h.disagree_b_right + h2h.disagree_both_wrong
    if not resolved:
        return

    st.markdown("**Resolved:**")
    for slot_id in h2h.disagree_a_right:
        slot = ctx.tournament.slots[slot_id]
        pts = POINTS_PER_ROUND.get(slot.round, 0)
        st.markdown(
            f":green[**{player_a}**] picked {ctx.team_name(entry_a.picks[slot_id])} \u2705 vs "
            f":red[**{player_b}**] picked {ctx.team_name(entry_b.picks[slot_id])} \u274c "
            f"\u2014 {ROUND_NAMES.get(slot.round, '')} (+{pts} pts to {player_a})"
        )
    for slot_id in h2h.disagree_b_right:
        slot = ctx.tournament.slots[slot_id]
        pts = POINTS_PER_ROUND.get(slot.round, 0)
        st.markdown(
            f":red[**{player_a}**] picked {ctx.team_name(entry_a.picks[slot_id])} \u274c vs "
            f":green[**{player_b}**] picked {ctx.team_name(entry_b.picks[slot_id])} \u2705 "
            f"\u2014 {ROUND_NAMES.get(slot.round, '')} (+{pts} pts to {player_b})"
        )
    for slot_id in h2h.disagree_both_wrong:
        slot = ctx.tournament.slots[slot_id]
        winner = ctx.team_name(ctx.results.winner_of(slot_id))
        st.markdown(
            f":gray[Both wrong] \u2014 {ctx.team_name(entry_a.picks[slot_id])} / "
            f"{ctx.team_name(entry_b.picks[slot_id])} "
            f"(actual: {winner}) \u2014 {ROUND_NAMES.get(slot.round, '')}"
        )


def _render_pending_diffs(ctx, entry_a, entry_b, h2h, player_a, player_b):
    """Render games where they disagree and the result is pending."""
    if not h2h.disagree_pending:
        return

    st.markdown("**Still unresolved (swing games):**")
    for slot_id in h2h.disagree_pending:
        slot = ctx.tournament.slots[slot_id]
        pts = POINTS_PER_ROUND.get(slot.round, 0)
        pick_a = entry_a.picks[slot_id]
        pick_b = entry_b.picks[slot_id]
        a_alive = "\U0001f7e2" if ctx.is_alive(pick_a) else "\U0001f534"
        b_alive = "\U0001f7e2" if ctx.is_alive(pick_b) else "\U0001f534"
        st.markdown(
            f"{a_alive} **{player_a}**: {ctx.team_name(pick_a)} vs "
            f"{b_alive} **{player_b}**: {ctx.team_name(pick_b)} "
            f"\u2014 {ROUND_NAMES.get(slot.round, '')} ({pts} pts at stake)"
        )


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # H2H is player-specific, no single summary
