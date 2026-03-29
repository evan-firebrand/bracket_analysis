"""Fetch Vegas odds (DraftKings lines) from ESPN using Claude computer use."""

from src.agent import run_agent, extract_json_from_response
from src.browser import BrowserSession
from src.models import odds_prompt_schema


def fetch_odds(
    odds_url: str,
    browser: BrowserSession,
    model: str = None,
) -> list | None:
    """Fetch DraftKings betting lines from ESPN scoreboard.

    Args:
        odds_url: URL to the ESPN NCAA tournament scoreboard (shows odds).
        browser: An active BrowserSession.
        model: Optional model override.

    Returns:
        List of odds dicts, or None if extraction failed.
    """
    schema = odds_prompt_schema()

    prompt = f"""You are looking at the ESPN NCAA Men's Basketball Tournament scoreboard.

Your task:
1. Look at all upcoming and in-progress tournament games shown on this page.
2. For each game, find the betting odds/lines displayed (DraftKings or ESPN BET).
   These typically appear near each game as point spreads, moneylines, and over/unders.
3. Scroll through to find all games with available odds.

Record each game's odds in this JSON format:
{schema}

Return your results as a JSON array of odds objects.

Important:
- Include odds for ALL games that have betting lines displayed.
- The spread is from team1's perspective (negative means team1 is favored).
- Moneyline values are American odds format (e.g., -250 for favorite, +210 for underdog).
- If a particular odds field is not visible for a game, use null for that field.
- Scroll down to see all games if they don't fit on one screen.
- If you need to click on a game to see detailed odds, do so.
- Output ONLY valid JSON. No other text before or after the JSON array.
- Start with [ and end with ].
"""

    kwargs = {"task_prompt": prompt, "start_url": odds_url, "browser": browser}
    if model:
        kwargs["model"] = model

    raw_response = run_agent(**kwargs)
    data = extract_json_from_response(raw_response)

    if data is None:
        print(f"Warning: Could not parse JSON from agent response.")
        print(f"Raw response (first 500 chars): {raw_response[:500]}")
        return None

    return data
