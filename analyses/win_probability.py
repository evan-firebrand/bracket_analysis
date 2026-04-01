"""Win Probability plugin — who's going to win, finish distributions, critical games.

Presentation only. Business logic in core/scenarios.py.
"""

from __future__ import annotations

import json
from itertools import product
from pathlib import Path

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.models import GameResult, Results
from core.narrative import describe_probability, ordinal
from core.scenarios import (
    _get_win_probability,
    _resolve_participants,
    run_scenarios,
)
from core.scoring import ROUND_NAMES, score_entry
from core.tournament import get_remaining_games, get_remaining_slots

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
    _render_how_this_ends(ctx)
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
    df["Win %"] = df["Win %"].apply(lambda x: "0%" if x == 0 else f"{x:.1%}")
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


def _load_odds() -> dict | None:
    """Load odds data if available."""
    path = Path("data/odds.json")
    if path.exists():
        with open(path) as f:
            return json.load(f)
    return None


def _render_how_this_ends(ctx):
    """Map out every path to the finish — who wins when, what's decided early."""
    remaining = get_remaining_slots(ctx.tournament, ctx.results)
    if not remaining or len(remaining) > 15:
        return

    odds = _load_odds()

    # Separate remaining games into "deciding" games (semis, earlier rounds)
    # and the final game (championship / last game in the bracket)
    remaining_by_round: dict[int, list[str]] = {}
    for slot_id in remaining:
        rnd = ctx.tournament.slots[slot_id].round
        remaining_by_round.setdefault(rnd, []).append(slot_id)

    sorted_rounds = sorted(remaining_by_round.keys())
    if len(sorted_rounds) < 2:
        return

    # The "deciding" games are all rounds except the last
    # The "final" is the last round's game(s)
    deciding_rounds = sorted_rounds[:-1]
    final_round = sorted_rounds[-1]
    deciding_slots = []
    for r in deciding_rounds:
        deciding_slots.extend(remaining_by_round[r])
    final_slots = remaining_by_round[final_round]

    if not deciding_slots:
        return

    # Get matchups for deciding games
    deciding_games = []
    for slot_id in deciding_slots:
        team_a, team_b = _resolve_participants(
            ctx.tournament, ctx.results.results, slot_id,
        )
        if team_a and team_b:
            deciding_games.append((slot_id, team_a, team_b))

    if not deciding_games:
        return

    # Enumerate all combinations of deciding game outcomes
    paths = []
    for outcomes in product([0, 1], repeat=len(deciding_games)):
        # Build hypothetical results with these deciding game outcomes
        hypo = dict(ctx.results.results)
        label_parts = []
        path_prob = 1.0

        for i, (slot_id, team_a, team_b) in enumerate(deciding_games):
            if outcomes[i] == 0:
                winner, loser = team_a, team_b
            else:
                winner, loser = team_b, team_a
            hypo[slot_id] = GameResult(winner=winner, loser=loser)

            prob_a = (
                _get_win_probability(team_a, team_b, ctx.tournament, odds)
                if odds
                else 0.5
            )
            game_prob = prob_a if outcomes[i] == 0 else (1 - prob_a)
            path_prob *= game_prob
            label_parts.append(ctx.team_name(winner))

        # Now simulate all final game outcomes and see who wins the pool
        final_winners = set()
        for final_outcomes in product([0, 1], repeat=len(final_slots)):
            final_hypo = dict(hypo)
            for j, fslot in enumerate(final_slots):
                ft_a, ft_b = _resolve_participants(
                    ctx.tournament, final_hypo, fslot,
                )
                if not ft_a or not ft_b:
                    continue
                if final_outcomes[j] == 0:
                    fw, fl = ft_a, ft_b
                else:
                    fw, fl = ft_b, ft_a
                final_hypo[fslot] = GameResult(winner=fw, loser=fl)

            full_results = Results(last_updated="", results=final_hypo)
            scores = [
                (e.player_name, score_entry(e, ctx.tournament, full_results).total_points)
                for e in ctx.entries
            ]
            scores.sort(key=lambda x: -x[1])
            final_winners.add(scores[0][0])

        final_round_name = ROUND_NAMES.get(final_round, "final")
        if len(final_winners) == 1:
            pool_winner = list(final_winners)[0]
            decided = True
        else:
            pool_winner = " or ".join(sorted(final_winners))
            decided = False

        paths.append({
            "label": " + ".join(label_parts),
            "prob": path_prob,
            "pool_winner": pool_winner,
            "decided_early": decided,
            "final_winners": final_winners,
        })

    # Sort by probability
    paths.sort(key=lambda p: -p["prob"])

    # Calculate how often the pool is decided before the final
    decided_prob = sum(p["prob"] for p in paths if p["decided_early"])

    st.subheader("How This Ends")

    if decided_prob > 0.5:
        final_name = ROUND_NAMES.get(final_round, "the final")
        st.markdown(
            f"**There's a {decided_prob:.0%} chance the pool is decided "
            f"before {final_name} is even played.**"
        )

    # Table of paths
    rows = []
    for p in paths:
        rows.append({
            "Saturday": p["label"],
            "Chance": f"{p['prob']:.0%}",
            "Pool Winner": p["pool_winner"],
            "Decided?": "Before the final" if p["decided_early"] else f"Comes down to {ROUND_NAMES.get(final_round, 'the final')}",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    # Dark horse narrative: find players whose win prob is much higher
    # than their current ranking suggests
    leaderboard_rank = {}
    for i, row in ctx.leaderboard.iterrows():
        leaderboard_rank[row["Player"]] = int(row["Rank"])

    sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)
    total = sr.total_scenarios
    contenders = [
        (name, sr.win_counts[name] / total, leaderboard_rank.get(name, 99))
        for name in sr.win_counts
        if sr.win_counts[name] > 0
    ]
    contenders.sort(key=lambda x: -x[1])

    for name, win_pct, rank in contenders:
        if rank >= 3 and win_pct >= 0.15:
            # Dark horse: winning a significant chunk but not on the podium
            # Find if their path needs favorites or underdogs
            best_path = max(
                (p for p in paths if name in p["final_winners"]),
                key=lambda p: p["prob"],
                default=None,
            )
            if best_path:
                st.markdown("---")
                st.markdown(
                    f"**Don't sleep on {name}.** Currently {ordinal(rank)} in "
                    f"the standings, but wins the pool in {win_pct:.0%} of "
                    f"scenarios. The most likely path? **{best_path['label']}** "
                    f"({best_path['prob']:.0%} chance) — and both of those "
                    f"teams are the Vegas favorites. If the favorites hold on "
                    f"Saturday, {name} wins it all."
                    if best_path["decided_early"]
                    else
                    f"**Don't sleep on {name}.** Currently {ordinal(rank)} in "
                    f"the standings, but wins the pool in {win_pct:.0%} of "
                    f"scenarios."
                )
                break


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
