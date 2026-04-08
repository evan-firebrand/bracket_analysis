"""NCAA Bracket Analysis — Streamlit entry point."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import streamlit as st
import yaml

from analyses import discover_plugins, get_plugins_by_category
from core.context import AnalysisContext


def _load_config() -> dict:
    path = Path("config.yaml")
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}

st.set_page_config(
    page_title="Bracket Analysis",
    page_icon="\U0001f3c0",
    layout="wide",
)


@st.cache_data(ttl=60)
def load_context() -> AnalysisContext:
    """Load all data and pre-compute. Cached for 60 seconds."""
    return AnalysisContext(data_dir="data")


def main():
    # Load data
    try:
        ctx = load_context()
    except FileNotFoundError as e:
        st.error(f"Data file not found: {e}")
        st.info("Make sure data files exist in the `data/` directory.")
        return
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return

    # Discover plugins
    plugins = discover_plugins()
    plugins_by_cat = get_plugins_by_category(plugins)

    # --- Sidebar navigation ---
    with st.sidebar:
        st.title("\U0001f3c0 Bracket Analysis")
        st.caption(f"{ctx.tournament.year} NCAA Tournament")

        # Refresh button
        if st.button("Refresh Data", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

        st.divider()

        # Global "Viewing as" player selector
        config = _load_config()
        my_player_name = config.get("app", {}).get("my_player_name", "")
        player_names = ctx.player_names()
        default_index = 0
        if my_player_name and my_player_name in player_names:
            default_index = player_names.index(my_player_name)
        viewing_player = st.selectbox(
            "Viewing as",
            player_names,
            index=default_index,
        )
        st.session_state["viewing_player"] = viewing_player

        st.divider()

        # Build navigation from plugins
        page_options = {"Home": None}
        for cat, cat_plugins in plugins_by_cat.items():
            for plugin in cat_plugins:
                label = f"{plugin.icon} {plugin.title}"
                page_options[label] = plugin

        selected_label = st.radio(
            "Navigation",
            list(page_options.keys()),
            label_visibility="collapsed",
        )

    # --- Main content area ---
    selected_plugin = page_options[selected_label]

    if selected_plugin is None:
        _render_home(ctx, plugins)
    else:
        selected_plugin.render(ctx)


def _relative_time(iso_str: str) -> str:
    """Convert ISO 8601 timestamp to a human-readable relative string."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            minutes = int(delta.total_seconds() / 60)
            return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
        elif hours < 24:
            h = int(hours)
            return f"{h} hour{'s' if h != 1 else ''} ago"
        else:
            days = int(hours / 24)
            return f"{days} day{'s' if days != 1 else ''} ago"
    except Exception:
        return iso_str


def _render_home(ctx: AnalysisContext, plugins):
    """Render the home dashboard."""
    config = _load_config()
    my_player = config.get("app", {}).get("my_player_name", "")

    st.title("\U0001f3c0 NCAA Bracket Analysis")

    # AI headline if available
    headline = ctx.get_ai_headline()
    if headline:
        st.markdown(f"### *{headline}*")

    # Tournament status
    total = len(ctx.tournament.slots)
    completed = ctx.results.completed_count()
    remaining = total - completed

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Games Played", completed)
    with col2:
        st.metric("Games Remaining", remaining)
    with col3:
        current = ctx.current_round()
        st.metric("Current Round", ctx.round_name(current) if current > 0 else "Pre-Tournament")
    with col4:
        st.metric("Players", len(ctx.entries))

    # --- Standings table ---
    st.subheader("Standings")

    sr = ctx.scenario_results
    total_scenarios = sr.total_scenarios if sr else 0

    max_possibles = {
        name: scored.max_possible
        for name, scored in ctx.scored_entries.items()
    }

    rows = []
    df = ctx.leaderboard.copy()
    # Recompute rank with proper tie handling (min rank = dense rank by total then max possible)
    df = df.sort_values(["Total", "Max Possible"], ascending=[False, False]).reset_index(drop=True)
    df["Rank"] = df["Total"].rank(method="min", ascending=False).astype(int)

    for _, lb_row in df.iterrows():
        name = lb_row["Player"]
        scored = ctx.scored_entries[name]
        entry = ctx.get_entry(name)

        # Win probability
        win_pct = None
        is_elim = False
        if sr and total_scenarios > 0:
            wins = sr.win_counts.get(name, 0)
            win_pct = wins / total_scenarios * 100
            is_elim = sr.is_eliminated.get(name, False)

        # Alive teams count (pending picks whose team is still in)
        alive_count = 0
        if entry:
            for slot_id in scored.pending_picks:
                picked = entry.picks.get(slot_id)
                if picked and ctx.is_alive(picked):
                    alive_count += 1

        # Clinch check: my min > every other player's max possible
        others_max = [mp for n, mp in max_possibles.items() if n != name]
        clinched = bool(others_max and scored.total_points > max(others_max))

        label = name
        if my_player and name == my_player:
            label = f"**{name}**"

        rows.append({
            "Rank": int(lb_row["Rank"]),
            "Player": label,
            "Score": scored.total_points,
            "Max Possible": scored.max_possible,
            "Win %": f"{win_pct:.0f}%" if win_pct is not None else "—",
            "Alive Teams": alive_count,
            "Status": "Clinched" if clinched else ("Eliminated" if is_elim else ""),
        })

    import pandas as pd
    table_df = pd.DataFrame(rows)
    st.dataframe(table_df, use_container_width=True, hide_index=True)

    # Badges for clinched / eliminated players
    clinched_players = [r["Player"].strip("*") for r in rows if r["Status"] == "Clinched"]
    eliminated_players = [r["Player"].strip("*") for r in rows if r["Status"] == "Eliminated"]
    if clinched_players:
        st.success(f"Clinched: {', '.join(clinched_players)}")
    if eliminated_players:
        st.warning(f"Eliminated from contention: {', '.join(eliminated_players)}")

    # Data freshness signal
    rel = _relative_time(ctx.results.last_updated)
    age_hours = 0.0
    try:
        dt = datetime.fromisoformat(ctx.results.last_updated.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        pass

    if age_hours > 6:
        st.warning(f"Data may be stale — last updated {rel}. Use Refresh Data to reload.")
    else:
        st.caption(f"Last updated {rel}")

    # AI stories if available
    stories = ctx.get_ai_stories()
    if stories:
        st.subheader("Headlines")
        for story in stories[:3]:
            with st.container():
                st.markdown(f"**{story.get('title', '')}**")
                st.markdown(story.get("body", ""))
                st.divider()

    # AI recap with copy button
    recap = ctx.get_ai_recap()
    if recap:
        st.subheader("Group Chat Recap")
        st.code(recap, language=None)

    # Plugin summaries
    summaries = []
    for plugin in plugins:
        if plugin.summarize:
            summary = plugin.summarize(ctx)
            if summary:
                summaries.append((plugin.icon, plugin.title, summary))

    if summaries:
        st.subheader("Quick Takes")
        for icon, title, summary in summaries:
            st.markdown(f"{icon} **{title}**: {summary}")


if __name__ == "__main__":
    main()
