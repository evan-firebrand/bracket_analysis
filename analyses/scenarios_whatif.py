"""What If plugin — game-by-game what-if tool and team-focused scenarios.

Presentation only. Business logic in core/scenarios.py.
"""

from __future__ import annotations

import streamlit as st

from core.comparison import compare_counterfactual, find_best_swaps, team_exposure
from core.context import AnalysisContext
from core.scenarios import what_if
from core.scoring import ROUND_NAMES, build_leaderboard
from core.tournament import get_remaining_games

TITLE = "What If...?"
DESCRIPTION = "Explore how upcoming games change the standings"
CATEGORY = "scenarios"
ORDER = 20
ICON = "\U0001f914"  # thinking face


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    if ctx.games_remaining() == 0:
        st.success("Tournament is complete!")
        return

    tab1, tab2, tab3 = st.tabs(["Game-by-Game", "Team Impact", "Pick Swap"])

    with tab1:
        _render_game_by_game(ctx)

    with tab2:
        _render_team_impact(ctx)

    with tab3:
        _render_pick_swap(ctx)


def _render_game_by_game(ctx):
    """Let user pick winners for upcoming games and see leaderboard shift."""
    st.subheader("Pick the winners and see what happens")

    remaining = get_remaining_games(ctx.tournament, ctx.results)
    actionable = [g for g in remaining if g["team_a"] and g["team_b"]]

    if not actionable:
        st.info("No upcoming games with known matchups.")
        return

    # Use session state to track hypothetical picks
    if "whatif_picks" not in st.session_state:
        st.session_state.whatif_picks = {}

    # Reset button
    if st.button("Reset All", key="whatif_reset"):
        st.session_state.whatif_picks = {}
        st.rerun()

    # Game pickers
    for game in actionable:
        slot_id = game["slot_id"]
        team_a = game["team_a"]
        team_b = game["team_b"]
        team_a_name = ctx.team_name(team_a)
        team_b_name = ctx.team_name(team_b)
        slot = ctx.tournament.slots.get(slot_id)
        round_name = ROUND_NAMES.get(slot.round, "") if slot else ""

        options = ["Undecided", team_a_name, team_b_name]
        current = st.session_state.whatif_picks.get(slot_id)
        default_idx = 0
        if current == team_a:
            default_idx = 1
        elif current == team_b:
            default_idx = 2

        choice = st.radio(
            f"{round_name}: {team_a_name} vs {team_b_name}",
            options,
            index=default_idx,
            horizontal=True,
            key=f"whatif_{slot_id}",
        )

        if choice == team_a_name:
            st.session_state.whatif_picks[slot_id] = team_a
        elif choice == team_b_name:
            st.session_state.whatif_picks[slot_id] = team_b
        elif slot_id in st.session_state.whatif_picks:
            del st.session_state.whatif_picks[slot_id]

    # Apply hypothetical outcomes
    picks = st.session_state.whatif_picks
    if not picks:
        st.info("Pick a winner above to see how the leaderboard changes.")
        return

    # Build hypothetical results
    hypo_results = ctx.results
    for slot_id, winner in picks.items():
        game = next((g for g in actionable if g["slot_id"] == slot_id), None)
        if game:
            loser = game["team_b"] if winner == game["team_a"] else game["team_a"]
            hypo_results = what_if(hypo_results, slot_id, winner, loser)

    # Show hypothetical leaderboard vs current
    st.subheader("Projected Leaderboard")
    hypo_board = build_leaderboard(ctx.entries, ctx.tournament, hypo_results)
    current_board = ctx.leaderboard

    # Merge to show rank changes
    display_rows = []
    for _, row in hypo_board.iterrows():
        name = row["Player"]
        current_row = current_board[current_board["Player"] == name]
        current_rank = int(current_row["Rank"].iloc[0]) if len(current_row) > 0 else 0
        new_rank = int(row["Rank"])
        rank_change = current_rank - new_rank  # positive = moved up

        change_str = ""
        if rank_change > 0:
            change_str = f"\u2191{rank_change}"
        elif rank_change < 0:
            change_str = f"\u2193{-rank_change}"

        current_pts = int(current_row["Total"].iloc[0]) if len(current_row) > 0 else 0
        pts_gained = int(row["Total"]) - current_pts

        display_rows.append({
            "Rank": new_rank,
            "Player": name,
            "Total": int(row["Total"]),
            "Change": change_str,
            "Pts Gained": f"+{pts_gained}" if pts_gained > 0 else str(pts_gained),
        })

    st.dataframe(display_rows, use_container_width=True, hide_index=True)


