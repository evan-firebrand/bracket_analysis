"""Ask Claude — dedicated chat tab for freeform questions about the pool."""
from __future__ import annotations

import streamlit as st

from core.context import AnalysisContext

TITLE = "Ask Claude"
DESCRIPTION = "Ask freeform questions about brackets, players, scenarios, and odds"
CATEGORY = "ai"
ORDER = 10
ICON = "\U0001f4ac"  # speech balloon

# Session state key for chat history (one history per Streamlit session)
_HISTORY_KEY = "ask_claude_history"


def _get_history() -> list[dict]:
    if _HISTORY_KEY not in st.session_state:
        st.session_state[_HISTORY_KEY] = []
    return st.session_state[_HISTORY_KEY]


def _reset_history() -> None:
    st.session_state[_HISTORY_KEY] = []


def render(ctx: AnalysisContext):
    st.header(f"{ICON} {TITLE}")

    viewer = st.session_state.get("viewing_player")
    if viewer:
        st.caption(
            f"Viewing as: **{viewer}** — Claude personalizes answers to your bracket."
        )
    else:
        st.caption("Pick a player in the sidebar to personalize answers to your bracket.")

    # Reset button — top right of chat area
    cols = st.columns([6, 1])
    with cols[1]:
        if st.button("Clear", help="Reset conversation"):
            _reset_history()
            st.rerun()

    # Render existing history
    history = _get_history()
    for turn in history:
        with st.chat_message(turn["role"]):
            st.markdown(turn["content"])

    # Chat input at the bottom
    question = st.chat_input("Ask anything about the pool...")
    if not question:
        return

    # Append user turn and render it immediately
    history.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)

    # Stream the assistant response.
    # ctx.answer_question internally appends the new user turn to the messages it
    # passes to the agent, so we hand it the history WITHOUT the just-appended turn
    # to avoid duplication.
    prior_history = history[:-1]
    with st.chat_message("assistant"):
        full_response = st.write_stream(
            ctx.answer_question(question, viewer=viewer, history=prior_history)
        )

    # Persist the assistant's full response into history
    if isinstance(full_response, str) and full_response:
        history.append({"role": "assistant", "content": full_response})
    elif full_response:
        # write_stream may return a list of chunks; join them
        history.append(
            {"role": "assistant", "content": "".join(str(c) for c in full_response)}
        )


def summarize(ctx: AnalysisContext) -> str | None:
    """No home-screen quick-take for chat."""
    return None
