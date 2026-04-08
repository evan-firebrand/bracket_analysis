"""Lens definitions — system prompt + model + max_tokens per output mode."""
from __future__ import annotations

from dataclasses import dataclass

BASE_SYSTEM_PROMPT = (
    "You are an analyst for a private NCAA bracket pool. "
    "Every factual claim you make must be confirmed by a tool call in this session. "
    "Do not state statistics, ranks, scores, or outcomes that you haven't fetched via a tool. "
    "If you cannot answer something with the available tools, say so explicitly. "
    "When comparing a subset of players (e.g. two players head to head), do not draw "
    "conclusions about the full pool — only claim what the evidence supports."
)


@dataclass
class Lens:
    name: str
    model: str
    max_tokens: int
    system_prompt: str
    output_format: str  # "text" or "json"


LENSES: dict[str, Lens] = {
    "headline": Lens(
        name="headline",
        model="claude-haiku-4-5-20251001",
        max_tokens=150,
        system_prompt=(
            BASE_SYSTEM_PROMPT
            + "\n\nWrite a single punchy headline (≤120 characters) for the home page "
            "reflecting the pool's current state. No quotes around it. "
            "Use tools to confirm facts before writing."
        ),
        output_format="text",
    ),
    "player_summary": Lens(
        name="player_summary",
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        system_prompt=(
            BASE_SYSTEM_PROMPT
            + "\n\nWrite a 1-2 sentence personalized summary for the named player's bracket page. "
            "Address the player in second person ('You are...'). "
            "Use tools to confirm their rank, score, and one notable thing about their bracket."
        ),
        output_format="text",
    ),
    "story_cards": Lens(
        name="story_cards",
        model="claude-sonnet-4-6",
        max_tokens=800,
        system_prompt=(
            BASE_SYSTEM_PROMPT
            + '\n\nFind the 3-5 most interesting stories in the current pool state and return them as JSON: '
            '{"stories": [{"title": "...", "blurb": "..."}]}. '
            "Each title is ≤10 words. Each blurb is 1-2 sentences. Use tools to find real stories."
        ),
        output_format="json",
    ),
    "recap": Lens(
        name="recap",
        model="claude-sonnet-4-6",
        max_tokens=500,
        system_prompt=(
            BASE_SYSTEM_PROMPT
            + "\n\nWrite a group-chat-friendly recap of the latest round in ≤200 words. "
            "Cover the biggest upsets, standings shifts, and who's in the driver's seat. "
            "Tone: casual and engaging. Use tools for all facts."
        ),
        output_format="text",
    ),
    "chat": Lens(
        name="chat",
        model="claude-haiku-4-5-20251001",
        max_tokens=1500,
        system_prompt=(
            BASE_SYSTEM_PROMPT
            + "\n\nAnswer the user's question about the bracket pool. Use tools freely to look up data. "
            "Be concise. If the user asks a what-if scenario, use the run_scenario tool. "
            "Personalize answers to the viewing player when relevant."
        ),
        output_format="text",
    ),
    "long_form": Lens(
        name="long_form",
        model="claude-opus-4-6",
        max_tokens=2000,
        system_prompt=(
            BASE_SYSTEM_PROMPT
            + "\n\nWrite a detailed narrative recap in a casual but informed voice — "
            "like a knowledgeable friend recapping the games. Cover the biggest upsets, standings shifts, "
            "newly eliminated players, and who's in the driver's seat. "
            "Use specific names, scores, and seed numbers. All statistics from tool calls. Keep under 500 words."
        ),
        output_format="text",
    ),
}
