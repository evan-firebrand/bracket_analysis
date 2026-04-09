"""Tests for the Claude agent loop (all API calls mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from core.ai.agent import AIUnavailableError, _build_user_message, generate, stream
from core.ai.evidence import EvidencePacket


def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(name: str, input_args: dict, block_id: str = "tu_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_args
    block.id = block_id
    return block


def _make_response(content, stop_reason: str):
    response = MagicMock()
    response.content = content
    response.stop_reason = stop_reason
    return response


@pytest.fixture
def mock_ctx():
    """Minimal AnalysisContext mock."""
    ctx = MagicMock()
    return ctx


class TestBuildUserMessage:
    def test_includes_viewer(self):
        msg = _build_user_message("headline", {"viewer": "Alice"})
        assert "Alice" in msg

    def test_includes_page(self):
        msg = _build_user_message("headline", {"page": "leaderboard"})
        assert "leaderboard" in msg

    def test_empty_context(self):
        msg = _build_user_message("headline", {})
        assert isinstance(msg, str)
        assert len(msg) > 0


class TestGenerate:
    def test_pure_text_response(self, mock_ctx):
        text_response = _make_response([_make_text_block("Alice leads the pool!")], "end_turn")

        with patch("core.ai.agent.get_client") as mock_get_client, \
             patch("core.ai.agent.get_tool_schemas", return_value=[]):
            mock_client = MagicMock()
            mock_client.messages.create.return_value = text_response
            mock_get_client.return_value = mock_client

            text, evidence = generate("headline", {"viewer": "Alice"}, mock_ctx)

        assert text == "Alice leads the pool!"
        assert mock_client.messages.create.call_count == 1
        assert isinstance(evidence, EvidencePacket)
        assert evidence.lens == "headline"
        assert evidence.viewer == "Alice"
        assert evidence.tool_calls == []
        assert evidence.final_output == "Alice leads the pool!"

    def test_tool_use_then_text(self, mock_ctx):
        tool_block = _make_tool_use_block("get_pool_state", {})
        tool_response = _make_response([tool_block], "tool_use")
        text_response = _make_response([_make_text_block("Round 2 is underway!")], "end_turn")

        with patch("core.ai.agent.get_client") as mock_get_client, \
             patch("core.ai.agent.get_tool_schemas", return_value=[]), \
             patch("core.ai.agent.execute_tool", return_value='{"round": 2}') as mock_exec:
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [tool_response, text_response]
            mock_get_client.return_value = mock_client

            text, evidence = generate("headline", {}, mock_ctx)

        assert text == "Round 2 is underway!"
        assert mock_client.messages.create.call_count == 2
        mock_exec.assert_called_once_with("get_pool_state", {}, mock_ctx)
        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].name == "get_pool_state"
        assert evidence.tool_calls[0].result_summary == '{"round": 2}'

    def test_multiple_tool_rounds(self, mock_ctx):
        tool_block1 = _make_tool_use_block("get_pool_state", {}, "tu_1")
        tool_block2 = _make_tool_use_block("get_leaderboard", {"limit": 3}, "tu_2")
        tool_response1 = _make_response([tool_block1], "tool_use")
        tool_response2 = _make_response([tool_block2], "tool_use")
        text_response = _make_response([_make_text_block("Final answer")], "end_turn")

        with patch("core.ai.agent.get_client") as mock_get_client, \
             patch("core.ai.agent.get_tool_schemas", return_value=[]), \
             patch("core.ai.agent.execute_tool", return_value='{}'):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [tool_response1, tool_response2, text_response]
            mock_get_client.return_value = mock_client

            text, evidence = generate("headline", {}, mock_ctx)

        assert text == "Final answer"
        assert mock_client.messages.create.call_count == 3
        assert [tc.name for tc in evidence.tool_calls] == ["get_pool_state", "get_leaderboard"]
        assert evidence.tool_calls[1].args == {"limit": 3}

    def test_raises_when_no_client(self, mock_ctx):
        with patch("core.ai.agent.get_client", return_value=None):
            with pytest.raises(AIUnavailableError):
                generate("headline", {}, mock_ctx)


class TestStream:
    def test_yields_tokens(self, mock_ctx):
        text_response = _make_response([_make_text_block("some text")], "end_turn")

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["hello ", "world"])

        with patch("core.ai.agent.get_client") as mock_get_client, \
             patch("core.ai.agent.get_tool_schemas", return_value=[]):
            mock_client = MagicMock()
            # First call: non-streaming check for tool_use
            mock_client.messages.create.return_value = text_response
            # Streaming call for final text
            mock_client.messages.stream.return_value = mock_stream_ctx
            mock_get_client.return_value = mock_client

            tokens = list(stream("chat", [{"role": "user", "content": "hello"}], mock_ctx))

        assert tokens == ["hello ", "world"]

    def test_records_evidence_when_provided(self, mock_ctx):
        tool_block = _make_tool_use_block("get_pool_state", {})
        tool_response = _make_response([tool_block], "tool_use")
        text_response = _make_response([_make_text_block("done")], "end_turn")

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
        mock_stream_ctx.__exit__ = MagicMock(return_value=False)
        mock_stream_ctx.text_stream = iter(["Al", "ice ", "wins"])

        with patch("core.ai.agent.get_client") as mock_get_client, \
             patch("core.ai.agent.get_tool_schemas", return_value=[]), \
             patch("core.ai.agent.execute_tool", return_value='{"round": 2}'):
            mock_client = MagicMock()
            mock_client.messages.create.side_effect = [tool_response, text_response]
            mock_client.messages.stream.return_value = mock_stream_ctx
            mock_get_client.return_value = mock_client

            evidence = EvidencePacket(lens="chat", viewer="Alice")
            tokens = list(stream("chat", [{"role": "user", "content": "hi"}], mock_ctx, evidence))

        assert tokens == ["Al", "ice ", "wins"]
        assert len(evidence.tool_calls) == 1
        assert evidence.tool_calls[0].name == "get_pool_state"
        assert evidence.final_output == "Alice wins"

    def test_raises_when_no_client(self, mock_ctx):
        with patch("core.ai.agent.get_client", return_value=None):
            with pytest.raises(AIUnavailableError):
                # stream() is a generator — need to advance it to trigger the error
                list(stream("chat", [], mock_ctx))
