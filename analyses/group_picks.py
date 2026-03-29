"""Group Picks plugin — pick distributions, contrarian report, team exposure."""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.narrative import describe_pick_popularity
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES

TITLE = "The Group's Picks"
DESCRIPTION = "See what everyone picked and who's going against the crowd"
CATEGORY = "matchups"
ORDER = 20
ICON = "\U0001f4ca"  # bar chart


def _pick_popularity(
    ctx: AnalysisContext,
) -> dict[str, Counter]:
    """For each slot, count how many players picked each team."""
    popularity: dict[str, Counter] = {}
    for slot_id in ctx.tournament.slot_order:
        counter: Counter = Counter()
        for entry in ctx.entries:
            pick = entry.picks.get(slot_id)
            if pick:
                counter[pick] += 1
        popularity[slot_id] = counter
    return popularity


def _team_exposure(ctx: AnalysisContext) -> dict[str, int]:
    """For each alive team, total points at risk across all players in remaining games."""
    exposure: dict[str, int] = {}
    for entry in ctx.entries:
        scored = ctx.get_scored(entry.player_name)
        if not scored:
            continue
        for slot_id in scored.pending_picks:
            team = entry.picks.get(slot_id)
            if team and ctx.is_alive(team):
                slot = ctx.tournament.slots[slot_id]
                pts = POINTS_PER_ROUND.get(slot.round, 0)
                exposure[team] = exposure.get(team, 0) + pts
    return exposure


