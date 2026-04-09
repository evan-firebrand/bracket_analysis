"""Anthropic client singleton."""
from __future__ import annotations

_client = None


def get_client():
    """Return the Anthropic client, or None if no API key is available."""
    global _client
    if _client is not None:
        return _client

    api_key = _load_api_key()
    if not api_key:
        return None

    import anthropic
    _client = anthropic.Anthropic(api_key=api_key)
    return _client


def _load_api_key() -> str | None:
    """Try st.secrets first, then env var."""
    # Try Streamlit secrets (Streamlit Cloud deployment)
    try:
        import streamlit as st
        key = st.secrets.get("ANTHROPIC_API_KEY")
        if key:
            return key
    except Exception:
        pass

    # Try environment variable (local dev)
    import os
    return os.environ.get("ANTHROPIC_API_KEY") or None
