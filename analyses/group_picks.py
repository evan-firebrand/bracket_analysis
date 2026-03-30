"""Group Picks plugin — pick distributions, contrarian report, team exposure, chalk score.

Presentation only. Business logic lives in core/comparison.py.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.comparison import (
    chalk_score,
    contrarian_picks,
    group_chalk_score,
    pick_popularity,
    team_exposure,
)
from core.context import AnalysisContext
from core.narrative import describe_pick_popularity
from core.scoring import ROUND_NAMES

TITLE = "The Group's Picks"
DESCRIPTION = "See what everyone picked and who's going against the crowd"
CATEGORY = "matchups"
ORDER = 20
ICON = "\U0001f4ca"  # bar chart


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    popularity = pick_popularity(ctx.entries, ctx.tournament)
    n_players = len(ctx.entries)

    _render_chalk_score(ctx)
    _render_champion_picks(ctx, popularity, n_players)
    _render_round_picks(ctx, popularity, n_players)
    _render_team_exposure(ctx)
    _render_contrarian_report(ctx, popularity, n_players)


def _render_chalk_score(ctx: AnalysisContext):
    """Show how chalky each player's bracket is."""
    st.subheader("Chalk Score")
    st.caption(
        "How often each player picked the higher seed in Round 1. "
        "100% = pure chalk, 0% = all upsets."
    )

    group_score = group_chalk_score(ctx.entries, ctx.tournament)
    individual = chalk_score(ctx.entries, ctx.tournament)

    st.markdown(f"**Group average:** {group_score:.0%} chalk")

    if individual:
        chalk_df = pd.DataFrame([
            {"Player": name, "Chalk %": f"{score:.0%}", "Score": score}
            for name, score in sorted(individual.items(), key=lambda x: -x[1])
        ])
        st.bar_chart(
            data=chalk_df.set_index("Player")["Score"],
        )


def _render_champion_picks(ctx, popularity, n_players):
    """Show who everyone picked to win it all."""
    champ_slot = next(
        (sid for sid, s in ctx.tournament.slots.items() if s.feeds_into is None),
        None,
    )
    if not champ_slot or champ_slot not in popularity:
        return

    st.subheader("Champion Picks")
    champ_counts = popularity[champ_slot]

    champ_data = {
        ctx.team_name(team): count
        for team, count in champ_counts.most_common()
    }
    st.bar_chart(champ_data)

    # Narrative
    most_popular = champ_counts.most_common(1)
    if most_popular:
        team, count = most_popular[0]
        lone_wolves = [
            (ctx.team_name(t), next(
                e.player_name for e in ctx.entries if e.picks.get(champ_slot) == t
            ))
            for t, c in champ_counts.items() if c == 1
        ]
        if count == n_players:
            st.markdown(f"**Everyone** picked **{ctx.team_name(team)}** to win it all.")
        else:
            msg = (
                f"**{ctx.team_name(team)}** is the most popular champion pick "
                f"with **{count} of {n_players}** players."
            )
            for team_name, picker in lone_wolves:
                msg += f" Only **{picker}** has **{team_name}**."
            st.markdown(msg)


def _render_round_picks(ctx, popularity, n_players):
    """Show pick distributions for each game, filterable by round."""
    st.subheader("Pick Distributions by Round")

    rounds_available = [
        (r, name) for r, name in ROUND_NAMES.items()
        if any(s.round == r for s in ctx.tournament.slots.values())
    ]
    round_filter = st.selectbox(
        "Select round",
        rounds_available,
        format_func=lambda x: x[1],
        key="group_picks_round",
    )

    if not round_filter:
        return

    round_num = round_filter[0]
    round_slots = sorted(
        [s for s in ctx.tournament.slots.values() if s.round == round_num],
        key=lambda s: (s.region, s.position),
    )

    for slot in round_slots:
        counts = popularity[slot.slot_id]
        if not counts:
            continue

        if slot.top_team and slot.bottom_team:
            game_label = f"{ctx.team_name(slot.top_team)} vs {ctx.team_name(slot.bottom_team)}"
        else:
            game_label = f"{slot.region} \u2014 Game {slot.position}"

        result_str = ""
        if ctx.results.is_complete(slot.slot_id):
            winner = ctx.results.winner_of(slot.slot_id)
            result_str = f" \u2014 **{ctx.team_name(winner)}** won"

        st.markdown(f"**{game_label}**{result_str}")

        pick_data = {
            f"{ctx.team_name(team)} ({count}/{n_players})": count
            for team, count in counts.most_common()
        }
        st.bar_chart(pick_data)


def _render_team_exposure(ctx):
    """Show how many points are riding on each alive team across all brackets."""
    st.subheader("Team Exposure")
    st.caption("Total points at risk across all brackets if this team is eliminated")

    exposure = team_exposure(ctx.entries, ctx.tournament, ctx.results)
    if not exposure:
        st.info("No pending picks with alive teams.")
        return

    exposure_sorted = sorted(exposure.items(), key=lambda x: -x[1])
    exp_df = pd.DataFrame([
        {"Team": ctx.team_name(team), "Total Points at Risk": pts}
        for team, pts in exposure_sorted
    ])
    st.dataframe(exp_df, use_container_width=True, hide_index=True)


def _render_contrarian_report(ctx, popularity, n_players):
    """Show each player's picks that go against the crowd."""
    st.subheader("Contrarian Report")
    st.caption("Picks that fewer than 20% of the group made")

    contrarian = contrarian_picks(
        ctx.entries, ctx.tournament, ctx.results, popularity
    )

    for player_name, picks in sorted(contrarian.items(), key=lambda x: -len(x[1])):
        if not picks:
            continue
        correct = sum(1 for p in picks if p.correct is True)
        wrong = sum(1 for p in picks if p.correct is False)
        pending = sum(1 for p in picks if p.correct is None)

        with st.expander(
            f"{player_name} \u2014 {len(picks)} contrarian picks "
            f"(\u2705 {correct} \u274c {wrong} \u23f3 {pending})"
        ):
            for pick in picks:
                team_name = ctx.team_name(pick.team)
                round_name = ROUND_NAMES.get(pick.round, f"Round {pick.round}")
                pct_str = f"{pick.pct:.0%}"
                pop_desc = describe_pick_popularity(pick.pct)

                if pick.correct is True:
                    icon = "\u2705"
                elif pick.correct is False:
                    icon = "\u274c"
                else:
                    icon = "\u23f3"

                st.markdown(
                    f"{icon} **{team_name}** in {round_name} "
                    f"\u2014 only {pick.count}/{n_players} ({pct_str}) \u2014 {pop_desc}"
                )


def summarize(ctx: AnalysisContext) -> str | None:
    if not ctx.entries:
        return None

    exposure = team_exposure(ctx.entries, ctx.tournament, ctx.results)
    if not exposure:
        return None

    top_team, top_pts = max(exposure.items(), key=lambda x: x[1])
    return (
        f"{ctx.team_name(top_team)} has the most riding on them \u2014 "
        f"{top_pts} total points at risk across the group."
    )
