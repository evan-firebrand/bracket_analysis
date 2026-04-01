"""The Race — round-by-round leaderboard history, momentum, and insights."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.context import AnalysisContext
from core.models import GameResult, Results
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


def _build_key_moments(ctx: AnalysisContext) -> list[dict]:
    """Find the most impactful games in the tournament.

    For each completed game, calculates:
    - Points destroyed: future-round points that became impossible for each player
      when the losing team was eliminated
    - Alternate reality: what the standings would look like if the game went the
      other way (removing downstream games that depended on the winner)

    Returns a list of moment dicts sorted by total points destroyed, each with:
    slot_id, round, winner/loser info, points_destroyed, players_affected,
    most_hurt player, and whether flipping would change the current leader.
    """
    moments = []

    # Current standings for comparison
    actual_scores = {
        e.player_name: score_entry(e, ctx.tournament, ctx.results).total_points
        for e in ctx.entries
    }
    actual_leader = max(actual_scores, key=actual_scores.get)

    for slot_id, result in ctx.results.results.items():
        slot = ctx.tournament.slots[slot_id]
        loser = result.loser
        winner = result.winner

        # --- Points destroyed by this result ---
        total_destroyed = 0
        player_destroyed: dict[str, int] = {}

        for entry in ctx.entries:
            destroyed = 0
            for other_id, other_slot in ctx.tournament.slots.items():
                if other_slot.round > slot.round:
                    if entry.picks.get(other_id) == loser:
                        destroyed += POINTS_PER_ROUND[other_slot.round]
            if destroyed > 0:
                player_destroyed[entry.player_name] = destroyed
                total_destroyed += destroyed

        # --- Alternate reality: what if this game went the other way? ---
        alt_results_dict = dict(ctx.results.results)
        alt_results_dict[slot_id] = GameResult(
            winner=result.loser, loser=result.winner,
        )
        # Remove downstream games that depended on the actual winner
        for other_id, other_slot in ctx.tournament.slots.items():
            if other_slot.round > slot.round and other_id in alt_results_dict:
                other_result = alt_results_dict[other_id]
                if winner in (other_result.winner, other_result.loser):
                    del alt_results_dict[other_id]

        alt_results = Results(last_updated="", results=alt_results_dict)
        alt_scores = {
            e.player_name: score_entry(e, ctx.tournament, alt_results).total_points
            for e in ctx.entries
        }
        alt_leader = max(alt_scores, key=alt_scores.get)

        # Total point swing across all players
        total_swing = sum(
            abs(actual_scores[n] - alt_scores.get(n, 0))
            for n in actual_scores
        )

        if total_destroyed == 0 and total_swing < 100:
            continue

        winner_seed = ctx.team_seed(winner)
        loser_seed = ctx.team_seed(loser)
        is_upset = (
            winner_seed is not None
            and loser_seed is not None
            and winner_seed > loser_seed
        )

        most_hurt = (
            max(player_destroyed.items(), key=lambda x: x[1])
            if player_destroyed
            else None
        )

        moments.append({
            "slot_id": slot_id,
            "round": slot.round,
            "winner": winner,
            "loser": loser,
            "winner_seed": winner_seed,
            "loser_seed": loser_seed,
            "is_upset": is_upset,
            "points_destroyed": total_destroyed,
            "players_affected": len(player_destroyed),
            "player_destroyed": player_destroyed,
            "most_hurt": most_hurt,
            "alt_leader": alt_leader,
            "changes_leader": alt_leader != actual_leader,
            "total_swing": total_swing,
        })

    moments.sort(key=lambda x: -x["points_destroyed"])
    return moments


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    history = _build_history(ctx)
    if not history:
        st.info("No completed rounds yet.")
        return

    rounds = history["rounds"]
    round_labels = [ROUND_NAMES.get(r, f"Round {r}") for r in rounds]

    _render_rank_chart(ctx, history, round_labels)
    _render_key_moments(ctx)
    _render_bracket_autopsy(ctx)
    _render_round_mvps(ctx, history, rounds, round_labels)
    _render_momentum(ctx, history, rounds, round_labels)
    _render_player_detail(ctx, history, rounds, round_labels)


def _render_key_moments(ctx):
    """Show the most impactful games — bracket busters and turning points."""
    moments = _build_key_moments(ctx)
    if not moments:
        return

    st.subheader("Key Moments")

    # --- Bracket Busters: top games by points destroyed ---
    busters = [m for m in moments if m["points_destroyed"] > 0][:5]
    if busters:
        st.markdown("**Bracket Busters** — games that did the most damage")
        rows = []
        for m in busters:
            winner_name = ctx.team_name(m["winner"])
            loser_name = ctx.team_name(m["loser"])
            round_name = ROUND_NAMES.get(m["round"], "")
            upset_tag = " (upset)" if m["is_upset"] else ""
            seed_str = (
                f"({m['winner_seed']}) {winner_name} over "
                f"({m['loser_seed']}) {loser_name}"
            )
            most_hurt_str = ""
            if m["most_hurt"]:
                name, pts = m["most_hurt"]
                most_hurt_str = f"{name} ({pts} pts)"

            rows.append({
                "Game": seed_str + upset_tag,
                "Round": round_name,
                "Pts Destroyed": m["points_destroyed"],
                "Hit": f"{m['players_affected']}/{len(ctx.entries)}",
                "Most Affected": most_hurt_str,
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

        # Narrative for the biggest moment
        top = busters[0]
        winner_name = ctx.team_name(top["winner"])
        loser_name = ctx.team_name(top["loser"])
        round_name = ROUND_NAMES.get(top["round"], "")
        st.markdown(
            f"**The biggest bracket buster**: {winner_name} knocking out "
            f"{loser_name} in the {round_name} wiped out "
            f"**{top['points_destroyed']} future points** across the group."
        )

    # --- Turning Points: games that would change the current leader ---
    turning = [m for m in moments if m["changes_leader"]]
    turning.sort(key=lambda x: -x["total_swing"])
    if turning:
        st.markdown("---")
        st.markdown("**Turning Points** — if these had gone the other way, the leader would be different")
        rows = []
        for m in turning[:5]:
            winner_name = ctx.team_name(m["winner"])
            loser_name = ctx.team_name(m["loser"])
            round_name = ROUND_NAMES.get(m["round"], "")

            rows.append({
                "Game": f"{winner_name} over {loser_name}",
                "Round": round_name,
                "Point Swing": m["total_swing"],
                "Leader If Flipped": m["alt_leader"],
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )

    # --- Elimination Moments: when each eliminated player's fate was sealed ---
    _render_elimination_moments(ctx)


def _render_elimination_moments(ctx):
    """Show which game eliminated each player from contention."""
    # For each player currently eliminated (win_count == 0 in scenarios),
    # walk through games chronologically and find the first game after which
    # they could no longer finish first — i.e., their max possible dropped
    # below the eventual leader's score in every remaining scenario.
    #
    # Simpler approach: find the game that destroyed their last path to a
    # pick that would have kept them competitive. We use the scoring engine:
    # replay games in order and find when max_possible first drops below
    # the current leader's actual points.
    from core.scenarios import run_scenarios

    # Get current elimination status
    sr = run_scenarios(ctx.entries, ctx.tournament, ctx.results)
    eliminated = [
        name for name, is_elim in sr.is_eliminated.items() if is_elim
    ]

    if not eliminated:
        return

    # For each eliminated player, find the game that sealed their fate.
    # Walk through games in slot_order. After each game, check if the player's
    # max_possible has dropped below the best other player's guaranteed minimum.
    # A simpler heuristic: find the last game where they lost future points
    # (had the loser picked to advance further).
    elimination_games: dict[str, dict] = {}

    # Get games in chronological order (by round, then position)
    game_order = [
        sid for sid in ctx.tournament.slot_order
        if sid in ctx.results.results
    ]

    for name in eliminated:
        entry = ctx.get_entry(name)
        if not entry:
            continue

        # Find the last game that destroyed points for this player
        last_hit_slot = None
        last_hit_loser = None
        last_hit_destroyed = 0

        for slot_id in game_order:
            result = ctx.results.results[slot_id]
            slot = ctx.tournament.slots[slot_id]
            loser = result.loser

            destroyed = 0
            for other_id, other_slot in ctx.tournament.slots.items():
                if other_slot.round > slot.round:
                    if entry.picks.get(other_id) == loser:
                        destroyed += POINTS_PER_ROUND[other_slot.round]

            if destroyed > 0:
                last_hit_slot = slot_id
                last_hit_loser = loser
                last_hit_destroyed = destroyed

        if last_hit_slot:
            slot = ctx.tournament.slots[last_hit_slot]
            result = ctx.results.results[last_hit_slot]
            elimination_games[name] = {
                "slot_id": last_hit_slot,
                "round": slot.round,
                "winner": result.winner,
                "loser": result.loser,
                "pts_lost": last_hit_destroyed,
            }

    if elimination_games:
        st.markdown("---")
        st.markdown("**Eliminated** — the game that sealed each player's fate")

        rows = []
        for name, info in elimination_games.items():
            winner_name = ctx.team_name(info["winner"])
            loser_name = ctx.team_name(info["loser"])
            round_name = ROUND_NAMES.get(info["round"], "")
            rows.append({
                "Player": name,
                "Eliminated By": f"{winner_name} over {loser_name}",
                "Round": round_name,
                "Pts Lost": info["pts_lost"],
            })

        st.dataframe(
            pd.DataFrame(rows),
            use_container_width=True,
            hide_index=True,
        )


def _describe_depth(round_num: int) -> str:
    """Describe how deep a player had a team going, in plain English."""
    return {
        6: "winning it all",
        5: "the Final Four",
        4: "the Elite Eight",
        3: "the Sweet Sixteen",
        2: "the Round of 32",
    }.get(round_num, f"round {round_num}")


def _build_player_regrets(ctx: AnalysisContext) -> list[dict]:
    """For each player, find their costliest wrong pick and best call."""
    results = []

    for entry in ctx.entries:
        name = entry.player_name
        regrets = []
        triumphs = []

        for slot_id, result in ctx.results.results.items():
            slot = ctx.tournament.slots[slot_id]
            picked = entry.picks.get(slot_id)
            winner_seed = ctx.team_seed(result.winner)
            loser_seed = ctx.team_seed(result.loser)

            if picked != result.winner:
                # Wrong pick — how much did it cost?
                loser = result.loser
                pts_this = POINTS_PER_ROUND[slot.round]
                future_pts = 0
                deepest_round = slot.round
                for oid, oslot in ctx.tournament.slots.items():
                    if oslot.round > slot.round:
                        if entry.picks.get(oid) == loser:
                            future_pts += POINTS_PER_ROUND[oslot.round]
                            deepest_round = max(deepest_round, oslot.round)

                others_right = sum(
                    1 for e in ctx.entries
                    if e.player_name != name
                    and e.picks.get(slot_id) == result.winner
                )
                regrets.append({
                    "slot_id": slot_id,
                    "round": slot.round,
                    "team": loser,
                    "beat_by": result.winner,
                    "score": result.score or "",
                    "team_seed": loser_seed,
                    "beat_by_seed": winner_seed,
                    "total_cost": pts_this + future_pts,
                    "deepest_round": deepest_round,
                    "others_right": others_right,
                    "is_upset": (
                        winner_seed is not None
                        and loser_seed is not None
                        and winner_seed > loser_seed
                    ),
                })
            else:
                # Correct pick — how contrarian was it?
                others_right = sum(
                    1 for e in ctx.entries
                    if e.player_name != name
                    and e.picks.get(slot_id) == result.winner
                )
                is_upset = (
                    winner_seed is not None
                    and loser_seed is not None
                    and winner_seed > loser_seed
                )
                # Score by value * how few others had it
                contrarian = len(ctx.entries) - 1 - others_right
                pts = POINTS_PER_ROUND[slot.round]
                triumphs.append({
                    "slot_id": slot_id,
                    "round": slot.round,
                    "team": result.winner,
                    "over": result.loser,
                    "score": result.score or "",
                    "team_seed": winner_seed,
                    "over_seed": loser_seed,
                    "pts": pts,
                    "others_right": others_right,
                    "contrarian": contrarian,
                    "is_upset": is_upset,
                    "value_score": pts * (1 + contrarian / len(ctx.entries)),
                })

        regrets.sort(key=lambda r: -r["total_cost"])
        triumphs.sort(key=lambda t: -t["value_score"])

        results.append({
            "name": name,
            "biggest_miss": regrets[0] if regrets else None,
            "best_call": triumphs[0] if triumphs else None,
        })

    return results


def _render_bracket_autopsy(ctx):
    """Tell each player's story — their biggest miss and best call."""
    regrets = _build_player_regrets(ctx)
    if not regrets:
        return

    st.subheader("Bracket Autopsy")
    st.caption("Every bracket tells a story — the picks that made you and the ones that broke you")

    for player in regrets:
        name = player["name"]
        miss = player["biggest_miss"]
        best = player["best_call"]

        with st.expander(f"**{name}**", expanded=False):
            if miss:
                team = ctx.team_name(miss["team"])
                beat_by = ctx.team_name(miss["beat_by"])
                rnd = ROUND_NAMES[miss["round"]]
                depth = _describe_depth(miss["deepest_round"])
                score = f" ({miss['score']})" if miss["score"] else ""
                others = miss["others_right"]
                total_others = len(ctx.entries) - 1

                # Build the narrative
                if miss["deepest_round"] == 6:
                    rode_line = f"had {team} winning the whole thing"
                else:
                    rode_line = f"had {team} going all the way to {depth}"

                # Was this a shared pain or did they go it alone?
                if others == 0:
                    crowd_line = "Nobody else in the group saw it coming either."
                elif others <= 2:
                    crowd_line = f"Only {others} other{'s' if others > 1 else ''} in the group got that one right."
                else:
                    crowd_line = f"Most of the group got that one right — {others} of {total_others} had it."

                # Was it close?
                if miss["score"]:
                    parts = miss["score"].split("-")
                    if len(parts) == 2:
                        try:
                            margin = abs(int(parts[0]) - int(parts[1]))
                            if margin <= 3:
                                close_line = f" A {margin}-point game that could have gone either way."
                            else:
                                close_line = ""
                        except ValueError:
                            close_line = ""
                    else:
                        close_line = ""
                else:
                    close_line = ""

                st.markdown(
                    f"**The one that got away:** {name} {rode_line} — "
                    f"then {beat_by} knocked them out in the {rnd}{score}.{close_line} "
                    f"{crowd_line}"
                )

            if best:
                team = ctx.team_name(best["team"])
                over = ctx.team_name(best["over"])
                rnd = ROUND_NAMES[best["round"]]
                score = f" ({best['score']})" if best["score"] else ""
                others = best["others_right"]
                total_others = len(ctx.entries) - 1

                if best["is_upset"] and others == 0:
                    call_line = (
                        f"**The best call:** Called the {team} upset over {over} "
                        f"in the {rnd}{score} — the only one in the group who had it."
                    )
                elif best["is_upset"]:
                    call_line = (
                        f"**The best call:** Nailed the {team} upset over {over} "
                        f"in the {rnd}{score}."
                    )
                elif others <= 1:
                    call_line = (
                        f"**The best call:** Had {team} over {over} in the "
                        f"{rnd}{score} when almost nobody else did."
                    )
                else:
                    call_line = (
                        f"**The best call:** Picked {team} to beat {over} in the "
                        f"{rnd}{score}."
                    )

                st.markdown(call_line)


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
