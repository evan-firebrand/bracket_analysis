"""Tests for the live AI layer wired into AnalysisContext.

All Anthropic calls are mocked. No network. No real API key needed.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.ai.evidence import EvidencePacket
from core.context import AnalysisContext


@pytest.fixture
def ctx() -> AnalysisContext:
    """Real AnalysisContext over the repo's data fixtures."""
    return AnalysisContext(data_dir="data")


# --- data_hash ---

class TestDataHash:
    def test_computed_once_per_instance(self, ctx: AnalysisContext) -> None:
        with patch("core.context.compute_data_hash") as mock_hash:
            mock_hash.return_value = "deadbeef"
            # Reset cached value so the patch takes effect
            ctx._data_hash_cached = None
            first = ctx.data_hash
            second = ctx.data_hash
            third = ctx.data_hash
            assert first == "deadbeef"
            assert second == "deadbeef"
            assert third == "deadbeef"
            assert mock_hash.call_count == 1


# --- configure_ai ---

class TestConfigureAi:
    def test_cache_disabled_means_no_cache_instance(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({"enabled": True, "cache_enabled": False, "cache_dir": str(tmp_path / "cache")})
        assert ctx._content_cache is None

    def test_cache_enabled_creates_cache(self, ctx: AnalysisContext, tmp_path) -> None:
        cache_dir = tmp_path / "cache"
        ctx.configure_ai({"enabled": True, "cache_enabled": True, "cache_dir": str(cache_dir)})
        assert ctx._content_cache is not None
        assert ctx._content_cache.cache_dir == cache_dir
        assert cache_dir.exists()

    def test_disabled_flag_disables_ai(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({"enabled": False, "cache_dir": str(tmp_path / "cache")})
        assert ctx._ai_enabled is False

    def test_audit_dir_set(self, ctx: AnalysisContext, tmp_path) -> None:
        audit = tmp_path / "audit"
        ctx.configure_ai({"enabled": True, "audit_dir": str(audit), "cache_dir": str(tmp_path / "cache")})
        assert ctx._audit_dir == audit

    def test_none_config_safe(self, ctx: AnalysisContext) -> None:
        ctx.configure_ai(None)
        # Default: enabled if anthropic available
        assert isinstance(ctx._ai_enabled, bool)


# --- generate_copy ---

class TestGenerateCopy:
    def test_returns_none_when_disabled(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({"enabled": False, "cache_dir": str(tmp_path / "cache")})
        result = ctx.generate_copy("headline", "home", viewer="Alice")
        assert result is None

    def test_returns_none_when_agent_raises_unavailable(
        self, ctx: AnalysisContext, tmp_path
    ) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": False,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })
        with patch("core.context._ai_agent") as mock_agent:
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.generate.side_effect = AIUnavailableError("no key")
            result = ctx.generate_copy("headline", "home", viewer="Alice")
            assert result is None

    def test_returns_none_on_generic_exception(
        self, ctx: AnalysisContext, tmp_path
    ) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": False,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })
        with patch("core.context._ai_agent") as mock_agent:
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.generate.side_effect = RuntimeError("boom")
            result = ctx.generate_copy("headline", "home", viewer="Alice")
            assert result is None

    def test_cache_hit_skips_agent(self, ctx: AnalysisContext, tmp_path) -> None:
        cache_dir = tmp_path / "cache"
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": True,
            "cache_dir": str(cache_dir),
            "audit_dir": str(tmp_path / "audit"),
        })
        # Seed the cache with a known entry
        ctx._content_cache.put(
            "headline",
            "Alice",
            ctx.data_hash,
            "cached headline text",
            evidence={"tool_calls": []},
        )
        with patch("core.context._ai_agent") as mock_agent:
            mock_agent.generate = MagicMock()
            result = ctx.generate_copy("headline", "home", viewer="Alice")
            assert result == "cached headline text"
            mock_agent.generate.assert_not_called()

    def test_cache_miss_then_hit(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": True,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })
        packet = EvidencePacket(lens="headline", viewer="Alice")
        packet.record("get_leaderboard", {}, '{"leader": "Alice"}')

        with patch("core.context._ai_agent") as mock_agent, \
             patch("core.context.log_audit") as mock_audit:
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.generate.return_value = ("hello world", packet)

            # First call: miss → calls agent
            first = ctx.generate_copy("headline", "home", viewer="Alice")
            assert first == "hello world"
            assert mock_agent.generate.call_count == 1
            assert mock_audit.call_count == 1

            # Second call: hit → does not call agent
            second = ctx.generate_copy("headline", "home", viewer="Alice")
            assert second == "hello world"
            assert mock_agent.generate.call_count == 1  # still 1


# --- answer_question ---

class TestAnswerQuestion:
    def test_streams_tokens_when_available(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": False,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })

        def fake_stream(lens, messages, ctx_arg, evidence=None):
            yield "hello "
            yield "world"

        with patch("core.context._ai_agent") as mock_agent, \
             patch("core.context.log_audit"):
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.stream.side_effect = fake_stream
            tokens = list(ctx.answer_question("who is winning?", viewer="Alice"))
            assert tokens == ["hello ", "world"]

    def test_yields_fallback_when_disabled(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({"enabled": False, "cache_dir": str(tmp_path / "cache")})
        tokens = list(ctx.answer_question("who is winning?", viewer="Alice"))
        assert len(tokens) == 1
        assert isinstance(tokens[0], str)
        assert tokens[0]  # non-empty

    def test_does_not_write_to_cache(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": True,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })

        def fake_stream(lens, messages, ctx_arg, evidence=None):
            yield "answer"

        # Wrap the cache.put method to monitor calls
        original_put = ctx._content_cache.put
        put_calls = []

        def tracked_put(*args, **kwargs):
            put_calls.append((args, kwargs))
            return original_put(*args, **kwargs)

        ctx._content_cache.put = tracked_put

        with patch("core.context._ai_agent") as mock_agent, \
             patch("core.context.log_audit"):
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.stream.side_effect = fake_stream
            list(ctx.answer_question("hi", viewer="Alice"))

        assert put_calls == []  # chat must never touch the cache

    def test_handles_unavailable_mid_stream(self, ctx: AnalysisContext, tmp_path) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": False,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })

        with patch("core.context._ai_agent") as mock_agent:
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.stream.side_effect = AIUnavailableError("no key")
            tokens = list(ctx.answer_question("hi", viewer="Alice"))
            assert len(tokens) == 1
            assert tokens[0]  # non-empty fallback

    def test_handles_generic_exception_mid_stream(
        self, ctx: AnalysisContext, tmp_path
    ) -> None:
        ctx.configure_ai({
            "enabled": True,
            "cache_enabled": False,
            "cache_dir": str(tmp_path / "cache"),
            "audit_dir": str(tmp_path / "audit"),
        })
        with patch("core.context._ai_agent") as mock_agent:
            from core.ai.agent import AIUnavailableError
            mock_agent.AIUnavailableError = AIUnavailableError
            mock_agent.stream.side_effect = RuntimeError("kaboom")
            tokens = list(ctx.answer_question("hi", viewer="Alice"))
            # Should not raise; should yield an error line
            assert len(tokens) == 1
            assert "Error" in tokens[0] or "kaboom" in tokens[0]
