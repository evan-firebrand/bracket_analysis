"""NCAA Bracket Analysis — Streamlit entry point."""

from __future__ import annotations

import streamlit as st

from analyses import CATEGORY_LABELS, discover_plugins, get_plugins_by_category
from core.context import AnalysisContext

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


def _render_home(ctx: AnalysisContext, plugins):
    """Render the home dashboard."""
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

    # Quick leaderboard (top 10)
    st.subheader("Leaderboard")
    if len(ctx.leaderboard) > 0:
        top_n = min(10, len(ctx.leaderboard))
        display = ctx.leaderboard.head(top_n)[["Rank", "Player", "Total", "Max Possible", "Correct"]]
        st.dataframe(display, use_container_width=True, hide_index=True)

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
