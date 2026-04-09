"""End-of-Tournament Awards — superlatives for each player.

Presentation only. Business logic in core/superlatives.py.
"""

from __future__ import annotations

import streamlit as st

from core.context import AnalysisContext
from core.superlatives import Superlative, compute_superlatives, player_award_summary

TITLE = "End-of-Tournament Awards"
DESCRIPTION = "Superlatives and distinctions for each player"
CATEGORY = "stories"
ORDER = 30
ICON = "🏅"


def render(ctx: AnalysisContext) -> None:
    st.header(f"{ICON} {TITLE}")
    st.caption("Every bracket tells a story. Here's how this pool will be remembered.")

    awards = compute_superlatives(ctx.entries, ctx.tournament, ctx.results)

    if not awards:
        st.info("No awards to display yet — check back when more games are complete.")
        return

    _render_award_cards(awards, ctx)
    st.divider()
    _render_award_summary(ctx, awards)


def _render_award_cards(awards: list[Superlative], ctx: AnalysisContext) -> None:
    cols = st.columns(2)
    for i, award in enumerate(awards):
        with cols[i % 2]:
            with st.container(border=True):
                st.markdown(f"### {award.icon} {award.title}")
                winner_display = award.winner
                if award.is_tie:
                    winner_display += " *(tie)*"
                st.markdown(f"**{winner_display}**")
                st.markdown(f"*{award.value}*")
                st.caption(award.description)
                if award.runner_up and award.runner_up_value:
                    st.caption(f"Runner-up: {award.runner_up} — {award.runner_up_value}")


def _render_award_summary(ctx: AnalysisContext, awards: list[Superlative]) -> None:
    st.subheader("Awards Summary")
    summary = player_award_summary(ctx.entries, awards)

    # Sort players by number of awards won, then alphabetically
    sorted_players = sorted(
        summary.items(),
        key=lambda x: (-len(x[1]), x[0]),
    )

    rows = []
    for player, player_awards in sorted_players:
        rows.append({
            "Player": player,
            "Awards": len(player_awards),
            "Titles": ", ".join(player_awards) if player_awards else "—",
        })

    import pandas as pd
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)


def summarize(ctx: AnalysisContext) -> str | None:
    awards = compute_superlatives(ctx.entries, ctx.tournament, ctx.results)
    if not awards:
        return None

    summary = player_award_summary(ctx.entries, awards)
    # Highlight players with 2+ awards
    highlights = [
        f"{player} claimed {', '.join(titles)}"
        for player, titles in sorted(summary.items(), key=lambda x: -len(x[1]))
        if titles
    ]
    if not highlights:
        return None
    return "; ".join(highlights[:3]) + "."
