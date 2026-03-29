"""Fetch bracket picks from ESPN using Claude computer use."""

from src.agent import run_agent, extract_json_from_response
from src.browser import BrowserSession
from src.models import bracket_pick_prompt_schema


def fetch_espn_bracket(
    group_url: str,
    target_member: str,
    browser: BrowserSession,
    model: str = None,
) -> dict | None:
    """Fetch a specific member's bracket from an ESPN group page.

    Args:
        group_url: URL to the ESPN Tournament Challenge group page.
        target_member: Name of the member whose bracket to fetch (e.g. "Rebecca").
        browser: An active BrowserSession.
        model: Optional model override.

    Returns:
        Dict with bracket data, or None if extraction failed.
    """
    schema = bracket_pick_prompt_schema()

    prompt = f"""You are looking at an ESPN Tournament Challenge group page.

Your task:
1. Find the member named "{target_member}" in the group standings/leaderboard.
2. Click on their bracket entry to view their full bracket.
3. Once you can see the bracket, extract ALL of their picks for every game in the tournament.
4. Scroll as needed to see all regions and rounds (Round of 64 through Championship).

For each game pick, record it in this JSON format:
{schema}

Return your results as a JSON object with this structure:
{{
    "member_name": "{target_member}",
    "bracket_name": "<name of the bracket entry if visible>",
    "picks": [
        <array of pick objects in the format above>
    ]
}}

Important:
- Include ALL 63 game picks (32 in Round 1, 16 in Round 2, 8 in Sweet 16, 4 in Elite 8, 2 in Final Four, 1 Championship).
- Make sure to scroll through all four regions plus the Final Four.
- Output ONLY valid JSON. No other text before or after the JSON.
"""

    kwargs = {"task_prompt": prompt, "start_url": group_url, "browser": browser}
    if model:
        kwargs["model"] = model

    raw_response = run_agent(**kwargs)
    data = extract_json_from_response(raw_response)

    if data is None:
        print(f"Warning: Could not parse JSON from agent response.")
        print(f"Raw response (first 500 chars): {raw_response[:500]}")
        return {"raw_response": raw_response}

    return data
