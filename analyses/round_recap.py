"""Round Recap plugin — what happened in the most recent round.

Presentation only. Business logic in core/recap.py.
"""

from __future__ import annotations

import streamlit as st

from core.context import AnalysisContext
from core.recap import RoundRecap, round_recap, standings_diff

TITLE = "What Happened?"
DESCRIPTION = "Round recap — results, upsets, and standings impact"
CATEGORY = "results"
ORDER = 10
ICON = "\U0001f4cb"  # clipboard


def render(ctx: AnalysisContext) -> None:
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    recap = round_recap(ctx.tournament, ctx.results, ctx.entries)

    if recap is None:
        st.info("The tournament hasn't started yet. Check back once games are played.")
        return

    _render_round_header(recap)
    _render_game_results(recap, ctx)
    st.divider()
    _render_standings_shift(recap, ctx)
    st.divider()
    _render_eliminated_teams(recap, ctx)


def _render_round_header(recap: RoundRecap) -> None:
    st.subheader(f"{recap.round_name} Recap")
    if not recap.is_complete:
        completed = len(recap.games)
        st.caption(
            f"{completed} of {recap.total_games_in_round} games complete — "
            "showing results so far"
        )


def _render_game_results(recap: RoundRecap, ctx: AnalysisContext) -> None:
    # Group games by region, preserving natural order
    region_order = ["East", "West", "South", "Midwest", "Final Four"]
    games_by_region: dict[str, list] = {}
    for game in recap.games:
        games_by_region.setdefault(game.region, []).append(game)

    # Sort regions by predefined order, append any unexpected regions at end
    ordered_regions = [r for r in region_order if r in games_by_region]
    ordered_regions += [r for r in games_by_region if r not in region_order]

    for region in ordered_regions:
        st.subheader(region)
        for game in games_by_region[region]:
            winner_team = ctx.tournament.teams.get(game.winner)
            loser_team = ctx.tournament.teams.get(game.loser)
            winner_name = winner_team.name if winner_team else game.winner
            loser_name = loser_team.name if loser_team else game.loser
            winner_seed = f"({winner_team.seed}) " if winner_team else ""
            loser_seed = f"({loser_team.seed}) " if loser_team else ""

            score_str = f"  {game.score}" if game.score else ""
            matchup = f"**{winner_seed}{winner_name}** def. {loser_seed}{loser_name}{score_str}"

            pick_label = f"{game.pick_count}/{game.total_players} picked {winner_name}"

            col1, col2 = st.columns([3, 2])
            with col1:
                if game.is_upset:
                    st.markdown(f"{matchup}  🚨 **UPSET**")
                else:
                    st.markdown(matchup)
            with col2:
                if game.is_upset:
                    st.warning(pick_label, icon="⚠️")
                else:
                    st.success(pick_label, icon="✅")


def _render_standings_shift(recap: RoundRecap, ctx: AnalysisContext) -> None:
    st.subheader("Standings After This Round")

    diffs = standings_diff(ctx.tournament, ctx.results, ctx.entries, recap.round)
    if not diffs:
        return

    rows = []
    for d in diffs:
        if d.rank_change > 0:
            change_str = f"↑{d.rank_change}"
        elif d.rank_change < 0:
            change_str = f"↓{abs(d.rank_change)}"
        else:
            change_str = "—"

        name = d.player_name
        if d.clinched:
            name += " 🏆 Clinched"
        elif d.newly_eliminated:
            name += " ❌ Eliminated"

        rows.append({
            "Player": name,
            "This Round": f"+{d.points_this_round}" if d.points_this_round > 0 else str(d.points_this_round),
            "Total": d.total_points,
            "Rank": f"#{d.rank_after}",
            "Change": change_str,
        })

    st.dataframe(
        rows,
        use_container_width=True,
        hide_index=True,
    )


def _render_eliminated_teams(recap: RoundRecap, ctx: AnalysisContext) -> None:
    """Show teams knocked out this round and how many players had them going further."""
    st.subheader("Teams Eliminated This Round")

    if not recap.games:
        st.caption("No completed games yet.")
        return

    for game in recap.games:
        loser_team = ctx.tournament.teams.get(game.loser)
        winner_team = ctx.tournament.teams.get(game.winner)
        loser_name = loser_team.name if loser_team else game.loser
        winner_name = winner_team.name if winner_team else game.winner
        loser_seed = f"({loser_team.seed}) " if loser_team else ""
        winner_seed = f"({winner_team.seed}) " if winner_team else ""

        # Count players who had the loser picked to advance beyond this round
        surviving_pickers = _count_surviving_pickers(game.loser, game.slot_id, ctx)
        survivor_note = ""
        if surviving_pickers > 0:
            plural = "s" if surviving_pickers != 1 else ""
            survivor_note = f" — {surviving_pickers} player{plural} had them going further"

        st.markdown(
            f"- {loser_seed}**{loser_name}** — lost to {winner_seed}{winner_name}{survivor_note}"
        )


def summarize(ctx: AnalysisContext) -> str | None:
    recap = round_recap(ctx.tournament, ctx.results, ctx.entries)
    if recap is None:
        return None

    upsets = [g for g in recap.games if g.is_upset]
    status = "complete" if recap.is_complete else f"{len(recap.games)}/{recap.total_games_in_round} games"

    if upsets:
        upset_names = [
            ctx.tournament.teams[g.winner].name
            if g.winner in ctx.tournament.teams else g.winner
            for g in upsets
        ]
        upset_str = " and ".join(upset_names)
        return f"{recap.round_name} ({status}): {len(upsets)} upset{'s' if len(upsets) != 1 else ''} — {upset_str}."

    return f"{recap.round_name} ({status}): no upsets, all favorites advanced."


def _count_surviving_pickers(
    eliminated_team: str,
    lost_in_slot: str,
    ctx: AnalysisContext,
) -> int:
    """Count how many players had this team picked to win beyond the given slot."""
    lost_slot = ctx.tournament.slots.get(lost_in_slot)
    if not lost_slot:
        return 0

    # Any slot in a later round where this player picked the eliminated team
    count = 0
    for entry in ctx.entries:
        for slot_id, pick in entry.picks.items():
            if pick != eliminated_team:
                continue
            slot = ctx.tournament.slots.get(slot_id)
            if slot and slot.round > lost_slot.round:
                count += 1
                break  # only count each player once

    return count
