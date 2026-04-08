"""Pool Exposure plugin — field-wide team and path analysis.

Shows where the pool is crowded vs. unique: which teams are overowned,
which championship paths are rare, and how each player's remaining exposure
compares to the field.

Presentation only. Business logic leverages core/comparison.py and core/metrics.py.
"""

from __future__ import annotations

from collections import Counter

import pandas as pd
import streamlit as st

from core.comparison import pick_popularity, team_exposure
from core.context import AnalysisContext
from core.metrics import separation_index_all
from core.scoring import POINTS_PER_ROUND, ROUND_NAMES, get_alive_teams

TITLE = "Pool Exposure"
DESCRIPTION = "Where the pool is crowded and where you're alone"
CATEGORY = "matchups"
ORDER = 30
ICON = "\U0001f5fa\ufe0f"  # world map


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    if not ctx.entries:
        st.info("No entries loaded.")
        return

    n_players = len(ctx.entries)
    popularity = pick_popularity(ctx.entries, ctx.tournament)
    alive = get_alive_teams(ctx.tournament, ctx.results)

    _render_champion_distribution(ctx, popularity, n_players)
    st.divider()
    _render_field_exposure_by_round(ctx, popularity, n_players, alive)
    st.divider()
    _render_crowded_vs_rare_paths(ctx, popularity, n_players, alive)
    st.divider()
    _render_separation_ranking(ctx)
    st.divider()
    _render_per_player_alignment(ctx, popularity, n_players, alive)


def _render_champion_distribution(ctx, popularity, n_players):
    st.subheader("Champion Picks")
    st.caption("Who does the pool think will win it all?")

    # Find the championship slot (feeds_into = None)
    champ_slot = next(
        (sid for sid, s in ctx.tournament.slots.items() if s.feeds_into is None),
        None,
    )
    if not champ_slot or champ_slot not in popularity:
        return

    champ_counts = popularity[champ_slot]
    rows = []
    for team, count in champ_counts.most_common():
        alive_flag = "\U0001f7e2" if team in ctx.alive_teams else "\U0001f534"
        rows.append({
            "Team": ctx.team_name(team),
            "Alive": alive_flag,
            "Picked by": count,
            "% of Pool": f"{count / n_players:.0%}",
        })

    col1, col2 = st.columns([1, 1])
    with col1:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    with col2:
        chart_data = {ctx.team_name(t): c for t, c in champ_counts.most_common()}
        st.bar_chart(chart_data)


def _render_field_exposure_by_round(ctx, popularity, n_players, alive):
    st.subheader("Field Exposure by Round")
    st.caption(
        "For each alive team, how many brackets have them advancing to each round. "
        "High ownership = shared upside. Low ownership = rare path."
    )

    completed = set(ctx.results.results.keys())

    # Build: team -> {round: count}
    team_round_counts: dict[str, dict[int, int]] = {}
    for slot_id in ctx.tournament.slot_order:
        if slot_id in completed:
            continue
        slot = ctx.tournament.slots[slot_id]
        counter = popularity.get(slot_id, Counter())
        for team, count in counter.items():
            if team not in alive:
                continue
            team_round_counts.setdefault(team, {})[slot.round] = count

    if not team_round_counts:
        st.info("No remaining games.")
        return

    # Build DataFrame: one row per team, columns = round names
    remaining_rounds = sorted(
        {r for td in team_round_counts.values() for r in td.keys()}
    )
    round_cols = [ROUND_NAMES.get(r, f"R{r}") for r in remaining_rounds]

    rows = []
    for team, round_counts in sorted(team_round_counts.items(), key=lambda x: -sum(x[1].values())):
        row = {"Team": ctx.team_name(team)}
        for r, col in zip(remaining_rounds, round_cols):
            count = round_counts.get(r, 0)
            row[col] = f"{count}/{n_players}" if count > 0 else "—"
        rows.append(row)

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)


def _render_crowded_vs_rare_paths(ctx, popularity, n_players, alive):
    st.subheader("Crowded Paths vs. Rare Paths")
    st.caption(
        "A 'crowded' path is one many brackets share — winning it doesn't differentiate. "
        "A 'rare' path is unique upside."
    )

    completed = set(ctx.results.results.keys())

    # Find championship slot
    champ_slot = next(
        (sid for sid, s in ctx.tournament.slots.items() if s.feeds_into is None),
        None,
    )
    if not champ_slot:
        return

    # For each alive team's championship pick: count how many players have it
    champ_picks = popularity.get(champ_slot, Counter())

    crowded = [(ctx.team_name(t), c) for t, c in champ_picks.most_common() if t in alive and c > 1]
    rare = [(ctx.team_name(t), c) for t, c in champ_picks.most_common() if t in alive and c == 1]
    unique = [(ctx.team_name(t), 0) for t in alive if t not in champ_picks]

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Crowded championship paths** (shared by 2+ brackets):")
        for name, count in sorted(crowded, key=lambda x: -x[1]):
            st.markdown(f"- {name}: {count}/{n_players} brackets")
        if not crowded:
            st.markdown("_None — all remaining title picks are unique_")

    with col2:
        st.markdown("**Rare paths** (held by exactly 1 bracket):")
        for name, _ in rare:
            st.markdown(f"- {name}: only 1 player has this")
        if not rare:
            st.markdown("_None — no lone-wolf title picks remain_")

    if unique:
        st.markdown(
            f"**Teams still alive that nobody picked to win**: "
            + ", ".join(name for name, _ in unique)
        )


