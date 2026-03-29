"""Fetch Vegas odds from ESPN using Claude computer use.

Output format matches docs/DATA_CONTRACT.md:
- Team-level round advancement probabilities (0.0 to 1.0)
- NOT per-game spreads or moneylines
- Only alive (non-eliminated) teams included
"""

from src.agent import extract_json_from_response, run_agent
from src.browser import BrowserSession
from src.models import odds_prompt_schema
from src.storage import load_tournament


def fetch_odds(
    odds_url: str,
    browser: BrowserSession,
    model: str = None,
    data_dir: str = "data",
) -> dict | None:
    """Fetch team-level tournament advancement odds from ESPN.

    The odds represent each team's probability of reaching each round,
    sourced from DraftKings/ESPN BET lines or BPI projections.

    Args:
        odds_url: URL to ESPN odds/BPI tournament projections page.
        browser: An active BrowserSession.
        model: Optional model override.
        data_dir: Path to data directory (to load tournament.json for context).

    Returns:
        Dict matching the odds.json schema, or None if extraction failed.
    """
    schema = odds_prompt_schema()

    # Load tournament structure if available for team slug context
    tournament = load_tournament(data_dir)
    tournament_context = ""
    if tournament:
        teams = tournament.get("teams", {})
        team_list = ", ".join(f"{slug} ({info['name']})" for slug, info in list(teams.items())[:10])
        tournament_context = f"""
The tournament structure has already been defined. Here are some of the team slugs in use:
{team_list}, ... etc.

Use these EXACT team slugs in your output. Team slugs are lowercase with underscores.
"""

    prompt = f"""You are looking at ESPN's NCAA tournament page.

Your task:
1. Find the tournament odds, BPI projections, or championship probability data.
   This might be on a "BPI" tab, "Odds" section, "Tournament Forecast", or similar.
   If not visible on the current page, try navigating to ESPN's tournament forecast/BPI page.
2. For each team still alive in the tournament, extract their probability of advancing
   to each round and winning the championship.

{tournament_context}

Return your results in this exact JSON format:
{schema}

Important:
- Probabilities must be between 0.0 and 1.0 (NOT percentages — convert 15% to 0.15).
- Probabilities are cumulative: r2 >= r3 >= r4 >= ff >= championship >= winner.
- Only include teams still alive in the tournament (not eliminated teams).
- Use team slugs (lowercase, underscores): duke, north_carolina, houston, etc.
- If exact round-by-round probabilities aren't available, extract what you can and
  set unavailable fields to null.
- Scroll as needed to see all teams.
- Output ONLY valid JSON. No other text before or after.
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
