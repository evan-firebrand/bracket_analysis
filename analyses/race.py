"""The Race — round-by-round leaderboard history, momentum, and insights."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.models import Results
from core.narrative import describe_trend, ordinal
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES, score_entry

TITLE = "The Race"
DESCRIPTION = "How the standings have shifted round by round"
CATEGORY = "standings"
ORDER = 20
ICON = "\U0001f4c8"  # chart with upward trend


def _build_history(ctx: AnalysisContext) -> dict:
    """Build round-by-round rank and points history for all players.

    Returns dict with keys: rounds, ranks, points, gains, correct, total_games.
    Each is keyed by player name where applicable.
    """
    completed_rounds = sorted({
        slot.round
        for slot in ctx.tournament.slots.values()
        if ctx.results.is_complete(slot.slot_id)
    })

    if not completed_rounds:
        return {}

    names = ctx.player_names()
    ranks: dict[str, list[int]] = {n: [] for n in names}
    points: dict[str, list[int]] = {n: [] for n in names}
    gains: dict[str, list[int]] = {n: [] for n in names}
    correct: dict[str, list[tuple[int, int]]] = {n: [] for n in names}

    prev_totals: dict[str, int] = {n: 0 for n in names}

    for through_round in completed_rounds:
        # Filter results through this round
        filtered = {
            slot_id: result
            for slot_id, result in ctx.results.results.items()
            if ctx.tournament.slots[slot_id].round <= through_round
        }
        partial = Results(last_updated="", results=filtered)

        # Score everyone
        scores = []
        for entry in ctx.entries:
            scored = score_entry(entry, ctx.tournament, partial)
            scores.append((entry.player_name, scored.total_points))

        scores.sort(key=lambda x: -x[1])

        # Record ranks and points
        for rank, (name, pts) in enumerate(scores, 1):
            ranks[name].append(rank)
            points[name].append(pts)
            gains[name].append(pts - prev_totals[name])
            prev_totals[name] = pts

        # Count correct picks in this specific round
        round_games = 0
        for slot_id, result in ctx.results.results.items():
            if ctx.tournament.slots[slot_id].round == through_round:
                round_games += 1

        for entry in ctx.entries:
            n_correct = 0
            for slot_id, result in ctx.results.results.items():
                if ctx.tournament.slots[slot_id].round == through_round:
                    if entry.picks.get(slot_id) == result.winner:
                        n_correct += 1
            correct[entry.player_name].append((n_correct, round_games))

    return {
        "rounds": completed_rounds,
        "ranks": ranks,
        "points": points,
        "gains": gains,
        "correct": correct,
    }


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    history = _build_history(ctx)
    if not history:
        st.info("No completed rounds yet.")
        return

    rounds = history["rounds"]
    round_labels = [ROUND_NAMES.get(r, f"Round {r}") for r in rounds]

    _render_rank_chart(ctx, history, round_labels)
    _render_round_mvps(ctx, history, rounds, round_labels)
    _render_momentum(ctx, history, rounds, round_labels)
    _render_player_detail(ctx, history, rounds, round_labels)


def _render_rank_chart(ctx, history, round_labels):
    """Line chart showing each player's rank over time."""
    st.subheader("Position by Round")

    # Build dataframe for chart: columns = players, index = round labels
    chart_data = {}
    for name, rank_list in history["ranks"].items():
        chart_data[name] = rank_list

    df = pd.DataFrame(chart_data, index=round_labels)

    # Streamlit line chart (lower rank = better, so invert y-axis)
    # Use st.line_chart — it doesn't support inverted axes natively,
    # so we'll display a table alongside for clarity
    st.line_chart(df)
    st.caption("Lower position = better. 1 = first place.")


def _render_round_mvps(ctx, history, rounds, round_labels):
    """Show who had the best round each round."""
    st.subheader("Round MVP")

    for i, rnd in enumerate(rounds):
        round_label = round_labels[i]
        ppg = POINTS_PER_ROUND.get(rnd, 0)

        # Find best performer this round
        best_name = None
        best_gain = -1
        best_correct = (0, 0)

        for name in ctx.player_names():
            gain = history["gains"][name][i]
            if gain > best_gain:
                best_gain = gain
                best_name = name
                best_correct = history["correct"][name][i]

        n_correct, n_games = best_correct
        max_pts = n_games * ppg
        pct = best_gain / max_pts * 100 if max_pts > 0 else 0

        st.markdown(
            f"**{round_label}**: {best_name} — "
            f"+{best_gain} pts ({n_correct}/{n_games} correct, {pct:.0f}% of max)"
        )


