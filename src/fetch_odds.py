"""Fetch Vegas odds from DraftKings using Claude computer use.

Fetches per-game betting lines (spread, moneyline, over/under) for
upcoming NCAA tournament matchups from DraftKings Sportsbook.

Note: The data contract (docs/DATA_CONTRACT.md) specifies team-level
advancement probabilities. Moneylines can be converted to implied
probabilities downstream. This module fetches the raw lines.
"""

from src.agent import extract_json_from_response, run_agent
from src.browser import BrowserSession


def fetch_odds(
    odds_url: str,
    browser: BrowserSession,
    model: str = None,
    data_dir: str = "data",
) -> dict | None:
    """Fetch NCAA tournament game lines from DraftKings.

    Args:
        odds_url: URL to DraftKings NCAAB sportsbook page.
        browser: An active BrowserSession.
        model: Optional model override.
        data_dir: Path to data directory.

    Returns:
        Dict with odds data, or None if extraction failed.
    """

    prompt = """You are looking at the DraftKings Sportsbook NCAA basketball page.

Your task:
1. Find the NCAA tournament game lines (upcoming tournament matchups).
2. Look for March Madness, NCAA Tournament, or Elite 8 / Final Four games.
3. You may need to scroll or click on a "March Madness" or "NCAA Tournament" tab/filter.
4. For each upcoming tournament game, extract the betting lines.

For each game, record:
- team1: first team name (use lowercase with underscores: duke, michigan_st, etc.)
- team2: second team name
- spread: point spread for team1 (negative means favored, e.g. -6.5)
- moneyline_team1: American odds for team1 (e.g. -250)
- moneyline_team2: American odds for team2 (e.g. +210)
- over_under: total points line (e.g. 145.5)
- game_date: date if visible (YYYY-MM-DD format)

Return as JSON:
{
    "last_updated": "<current ISO 8601 timestamp>",
    "source": "DraftKings",
    "games": [
        {
            "team1": "<team_slug>",
            "team2": "<team_slug>",
            "spread": <float or null>,
            "moneyline_team1": <int or null>,
            "moneyline_team2": <int or null>,
            "over_under": <float or null>,
            "game_date": "<YYYY-MM-DD or null>"
        }
    ]
}

Team slug rules:
- Lowercase, underscores for spaces
- Examples: duke, uconn, arizona, purdue, illinois, iowa, michigan, tennessee

CRITICAL:
- Only include NCAA tournament games (Elite 8, Final Four, Championship).
- If a field is not visible, use null.
- Output ONLY valid JSON. No other text.
- If you can't find tournament game lines, look for "Featured" or "Popular"
  games which often highlight tournament matchups.
"""

    kwargs = {"task_prompt": prompt, "start_url": odds_url, "browser": browser}
    if model:
        kwargs["model"] = model

    raw_response = run_agent(**kwargs)
    data = extract_json_from_response(raw_response)

    if data is None:
        print("Warning: Could not parse JSON from agent response.")
        print(f"Raw response (first 500 chars): {raw_response[:500]}")
        return None

    return data
