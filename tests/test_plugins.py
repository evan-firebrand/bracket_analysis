"""Tests for the plugin auto-discovery system."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyses import CATEGORY_ORDER, discover_plugins, get_plugins_by_category
from core.context import AnalysisContext


class TestPluginDiscovery:
    def test_discovers_built_in_plugins(self):
        plugins = discover_plugins()
        names = [p.name for p in plugins]
        assert "leaderboard" in names
        assert "my_bracket" in names

    def test_plugins_have_required_attrs(self):
        plugins = discover_plugins()
        for plugin in plugins:
            assert plugin.title
            assert plugin.description
            assert plugin.category
            assert plugin.order > 0
            assert plugin.icon
            assert callable(plugin.render)

    def test_plugins_sorted_by_category_then_order(self):
        plugins = discover_plugins()
        # Standings should come before my_bracket
        standings_idx = next(
            i for i, p in enumerate(plugins) if p.category == "standings"
        )
        my_bracket_idx = next(
            i for i, p in enumerate(plugins) if p.category == "my_bracket"
        )
        assert standings_idx < my_bracket_idx

    def test_all_plugins_use_declared_category(self):
        plugins = discover_plugins()
        for plugin in plugins:
            assert plugin.category in CATEGORY_ORDER, (
                f"Plugin {plugin.name} uses undeclared category "
                f"{plugin.category!r}; allowed: {CATEGORY_ORDER}"
            )

    def test_group_by_category(self):
        plugins = discover_plugins()
        grouped = get_plugins_by_category(plugins)
        assert "standings" in grouped
        assert "my_bracket" in grouped
        assert len(grouped["standings"]) >= 1
        assert len(grouped["my_bracket"]) >= 1


class TestPluginAiCopyMigration:
    """Tests that the leaderboard / my_bracket plugins call ctx.generate_copy
    with the right (lens, page, viewer) tuple, and fall back to the static
    get_ai_* methods when generate_copy returns None.

    Plugin renders touch Streamlit widgets that error outside an actual
    Streamlit runtime, so we wrap each render() in try/except and assert
    against the mocks afterwards. We only need the AI call paths to fire
    before any Streamlit error.
    """

    def _make_ctx(self) -> AnalysisContext:
        return AnalysisContext(data_dir="data")

    def test_leaderboard_uses_generate_copy(self, monkeypatch):
        import analyses.leaderboard as leaderboard_mod

        ctx = self._make_ctx()
        mock_generate = MagicMock(return_value="AI HEADLINE")
        monkeypatch.setattr(ctx, "generate_copy", mock_generate)
        # Make sure static fallback would return something different so we
        # can be confident the live path won.
        monkeypatch.setattr(ctx, "get_ai_headline", lambda: "STATIC HEADLINE")

        # Provide a viewing_player in session state
        import streamlit as st
        st.session_state["viewing_player"] = "Alice"

        try:
            leaderboard_mod.render(ctx)
        except Exception:
            pass  # Streamlit widgets fail outside a runtime; ignore

        mock_generate.assert_called_once_with(
            "headline", "leaderboard", viewer="Alice"
        )

    def test_my_bracket_uses_generate_copy(self, monkeypatch):
        import analyses.my_bracket as my_bracket_mod

        ctx = self._make_ctx()
        # Pick a real player so the plugin proceeds past the selectbox.
        player = ctx.player_names()[0]

        mock_generate = MagicMock(return_value="AI SUMMARY")
        monkeypatch.setattr(ctx, "generate_copy", mock_generate)
        monkeypatch.setattr(
            ctx, "get_ai_player_summary", lambda name: "STATIC SUMMARY"
        )

        # Force the plugin's selectbox to return our chosen player by
        # patching streamlit.selectbox at module scope.
        import streamlit as st
        monkeypatch.setattr(st, "selectbox", lambda *a, **kw: player)

        try:
            my_bracket_mod.render(ctx)
        except Exception:
            pass

        # Viewer must be the *selected* player, not the session-state viewer.
        mock_generate.assert_any_call(
            "player_summary", "my_bracket", viewer=player
        )

    def test_leaderboard_falls_back_when_generate_copy_returns_none(
        self, monkeypatch
    ):
        import analyses.leaderboard as leaderboard_mod

        ctx = self._make_ctx()
        monkeypatch.setattr(ctx, "generate_copy", MagicMock(return_value=None))
        static_mock = MagicMock(return_value="STATIC")
        monkeypatch.setattr(ctx, "get_ai_headline", static_mock)

        captured: list[str] = []
        import streamlit as st

        def fake_markdown(text, *a, **kw):
            captured.append(text)

        monkeypatch.setattr(st, "markdown", fake_markdown)
        st.session_state["viewing_player"] = "Alice"

        try:
            leaderboard_mod.render(ctx)
        except Exception:
            pass

        static_mock.assert_called_once()
        # The first markdown call from the plugin is the italicized headline.
        assert any("STATIC" in t for t in captured), (
            f"expected STATIC headline to be rendered, got {captured!r}"
        )