def _render_momentum(ctx, history, rounds, round_labels):
    """Show biggest movers across the tournament."""
    st.subheader("Momentum")

    if len(rounds) < 2:
        st.caption("Need at least two completed rounds to show momentum.")
        return

    names = ctx.player_names()

    # Overall movement: first round rank vs latest rank
    movements = []
    for name in names:
        first_rank = history["ranks"][name][0]
        latest_rank = history["ranks"][name][-1]
        change = first_rank - latest_rank  # positive = improved
        movements.append((name, first_rank, latest_rank, change))

    movements.sort(key=lambda x: -x[3])

    rows = []
    for name, first_rank, latest_rank, change in movements:
        trend = describe_trend(change)
        # Points gained total
        total_pts = history["points"][name][-1]

        rows.append({
            "Player": name,
            f"After {round_labels[0]}": ordinal(first_rank),
            "Current": ordinal(latest_rank),
            "Moved": f"+{change}" if change > 0 else str(change) if change < 0 else "—",
            "Trend": trend.capitalize(),
            "Total Pts": total_pts,
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    # Narrative for biggest mover
    biggest = movements[0]
    if biggest[3] > 0:
        st.markdown(
            f"**Biggest climber**: {biggest[0]} — started {ordinal(biggest[1])}, "
            f"now {ordinal(biggest[2])}. {describe_trend(biggest[3]).capitalize()}."
        )

    # Most consistent: smallest total rank variance
    most_consistent = min(
        names,
        key=lambda n: max(history["ranks"][n]) - min(history["ranks"][n]),
    )
    rank_range = history["ranks"][most_consistent]
    if max(rank_range) == min(rank_range):
        st.markdown(
            f"**Most consistent**: {most_consistent} — "
            f"held {ordinal(rank_range[0])} place every round."
        )
    else:
        st.markdown(
            f"**Most consistent**: {most_consistent} — "
            f"never strayed more than {max(rank_range) - min(rank_range)} "
            f"spots from their average position."
        )


def _render_player_detail(ctx, history, rounds, round_labels):
    """Expandable per-player round-by-round breakdown."""
    st.subheader("Player Detail")

    player = st.selectbox(
        "Select a player",
        ctx.player_names(),
        key="race_player_detail",
    )

    if not player:
        return

    # Build per-round table
    rows = []
    for i, rnd in enumerate(rounds):
        ppg = POINTS_PER_ROUND.get(rnd, 0)
        n_correct, n_games = history["correct"][player][i]
        max_pts = n_games * ppg
        gain = history["gains"][player][i]
        pct = gain / max_pts * 100 if max_pts > 0 else 0

        rank = history["ranks"][player][i]
        rank_change = (
            history["ranks"][player][i - 1] - rank if i > 0 else 0
        )

        rows.append({
            "Round": round_labels[i],
            "Correct": f"{n_correct}/{n_games}",
            "Points": f"+{gain}",
            "Accuracy": f"{pct:.0f}%",
            "Rank": ordinal(rank),
            "Change": f"+{rank_change}" if rank_change > 0 else str(rank_change) if rank_change < 0 else "—",
        })

    st.dataframe(
        pd.DataFrame(rows),
        use_container_width=True,
        hide_index=True,
    )

    # Points gained bar chart
    chart_data = {
        round_labels[i]: history["gains"][player][i]
        for i in range(len(rounds))
    }
    st.bar_chart(chart_data)

    # Player narrative
    best_round_idx = max(range(len(rounds)), key=lambda i: history["gains"][player][i])
    best_gain = history["gains"][player][best_round_idx]
    best_correct, best_total = history["correct"][player][best_round_idx]
    st.markdown(
        f"**Best round**: {round_labels[best_round_idx]} — "
        f"+{best_gain} pts ({best_correct}/{best_total} correct)."
    )


def summarize(ctx: AnalysisContext) -> str | None:
    history = _build_history(ctx)
    if not history or len(history["rounds"]) < 2:
        return None

    names = ctx.player_names()
    movements = []
    for name in names:
        first = history["ranks"][name][0]
        latest = history["ranks"][name][-1]
        movements.append((name, first - latest))

    biggest = max(movements, key=lambda x: x[1])
    if biggest[1] > 0:
        return (
            f"{biggest[0]} has climbed {biggest[1]} spots since the "
            f"Round of 64 — {describe_trend(biggest[1])}."
        )

    return "The standings have been steady — no big movers so far."
