"""Fetch NCAA tournament game results from ESPN using Claude computer use."""

from src.agent import run_agent, extract_json_from_response
from src.browser import BrowserSession
from src.models import game_result_prompt_schema


def fetch_results(
    results_url: str,
    browser: BrowserSession,
    model: str = None,
) -> list | None:
    """Fetch current NCAA tournament game results from ESPN scoreboard.

    Args:
        results_url: URL to the ESPN NCAA tournament scoreboard.
        browser: An active BrowserSession.
        model: Optional model override.

    Returns:
        List of game result dicts, or None if extraction failed.
    """
    schema = game_result_prompt_schema()

    prompt = f"""You are looking at the ESPN NCAA Men's Basketball Tournament scoreboard.

Your task:
1. Look at all the games shown on this page.
2. Scroll through to find all tournament games across all rounds.
3. For each game that has a final score or is in progress, extract the result.

Record each game in this JSON format:
{schema}

Return your results as a JSON array of game objects.

Important:
- Include all completed games (status "final") and any in-progress games.
- Skip games that haven't started yet (or mark them as "scheduled" with scores of 0).
- Scroll down to see all games if they don't fit on one screen.
- If there are multiple days/rounds, navigate to see all of them.
- Output ONLY valid JSON. No other text before or after the JSON array.
- Start with [ and end with ].
"""

    kwargs = {"task_prompt": prompt, "start_url": results_url, "browser": browser}
    if model:
        kwargs["model"] = model

    raw_response = run_agent(**kwargs)
    data = extract_json_from_response(raw_response)

    if data is None:
        print(f"Warning: Could not parse JSON from agent response.")
        print(f"Raw response (first 500 chars): {raw_response[:500]}")
        return None

    return data
