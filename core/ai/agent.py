"""Claude agent loop — tool-use iteration for single-turn and streaming."""
from __future__ import annotations

from typing import Generator

from core.ai.client import get_client
from core.ai.evidence import EvidencePacket
from core.ai.lenses import LENSES
from core.ai.tools import execute_tool, get_tool_schemas


class AIUnavailableError(Exception):
    """Raised when the Anthropic client is not available (missing API key)."""


def _build_user_message(lens_name: str, context_dict: dict) -> str:
    """Build the initial user message for page copy generation."""
    parts = []
    if context_dict.get("viewer"):
        parts.append(f"The user viewing this page is: {context_dict['viewer']}")
    if context_dict.get("page"):
        parts.append(f"Current page: {context_dict['page']}")
    # Any extra context fields
    for k, v in context_dict.items():
        if k not in ("viewer", "page"):
            parts.append(f"{k}: {v}")
    parts.append("Please generate the content for this page now.")
    return "\n".join(parts)


def _execute_tool_uses(response_content, ctx, evidence: EvidencePacket | None = None) -> list[dict]:
    """Execute all tool_use blocks in a response and return tool_result list.

    If an evidence packet is supplied, each tool call is recorded into it.
    """
    results = []
    for block in response_content:
        if block.type == "tool_use":
            result_json = execute_tool(block.name, block.input, ctx)
            if evidence is not None:
                evidence.record(block.name, dict(block.input), result_json)
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_json,
            })
    return results


def _extract_text(response_content) -> str:
    """Extract text from response content blocks."""
    parts = []
    for block in response_content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "".join(parts).strip()


def generate(lens_name: str, context_dict: dict, ctx) -> tuple[str, EvidencePacket]:
    """
    Single-turn generation for page copy.

    Runs the full tool-use loop and returns ``(final_text, evidence_packet)``.
    The evidence packet captures every tool call made during the run and is
    suitable for "Show sources" UI, scope-block auto-generation, and audit
    logging.

    Raises AIUnavailableError if no API key is configured.
    """
    client = get_client()
    if client is None:
        raise AIUnavailableError("ANTHROPIC_API_KEY not set")

    lens = LENSES[lens_name]
    tools = get_tool_schemas()
    messages = [{"role": "user", "content": _build_user_message(lens_name, context_dict)}]
    evidence = EvidencePacket(lens=lens_name, viewer=context_dict.get("viewer"))

    while True:
        response = client.messages.create(
            model=lens.model,
            max_tokens=lens.max_tokens,
            system=lens.system_prompt,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = _execute_tool_uses(response.content, ctx, evidence)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        # stop_reason == "end_turn" or "max_tokens"
        text = _extract_text(response.content)
        evidence.final_output = text
        return text, evidence


def stream(
    lens_name: str,
    messages: list[dict],
    ctx,
    evidence: EvidencePacket | None = None,
) -> Generator[str, None, None]:
    """
    Multi-turn streaming for chat.

    Takes a conversation history (list of {role, content} dicts) and yields
    text tokens as they arrive. Tool calls are executed synchronously between
    streaming rounds; only the final text response is streamed.

    If ``evidence`` is provided, every tool call made during the run is
    recorded into it and the streamed tokens are also appended to
    ``evidence.final_output`` as they arrive. Callers can then inspect the
    packet after iteration completes (e.g. to show sources or audit the run).

    Raises AIUnavailableError if no API key is configured.
    """
    client = get_client()
    if client is None:
        raise AIUnavailableError("ANTHROPIC_API_KEY not set")

    lens = LENSES[lens_name]
    tools = get_tool_schemas()
    messages = list(messages)  # don't mutate caller's list

    if evidence is not None and evidence.final_output is None:
        evidence.final_output = ""

    while True:
        # Non-streaming for tool_use rounds (efficient for tool execution)
        response = client.messages.create(
            model=lens.model,
            max_tokens=lens.max_tokens,
            system=lens.system_prompt,
            tools=tools,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = _execute_tool_uses(response.content, ctx, evidence)
            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
            continue

        # Final text response — yield tokens
        # Re-run as streaming request for the final turn
        with client.messages.stream(
            model=lens.model,
            max_tokens=lens.max_tokens,
            system=lens.system_prompt,
            tools=tools,
            messages=messages,
        ) as s:
            for text in s.text_stream:
                if evidence is not None:
                    evidence.final_output = (evidence.final_output or "") + text
                yield text
        break
