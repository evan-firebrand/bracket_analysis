"""My Position plugin — personal competitive intelligence view.

Shows a selected player's win equity, finish distribution, separation index,
must-have outcomes, and danger outcomes in one focused view.

Presentation only. Business logic lives in core/metrics.py and core/scenarios.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.metrics import (
    OutcomeLabel,
    label_outcomes,
    pairwise_beat_probability,
    separation_index,
    shared_vs_unique_upside,
)
from core.narrative import (
    describe_probability,
    describe_separation_index,
    ordinal,
)
from core.scenarios import run_scenarios
from core.scoring import ROUND_NAMES

TITLE = "My Position"
DESCRIPTION = "Win equity, separation, must-have outcomes, and danger games"
CATEGORY = "scenarios"
ORDER = 5
ICON = "\U0001f3af"  # bullseye


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    names = ctx.player_names()
    player = st.selectbox("Select player", names, key="my_position_player")

    if not player:
        return

    entry = ctx.get_entry(player)
    scored = ctx.get_scored(player)
    if not entry or not scored:
        st.error("Could not load data for this player.")
        return

    # Current rank
    rank_row = ctx.leaderboard[ctx.leaderboard["Player"] == player]
    current_rank = int(rank_row["Rank"].iloc[0]) if not rank_row.empty else None
    n_players = len(ctx.entries)

    # Run scenario engine
    with st.spinner("Calculating scenarios..."):
        sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)

    total = sr.total_scenarios

    # --- Top metrics row ---
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        rank_label = ordinal(current_rank) if current_rank else "—"
        st.metric("Current Rank", rank_label, delta=None)

    with col2:
        st.metric("Points", f"{scored.total_points}", delta=None)

    with col3:
        win_pct = sr.win_counts.get(player, 0) / total if total > 0 else 0.0
        st.metric("Win Equity", f"{win_pct:.1%}")

    with col4:
        sep = separation_index(entry, ctx.entries, ctx.tournament, ctx.results)
        st.metric("Separation Index", f"{sep:.0%}")

    # --- Narrative summary ---
    is_elim = sr.is_eliminated.get(player, False)
    st.markdown(_position_narrative(player, win_pct, sep, current_rank, n_players, is_elim))

    st.divider()

    # --- Finish distribution ---
    _render_finish_distribution(ctx, sr, player, total, n_players)

    st.divider()

    # --- Upside breakdown ---
    _render_upside_breakdown(ctx, entry, scored, sr, player, total)

    st.divider()

    # --- Must-have and danger outcomes ---
    _render_outcome_guide(ctx, sr, player, entry)

    # --- vs. the field ---
    if not is_elim:
        st.divider()
        _render_vs_field(ctx, sr, player, n_players)


def _position_narrative(
    player: str,
    win_pct: float,
    sep: float,
    rank: int | None,
    n_players: int,
    is_elim: bool,
) -> str:
    if is_elim:
        return f"**{player}** has been mathematically eliminated — no remaining scenario ends with a 1st place finish."

    rank_str = ordinal(rank) if rank else "unranked"
    win_desc = describe_probability(win_pct)
    sep_desc = describe_separation_index(sep)

    return (
        f"**{player}** sits **{rank_str}** of {n_players} and is {win_desc}. "
        f"Separation: {sep_desc}."
    )


def _render_finish_distribution(ctx, sr, player, total, n_players):
    st.subheader("Finish Distribution")

    dist = sr.finish_distributions.get(player, {})
    if not dist:
        st.info("No scenario data available.")
        return

    chart_data = {}
    table_rows = []
    for pos in range(1, n_players + 1):
        count = dist.get(pos, 0)
        pct = count / total if total > 0 else 0.0
        chart_data[ordinal(pos)] = pct
        table_rows.append({"Finish": ordinal(pos), "Probability": f"{pct:.1%}", "Scenarios": count})

    col1, col2 = st.columns([2, 1])
    with col1:
        st.bar_chart(chart_data)
    with col2:
        # Cumulative highlights
        top1 = dist.get(1, 0) / total if total > 0 else 0
        top3 = sum(dist.get(p, 0) for p in [1, 2, 3]) / total if total > 0 else 0
        bottom_half = sum(dist.get(p, 0) for p in range((n_players // 2) + 1, n_players + 1)) / total if total > 0 else 0
        st.metric("Win", f"{top1:.1%}")
        st.metric("Top 3", f"{top3:.1%}")
        st.metric("Bottom Half", f"{bottom_half:.1%}")

    engine_label = "exact" if sr.engine == "brute_force" else f"{sr.total_scenarios:,} simulated"
    st.caption(f"{engine_label} scenarios — {ctx.games_remaining()} games remaining")


def _render_upside_breakdown(ctx, entry, scored, sr, player, total):
    st.subheader("Remaining Upside")

    shared_pts, unique_pts = shared_vs_unique_upside(
        entry, ctx.entries, ctx.tournament, ctx.results
    )
    total_remaining = shared_pts + unique_pts

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Current Points", scored.total_points)
    with col2:
        st.metric("Shared Upside", f"{shared_pts} pts", help="Points from picks at least one other player also has")
    with col3:
        st.metric("Unique Upside", f"{unique_pts} pts", help="Points from picks nobody else in the pool has")

    if total_remaining > 0:
        sep_pct = unique_pts / total_remaining
        st.progress(sep_pct, text=f"{sep_pct:.0%} of remaining upside is unique to you")


def _render_outcome_guide(ctx, sr, player, entry):
    st.subheader("Game Outcomes That Matter")

    effects = label_outcomes(player, sr, ctx.entries)
    if not effects:
        st.info("No remaining games to analyze." if ctx.games_remaining() == 0 else "No critical game data available.")
        return

    # Group by slot_id to show games together
    games: dict[str, list] = {}
    for effect in effects:
        games.setdefault(effect.slot_id, []).append(effect)

    fatal = [e for e in effects if e.label == OutcomeLabel.FATAL]
    separation = [e for e in effects if e.label == OutcomeLabel.SEPARATION]
    survival = [e for e in effects if e.label == OutcomeLabel.SURVIVAL]
    blocking = [e for e in effects if e.label == OutcomeLabel.BLOCKING]

    # Fatal outcomes first
    if fatal:
        st.markdown("**Must avoid — fatal outcomes:**")
        for e in sorted(fatal, key=lambda x: x.win_equity_delta):
            team_name = ctx.team_name(e.team)
            opp_name = ctx.team_name(e.opponent)
            slot = ctx.tournament.slots.get(e.slot_id)
            round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
            delta_str = f"{e.win_equity_delta:+.1%}"
            st.markdown(
                f":red[**{team_name} wins**] ({round_name}) — {e.note} "
                f"({delta_str} win equity)"
            )

    # Separation outcomes
    if separation:
        st.markdown("**Separation opportunities — root for these:**")
        for e in sorted(separation, key=lambda x: -x.win_equity_delta):
            team_name = ctx.team_name(e.team)
            slot = ctx.tournament.slots.get(e.slot_id)
            round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
            delta_str = f"{e.win_equity_delta:+.1%}"
            st.markdown(
                f":green[**{team_name} wins**] ({round_name}) — {e.note} "
                f"({delta_str} win equity)"
            )

    # Survival outcomes
    if survival:
        st.markdown("**Survival outcomes — keeps you alive:**")
        for e in survival:
            team_name = ctx.team_name(e.team)
            slot = ctx.tournament.slots.get(e.slot_id)
            round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
            st.markdown(f":blue[**{team_name} wins**] ({round_name}) — {e.note}")

    # Shared neutral (collapsed)
    shared = [e for e in effects if e.label == OutcomeLabel.SHARED_NEUTRAL]
    if shared:
        with st.expander(f"Shared / neutral outcomes ({len(shared)})"):
            for e in shared:
                team_name = ctx.team_name(e.team)
                slot = ctx.tournament.slots.get(e.slot_id)
                round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
                st.markdown(f":gray[{team_name} wins] ({round_name}) — {e.note}")


def _render_vs_field(ctx, sr, player, n_players):
    st.subheader("How You Stack Up vs. Each Opponent")

    rows = []
    for other in ctx.entries:
        if other.player_name == player:
            continue
        p_ahead = pairwise_beat_probability(sr, player, other.player_name)
        other_scored = ctx.get_scored(other.player_name)
        gap = (ctx.get_scored(player).total_points - other_scored.total_points) if other_scored else 0
        rows.append({
            "Opponent": other.player_name,
            "You lead by": gap,
            "Chance you finish ahead": p_ahead,
        })

    rows.sort(key=lambda r: r["Chance you finish ahead"])

    df = pd.DataFrame(rows)
    df["Chance you finish ahead"] = df["Chance you finish ahead"].apply(lambda x: f"{x:.1%}")
    df["You lead by"] = df["You lead by"].apply(lambda x: f"+{x}" if x > 0 else str(x))
    st.dataframe(df, use_container_width=True, hide_index=True)


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # Player-specific — no single pool summary
