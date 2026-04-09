"""Tests for the plugin auto-discovery system."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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


class TestAskClaudePlugin:
    def test_plugin_discovered(self):
        plugins = discover_plugins()
        names = [p.name for p in plugins]
        assert "ask_claude" in names

        ask_claude = next(p for p in plugins if p.name == "ask_claude")
        assert ask_claude.title == "Ask Claude"
        assert ask_claude.category == "ai"
        assert ask_claude.icon  # non-empty
        assert ask_claude.order > 0
        assert callable(ask_claude.render)

    def test_history_helpers(self):
        from analyses import ask_claude

        # Replace st.session_state with a fresh dict-like
        fake_state = {}
        with patch.object(ask_claude.st, "session_state", fake_state):
            history = ask_claude._get_history()
            assert history == []
            history.append({"role": "user", "content": "hi"})
            assert ask_claude._get_history() == [{"role": "user", "content": "hi"}]
            ask_claude._reset_history()
            assert ask_claude._get_history() == []

    def test_render_streams_through_answer_question(self):
        """Plugin must call ctx.answer_question with the new question + prior history."""
        from analyses import ask_claude

        # Simulate a session with one prior turn already in history
        fake_state = {
            "viewing_player": "Alice",
            "ask_claude_history": [
                {"role": "user", "content": "earlier question"},
                {"role": "assistant", "content": "earlier answer"},
            ],
        }

        # Mock the user submitting a new question via chat_input
        ctx = MagicMock()
        ctx.answer_question = MagicMock(return_value=iter(["streamed ", "answer"]))

        with patch.object(ask_claude.st, "session_state", fake_state), \
             patch.object(ask_claude.st, "chat_input", return_value="new question"), \
             patch.object(ask_claude.st, "chat_message"), \
             patch.object(ask_claude.st, "write_stream", return_value="streamed answer"), \
             patch.object(ask_claude.st, "header"), \
             patch.object(ask_claude.st, "caption"), \
             patch.object(ask_claude.st, "columns", return_value=[MagicMock(), MagicMock()]), \
             patch.object(ask_claude.st, "button", return_value=False), \
             patch.object(ask_claude.st, "markdown"):
            ask_claude.render(ctx)

        # Confirm answer_question was called with viewer + prior history (NOT including
        # the just-appended user turn)
        assert ctx.answer_question.call_count == 1
        call_args = ctx.answer_question.call_args
        assert call_args.args[0] == "new question"
        assert call_args.kwargs["viewer"] == "Alice"
        # prior_history should be the original 2 turns, not 3
        assert len(call_args.kwargs["history"]) == 2
        assert call_args.kwargs["history"][0]["content"] == "earlier question"

        # The new user turn AND the assistant response should now be in history
        assert len(fake_state["ask_claude_history"]) == 4
        assert fake_state["ask_claude_history"][-2] == {"role": "user", "content": "new question"}
        assert fake_state["ask_claude_history"][-1] == {"role": "assistant", "content": "streamed answer"}
