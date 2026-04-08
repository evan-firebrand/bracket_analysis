"""Head to Head plugin — compare any two brackets side by side.

Extended with:
- H2H win equity from scenario engine
- Indirect relevance annotations (shared games that gate divergence)
- Hinge game identification

Presentation only. Business logic lives in core/comparison.py and core/scenarios.py.
"""

from __future__ import annotations

import streamlit as st

from core.comparison import head_to_head
from core.context import AnalysisContext
from core.metrics import pairwise_beat_probability
from core.scenarios import run_scenarios
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES
from core.tournament import get_remaining_slots

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

    # --- Score comparison ---
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(player_a, f"{scored_a.total_points} pts")
    with col2:
        diff = scored_a.total_points - scored_b.total_points
        label = (
            f"{player_a} +{diff}" if diff > 0
            else (f"{player_b} +{-diff}" if diff < 0 else "Tied")
        )
        st.metric("Difference", label)
    with col3:
        st.metric(player_b, f"{scored_b.total_points} pts")

    # --- H2H win equity (scenario-based) ---
    _render_h2h_equity(ctx, player_a, player_b, scored_a, scored_b)

    # --- Narrative summary ---
    total_slots = len(ctx.tournament.slot_order)
    st.markdown(
        f"**{player_a}** and **{player_b}** agree on "
        f"**{len(h2h.agree)} of {total_slots}** picks. "
        f"They differ on **{h2h.total_disagree}** games"
        + (
            f" \u2014 the {len(h2h.disagree_pending)} unresolved differences "
            f"are worth up to **{h2h.pending_points} pts**. "
            f"That's where this race gets decided."
            if h2h.disagree_pending
            else "."
        )
    )

    # --- Where they differ ---
    st.subheader("Where They Differ")
    _render_resolved_diffs(ctx, entry_a, entry_b, h2h, player_a, player_b)
    _render_pending_diffs(ctx, entry_a, entry_b, h2h, player_a, player_b)

    # --- Indirect relevance: shared games that still matter ---
    _render_indirect_relevance(ctx, entry_a, entry_b, h2h, player_a, player_b)

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


def _render_h2h_equity(ctx, player_a, player_b, scored_a, scored_b):
    """Show who leads this head-to-head based on remaining scenarios."""
    if ctx.games_remaining() == 0:
        return

    with st.spinner("Computing H2H equity..."):
        sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)

    p_a_beats_b = pairwise_beat_probability(sr, player_a, player_b)
    p_b_beats_a = 1.0 - p_a_beats_b

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(f"{player_a} wins the H2H", f"{p_a_beats_b:.1%}")
    with col2:
        engine_label = "exact" if sr.engine == "brute_force" else f"{sr.total_scenarios:,} sim."
        lead_name = player_a if p_a_beats_b >= 0.5 else player_b
        lead_pct = max(p_a_beats_b, p_b_beats_a)
        st.metric("H2H Leader", f"{lead_name} ({lead_pct:.0%})")
        st.caption(f"Based on {engine_label} scenarios")
    with col3:
        st.metric(f"{player_b} wins the H2H", f"{p_b_beats_a:.1%}")

    # Narrative
    if abs(p_a_beats_b - 0.5) < 0.05:
        st.info("This H2H is nearly a toss-up — either player can come out ahead.")
    elif p_a_beats_b > 0.5:
        gap = scored_a.total_points - scored_b.total_points
        if gap > 0:
            st.success(
                f"**{player_a}** leads by {gap} pts and wins this matchup in "
                f"{p_a_beats_b:.0%} of remaining scenarios."
            )
        else:
            st.info(
                f"**{player_a}** trails on points but has better remaining picks — "
                f"wins this H2H in {p_a_beats_b:.0%} of scenarios."
            )
    else:
        st.warning(
            f"**{player_b}** is favored in this H2H at {p_b_beats_a:.0%} of scenarios."
        )


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


def _render_indirect_relevance(ctx, entry_a, entry_b, h2h, player_a, player_b):
    """Identify shared-pick games that still matter because they gate divergence points.

    A shared game has indirect relevance if it feeds into a slot where the two
    players diverge — meaning the shared game must resolve for the divergence
    to even become possible.
    """
    remaining = set(get_remaining_slots(ctx.tournament, ctx.results))

    # Find divergence slots that are still live
    live_divergence = set(h2h.disagree_pending)

    # For each shared pending slot, check if it feeds into a live divergence slot
    # by tracing the feeds_into chain
    indirectly_relevant = []

    for slot_id in h2h.agree:
        if slot_id not in remaining:
            continue  # already resolved

        # Walk the feeds_into chain from this slot
        current = ctx.tournament.slots[slot_id].feeds_into
        while current:
            if current in live_divergence:
                # This shared game gates a divergence point
                pick = entry_a.picks.get(slot_id)
                div_slot = ctx.tournament.slots[current]
                pick_a_at_div = entry_a.picks.get(current)
                pick_b_at_div = entry_b.picks.get(current)
                indirectly_relevant.append({
                    "slot_id": slot_id,
                    "pick": pick,
                    "gates_slot_id": current,
                    "gates_round": div_slot.round,
                    "div_pick_a": pick_a_at_div,
                    "div_pick_b": pick_b_at_div,
                })
                break
            current = ctx.tournament.slots[current].feeds_into if current in ctx.tournament.slots else None

    if not indirectly_relevant:
        return

    with st.expander(
        f"Shared games that still matter ({len(indirectly_relevant)}) — indirect relevance"
    ):
        st.caption(
            "These games have the same pick from both players, but they matter because "
            "they control access to a later slot where the brackets diverge."
        )
        for item in indirectly_relevant:
            slot = ctx.tournament.slots[item["slot_id"]]
            gate_round_name = ROUND_NAMES.get(item["gates_round"], "")
            pick_name = ctx.team_name(item["pick"]) if item["pick"] else "?"
            div_a = ctx.team_name(item["div_pick_a"]) if item["div_pick_a"] else "?"
            div_b = ctx.team_name(item["div_pick_b"]) if item["div_pick_b"] else "?"
            st.markdown(
                f"\u23f3 **{pick_name}** must advance ({ROUND_NAMES.get(slot.round, '')}) "
                f"to decide the {gate_round_name} split: "
                f"{player_a} \u2192 {div_a} vs {player_b} \u2192 {div_b}"
            )


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # H2H is player-specific, no single summary
