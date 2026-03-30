"""Win Probability plugin — who's going to win, finish distributions, critical games.

Presentation only. Business logic in core/scenarios.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.narrative import describe_probability, ordinal
from core.scenarios import run_scenarios
from core.scoring import ROUND_NAMES

TITLE = "Who's Going to Win?"
DESCRIPTION = "Win probabilities, finish distributions, and critical games"
CATEGORY = "scenarios"
ORDER = 10
ICON = "\U0001f3b2"  # dice


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    if ctx.games_remaining() == 0:
        st.success("Tournament is complete! Check the Leaderboard for final standings.")
        return

    # Run scenario engine
    with st.spinner("Crunching scenarios..."):
        scenario_results = run_scenarios(ctx.entries, ctx.tournament, ctx.results)

    total = scenario_results.total_scenarios
    engine_label = "exact" if scenario_results.engine == "brute_force" else "simulated"

    st.caption(
        f"{total:,} {engine_label} scenarios analyzed "
        f"({ctx.games_remaining()} games remaining)"
    )

    _render_win_probabilities(ctx, scenario_results)
    _render_critical_games(ctx, scenario_results)
    _render_finish_distributions(ctx, scenario_results)


def _render_win_probabilities(ctx, sr):
    """Show each player's chance of winning."""
    st.subheader("Win Probability")

    total = sr.total_scenarios
    rows = []
    for entry in ctx.entries:
        name = entry.player_name
        wins = sr.win_counts.get(name, 0)
        pct = wins / total if total > 0 else 0
        scored = ctx.get_scored(name)
        rows.append({
            "Player": name,
            "Win %": pct,
            "Scenarios Won": wins,
            "Current Pts": scored.total_points if scored else 0,
            "Status": describe_probability(pct),
        })

    rows.sort(key=lambda r: -r["Win %"])

    # Narrative for the leader
    if rows:
        leader = rows[0]
        st.markdown(
            f"**{leader['Player']}** is the favorite — "
            f"{leader['Status']}."
        )

    # Bar chart
    chart_data = {r["Player"]: r["Win %"] for r in rows}
    st.bar_chart(chart_data)

    # Table
    df = pd.DataFrame(rows)
    df["Win %"] = df["Win %"].apply(lambda x: f"{x:.1%}")
    st.dataframe(
        df[["Player", "Win %", "Scenarios Won", "Current Pts", "Status"]],
        use_container_width=True,
        hide_index=True,
    )

    # Eliminated callout
    eliminated = [name for name, elim in sr.is_eliminated.items() if elim]
    if eliminated:
        st.warning(
            f"**Eliminated ({len(eliminated)}):** "
            + ", ".join(eliminated)
            + " — no remaining scenario has them finishing first."
        )


def _render_critical_games(ctx, sr):
    """Show which upcoming games matter most."""
    if not sr.critical_games:
        return

    st.subheader("Critical Games")
    st.caption("Games that swing win probabilities the most")

    for cg in sr.critical_games[:5]:  # top 5
        team_a_name = ctx.team_name(cg.team_a)
        team_b_name = ctx.team_name(cg.team_b)
        slot = ctx.tournament.slots.get(cg.slot_id)
        round_name = ROUND_NAMES.get(slot.round, "") if slot else ""

        st.markdown(
            f"**{team_a_name} vs {team_b_name}** ({round_name}) "
            f"— max swing: **{cg.max_swing:.0%}**"
        )

        # Show swings for each player
        swing_rows = []
        for name, (pct_a, pct_b) in sorted(
            cg.swings.items(), key=lambda x: -abs(x[1][0] - x[1][1])
        ):
            swing_rows.append({
                "Player": name,
                f"If {team_a_name} wins": f"{pct_a:.1%}",
                f"If {team_b_name} wins": f"{pct_b:.1%}",
                "Swing": f"{abs(pct_a - pct_b):.1%}",
            })

        st.dataframe(
            pd.DataFrame(swing_rows),
            use_container_width=True,
            hide_index=True,
        )


def _render_finish_distributions(ctx, sr):
    """Show full finish position distributions per player."""
    st.subheader("Finish Position Distributions")

    total = sr.total_scenarios
    player = st.selectbox(
        "Select a player",
        ctx.player_names(),
        key="win_prob_finish_player",
    )

    if player and player in sr.finish_distributions:
        dist = sr.finish_distributions[player]
        n_players = len(ctx.entries)

        chart_data = {}
        for pos in range(1, n_players + 1):
            count = dist.get(pos, 0)
            pct = count / total if total > 0 else 0
            chart_data[ordinal(pos)] = pct

        st.bar_chart(chart_data)

        # Summary
        win_pct = sr.win_counts.get(player, 0) / total if total > 0 else 0
        podium = sum(dist.get(p, 0) for p in [1, 2, 3]) / total if total > 0 else 0
        st.markdown(
            f"**{player}** finishes 1st in **{win_pct:.1%}** of scenarios, "
            f"top 3 in **{podium:.1%}**."
        )


def summarize(ctx: AnalysisContext) -> str | None:
    if not ctx.entries or ctx.games_remaining() == 0:
        return None

    sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)
    total = sr.total_scenarios
    if total == 0:
        return None

    leader = max(sr.win_counts.items(), key=lambda x: x[1])
    pct = leader[1] / total
    return (
        f"{leader[0]} is the favorite at {pct:.0%} — "
        f"{describe_probability(pct)}."
    )