def _render_separation_ranking(ctx):
    st.subheader("Separation Index — How Unique Is Each Bracket?")
    st.caption(
        "Separation = fraction of remaining upside that's unique to this player. "
        "High separation = rare picks. Low separation = shared upside with the field."
    )

    separations = separation_index_all(ctx.entries, ctx.tournament, ctx.results)

    rows = []
    for entry in ctx.entries:
        scored = ctx.get_scored(entry.player_name)
        sep = separations[entry.player_name]
        if scored:
            remaining = scored.max_possible - scored.total_points
            unique_pts = round(sep * remaining)
            shared_pts = remaining - unique_pts
        else:
            unique_pts = 0
            shared_pts = 0

        rows.append({
            "Player": entry.player_name,
            "Separation": sep,
            "Unique Pts Remaining": unique_pts,
            "Shared Pts Remaining": shared_pts,
        })

    rows.sort(key=lambda r: -r["Separation"])

    df = pd.DataFrame(rows)
    col1, col2 = st.columns([1, 1])
    with col1:
        sep_chart = {r["Player"]: r["Separation"] for r in rows}
        st.bar_chart(sep_chart)
    with col2:
        df["Separation"] = df["Separation"].apply(lambda x: f"{x:.0%}")
        st.dataframe(
            df[["Player", "Separation", "Unique Pts Remaining", "Shared Pts Remaining"]],
            use_container_width=True,
            hide_index=True,
        )


def _render_per_player_alignment(ctx, popularity, n_players, alive):
    st.subheader("Your Alignment vs. the Field")
    st.caption("Select a player to see how their remaining picks compare to the pool's consensus.")

    player = st.selectbox(
        "Select player",
        ctx.player_names(),
        key="pool_exposure_player",
    )

    if not player:
        return

    entry = ctx.get_entry(player)
    if not entry:
        return

    completed = set(ctx.results.results.keys())
    rows = []

    for slot_id in ctx.tournament.slot_order:
        if slot_id in completed:
            continue
        pick = entry.picks.get(slot_id)
        if not pick or pick not in alive:
            continue

        slot = ctx.tournament.slots[slot_id]
        slot_popularity = popularity.get(slot_id, Counter())
        count = slot_popularity.get(pick, 0)
        ownership = count / n_players

        if ownership >= 0.70:
            alignment = "Aligned"
        elif ownership >= 0.40:
            alignment = "Slight majority"
        elif ownership >= 0.20:
            alignment = "Minority"
        else:
            alignment = "Unique"

        rows.append({
            "Round": ROUND_NAMES.get(slot.round, f"R{slot.round}"),
            "Your Pick": ctx.team_name(pick),
            "Also picked by": f"{count}/{n_players}",
            "Ownership": ownership,
            "Alignment": alignment,
        })

    if not rows:
        st.info("No remaining live picks to show.")
        return

    df = pd.DataFrame(rows)

    # Color coding via dataframe styling isn't native in st.dataframe,
    # so show separate sections
    unique = df[df["Alignment"] == "Unique"]
    aligned = df[df["Alignment"].isin(["Aligned", "Slight majority"])]

    if not unique.empty:
        st.markdown("**Your unique picks** (nobody else has these):")
        st.dataframe(
            unique[["Round", "Your Pick", "Also picked by"]],
            use_container_width=True,
            hide_index=True,
        )

    if not aligned.empty:
        with st.expander(f"Picks shared with the majority ({len(aligned)})"):
            st.dataframe(
                aligned[["Round", "Your Pick", "Also picked by", "Alignment"]],
                use_container_width=True,
                hide_index=True,
            )


def summarize(ctx: AnalysisContext) -> str | None:
    """Summarize overall pool concentration."""
    popularity = pick_popularity(ctx.entries, ctx.tournament)
    n_players = len(ctx.entries)
    if n_players == 0:
        return None

    champ_slot = next(
        (sid for sid, s in ctx.tournament.slots.items() if s.feeds_into is None),
        None,
    )
    if not champ_slot or champ_slot not in popularity:
        return None

    champ_picks = popularity[champ_slot]
    top_team, top_count = champ_picks.most_common(1)[0]
    pct = top_count / n_players
    team_name = ctx.team_name(top_team)

    if pct >= 0.60:
        return f"Pool is heavily concentrated: {pct:.0%} have {team_name} winning it all."
    elif pct >= 0.40:
        return f"{team_name} is the most popular champion pick at {pct:.0%} ownership."
    else:
        return f"Champion picks are split — {team_name} leads at {pct:.0%}."