def _render_team_impact(ctx):
    """Show what happens to the group if a specific team is eliminated."""
    st.subheader("What if a team gets knocked out?")
    st.caption("See who gains and who loses the most")

    alive = sorted(ctx.alive_teams)
    if not alive:
        st.info("No alive teams.")
        return

    selected_team = st.selectbox(
        "Select a team to eliminate",
        alive,
        format_func=lambda s: ctx.team_name(s),
        key="whatif_team",
    )

    if not selected_team:
        return

    team_name = ctx.team_name(selected_team)

    # Calculate exposure per player for this team
    exposure = team_exposure(ctx.entries, ctx.tournament, ctx.results)
    team_total = exposure.get(selected_team, 0)

    st.markdown(
        f"If **{team_name}** is eliminated, **{team_total} total points** "
        f"become impossible across the group."
    )

    # Per-player impact
    from core.scoring import POINTS_PER_ROUND

    player_impact = []
    for entry in ctx.entries:
        scored = ctx.get_scored(entry.player_name)
        if not scored:
            continue
        pts_lost = 0
        for slot_id in scored.pending_picks:
            if entry.picks.get(slot_id) == selected_team:
                slot = ctx.tournament.slots[slot_id]
                pts_lost += POINTS_PER_ROUND.get(slot.round, 0)

        player_impact.append({
            "Player": entry.player_name,
            "Points Lost": pts_lost,
            "Current Pts": scored.total_points,
            "New Max": scored.max_possible - pts_lost,
        })

    player_impact.sort(key=lambda r: -r["Points Lost"])

    if player_impact:
        # Narrative
        most_hurt = player_impact[0]
        least_hurt = player_impact[-1]
        if most_hurt["Points Lost"] > 0:
            st.markdown(
                f"**{most_hurt['Player']}** would be hurt the most, "
                f"losing **{most_hurt['Points Lost']} potential points**. "
                + (f"**{least_hurt['Player']}** would be least affected."
                   if least_hurt["Points Lost"] == 0
                   else "")
            )

        st.dataframe(player_impact, use_container_width=True, hide_index=True)


def _render_pick_swap(ctx):
    """Swap a player's pending pick and see how their win probability changes."""
    st.subheader("Would changing a pick help?")
    st.caption("Swap a player's pending pick and see how their win probability changes.")

    remaining = get_remaining_games(ctx.tournament, ctx.results)
    actionable = [g for g in remaining if g["team_a"] and g["team_b"]]

    if not actionable:
        st.info("No upcoming games with known matchups.")
        return

    # Player selector
    player = st.selectbox(
        "Select a player",
        ctx.player_names(),
        key="pickswap_player",
    )
    if not player:
        return

    entry = next((e for e in ctx.entries if e.player_name == player), None)
    if entry is None:
        return

    # Filter to games where this player has a pending pick
    pending_set = set(ctx.scored_entries[player].pending_picks) if player in ctx.scored_entries else set()
    swappable = [g for g in actionable if g["slot_id"] in pending_set]

    if not swappable:
        st.info(f"{player} has no pending picks in upcoming games.")
        return

    # Game selector — only games this player has a pending pick for
    def game_label(g):
        slot = ctx.tournament.slots.get(g["slot_id"])
        round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
        return f"{round_name}: {ctx.team_name(g['team_a'])} vs {ctx.team_name(g['team_b'])}"

    selected_game = st.selectbox(
        "Select a game",
        swappable,
        format_func=game_label,
        key="pickswap_game",
    )

    if not selected_game:
        return

    slot_id = selected_game["slot_id"]
    team_a = selected_game["team_a"]
    team_b = selected_game["team_b"]
    current_pick = entry.picks.get(slot_id)
    alt_team = team_b if current_pick == team_a else team_a

    current_name = ctx.team_name(current_pick) if current_pick else "None"
    alt_name = ctx.team_name(alt_team)

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Current Pick", current_name)
    with col2:
        st.metric("Swap To", alt_name)

    # Single-swap comparison — session state keyed by player+slot so stale
    # results from previous selections don't bleed through on re-render
    compare_key = f"pickswap_result_{player}_{slot_id}"
    if st.button("Compare Win Probabilities", key="pickswap_compare"):
        with st.spinner("Running scenarios..."):
            result = compare_counterfactual(
                ctx.entries,
                player,
                {slot_id: alt_team},
                ctx.tournament,
                ctx.results,
                propagate=True,
            )
        st.session_state[compare_key] = result

    if compare_key in st.session_state:
        result = st.session_state[compare_key]
        orig = result["original_pct"]
        cf = result["counterfactual_pct"]
        delta = result["delta"]

        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Current Win%", f"{orig:.1f}%")
        with c2:
            st.metric("After Swap Win%", f"{cf:.1f}%", delta=f"{delta:+.1f}pp")
        with c3:
            if delta > 1:
                st.success(f"+{delta:.1f}pp — swap helps")
            elif delta < -1:
                st.warning(f"{delta:.1f}pp — swap hurts")
            else:
                st.info("Minimal impact")

    # Find Best Swap across all pending picks
    st.divider()
    best_key = f"pickswap_best_{player}"
    if st.button(
        "Find Best Swap",
        key="pickswap_best",
        help="Tests every possible swap across all pending picks",
    ):
        with st.spinner("Testing all possible swaps..."):
            swaps = find_best_swaps(
                ctx.entries, player, ctx.tournament, ctx.results, max_swaps=10,
            )
        st.session_state[best_key] = swaps

    if best_key in st.session_state:
        swaps = st.session_state[best_key]
        if not swaps:
            st.info("No beneficial swaps found for any pending game.")
        else:
            st.subheader("Top Swap Suggestions")
            rows = []
            for swap in swaps:
                slot = ctx.tournament.slots.get(swap["slot_id"])
                round_name = ROUND_NAMES.get(slot.round, "") if slot else ""
                rows.append({
                    "Round": round_name,
                    "Current Pick": ctx.team_name(swap["old_team"]) if swap["old_team"] else "?",
                    "Swap To": ctx.team_name(swap["new_team"]),
                    "Win% Before": f"{swap['original_pct']:.1f}%",
                    "Win% After": f"{swap['new_pct']:.1f}%",
                    "Delta": f"{swap['delta']:+.1f}pp",
                })
            st.dataframe(rows, use_container_width=True, hide_index=True)


def summarize(ctx: AnalysisContext) -> str | None:
    return None  # Interactive tool, no single summary