def _contrarian_picks(
    ctx: AnalysisContext,
    popularity: dict[str, Counter],
    threshold: float = 0.20,
) -> dict[str, list[dict]]:
    """For each player, find picks that fewer than threshold% of the group shares."""
    n_players = len(ctx.entries)
    contrarian: dict[str, list[dict]] = {}

    for entry in ctx.entries:
        picks_list = []
        for slot_id in ctx.tournament.slot_order:
            pick = entry.picks.get(slot_id)
            if not pick:
                continue
            count = popularity[slot_id].get(pick, 0)
            pct = count / n_players if n_players > 0 else 0
            if pct < threshold:
                slot = ctx.tournament.slots[slot_id]
                correct = ctx.results.winner_of(slot_id) == pick if ctx.results.is_complete(slot_id) else None
                picks_list.append({
                    "slot_id": slot_id,
                    "round": slot.round,
                    "team": pick,
                    "pct": pct,
                    "count": count,
                    "correct": correct,
                })
        contrarian[entry.player_name] = picks_list

    return contrarian


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    popularity = _pick_popularity(ctx)
    n_players = len(ctx.entries)

    # --- Champion picks ---
    champ_slot = None
    for slot_id, slot in ctx.tournament.slots.items():
        if slot.feeds_into is None:
            champ_slot = slot_id
            break

    if champ_slot and champ_slot in popularity:
        st.subheader("Champion Picks")
        champ_counts = popularity[champ_slot]
        champ_data = {
            ctx.team_name(team): count
            for team, count in champ_counts.most_common()
        }
        st.bar_chart(champ_data)

        # Narrative about champion picks
        most_popular = champ_counts.most_common(1)
        if most_popular:
            team, count = most_popular[0]
            if count == n_players:
                st.markdown(f"**Everyone** picked **{ctx.team_name(team)}** to win it all.")
            elif count == 1:
                # Find who
                picker = next(
                    e.player_name for e in ctx.entries
                    if e.picks.get(champ_slot) == team
                )
                st.markdown(
                    f"**{ctx.team_name(team)}** is the most popular champion pick, "
                    f"but only **{picker}** has them. "
                    f"Everyone else picked someone different."
                )
            else:
                lone_wolves = [
                    (ctx.team_name(t), next(
                        e.player_name for e in ctx.entries
                        if e.picks.get(champ_slot) == t
                    ))
                    for t, c in champ_counts.items() if c == 1
                ]
                msg = (
                    f"**{ctx.team_name(team)}** is the most popular champion pick "
                    f"with **{count} of {n_players}** players."
                )
                if lone_wolves:
                    for team_name, picker in lone_wolves:
                        msg += f" Only **{picker}** has **{team_name}**."
                st.markdown(msg)

    # --- Round-by-round pick distributions ---
    st.subheader("Pick Distributions by Round")

    round_filter = st.selectbox(
        "Select round",
        [(r, name) for r, name in ROUND_NAMES.items()
         if any(s.round == r for s in ctx.tournament.slots.values())],
        format_func=lambda x: x[1],
        key="group_picks_round",
    )

    if round_filter:
        round_num = round_filter[0]
        round_slots = [
            s for s in ctx.tournament.slots.values()
            if s.round == round_num
        ]
        round_slots.sort(key=lambda s: (s.region, s.position))

        for slot in round_slots:
            counts = popularity[slot.slot_id]
            if not counts:
                continue

            # Show the game context
            if slot.top_team and slot.bottom_team:
                game_label = (
                    f"{ctx.team_name(slot.top_team)} vs "
                    f"{ctx.team_name(slot.bottom_team)}"
                )
            else:
                game_label = f"{slot.region} \u2014 Game {slot.position}"

            result_str = ""
            if ctx.results.is_complete(slot.slot_id):
                winner = ctx.results.winner_of(slot.slot_id)
                result_str = f" \u2014 **{ctx.team_name(winner)}** won"

            st.markdown(f"**{game_label}**{result_str}")

            # Bar showing pick distribution
            pick_data = {}
            for team, count in counts.most_common():
                pct = count / n_players
                label = f"{ctx.team_name(team)} ({count}/{n_players})"
                pick_data[label] = count
            st.bar_chart(pick_data)

    # --- Team exposure ---
    st.subheader("Team Exposure")
    st.caption("Total points at risk across all players if this team is eliminated")

    exposure = _team_exposure(ctx)
    if exposure:
        exposure_sorted = sorted(exposure.items(), key=lambda x: -x[1])
        exp_df = pd.DataFrame([
            {
                "Team": ctx.team_name(team),
                "Total Points at Risk": pts,
                "Status": "Alive" if ctx.is_alive(team) else "Eliminated",
            }
            for team, pts in exposure_sorted
        ])
        st.dataframe(exp_df, use_container_width=True, hide_index=True)
    else:
        st.info("No pending picks with alive teams.")

    # --- Contrarian report ---
    st.subheader("Contrarian Report")
    st.caption("Picks that fewer than 20% of the group made")

    contrarian = _contrarian_picks(ctx, popularity)
    for player_name, picks in sorted(
        contrarian.items(), key=lambda x: -len(x[1])
    ):
        if not picks:
            continue
        correct_count = sum(1 for p in picks if p["correct"] is True)
        wrong_count = sum(1 for p in picks if p["correct"] is False)
        pending_count = sum(1 for p in picks if p["correct"] is None)

        with st.expander(
            f"{player_name} \u2014 {len(picks)} contrarian picks "
            f"(\u2705 {correct_count} \u274c {wrong_count} \u23f3 {pending_count})"
        ):
            for pick in picks:
                team_name = ctx.team_name(pick["team"])
                round_name = ROUND_NAMES.get(pick["round"], f"Round {pick['round']}")
                pct_str = f"{pick['pct']:.0%}"
                pop_desc = describe_pick_popularity(pick["pct"])

                if pick["correct"] is True:
                    icon = "\u2705"
                elif pick["correct"] is False:
                    icon = "\u274c"
                else:
                    icon = "\u23f3"

                st.markdown(
                    f"{icon} **{team_name}** in {round_name} "
                    f"\u2014 only {pick['count']}/{n_players} ({pct_str}) \u2014 {pop_desc}"
                )


def summarize(ctx: AnalysisContext) -> str | None:
    if not ctx.entries:
        return None

    # Find the most "exposed" team
    exposure = _team_exposure(ctx)
    if not exposure:
        return None

    top_team, top_pts = max(exposure.items(), key=lambda x: x[1])
    return (
        f"{ctx.team_name(top_team)} has the most riding on them \u2014 "
        f"{top_pts} total points at risk across the group."
    )
