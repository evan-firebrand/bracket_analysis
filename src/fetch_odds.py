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
    """Fetch team-level tournament advancement odds from ESPN BPI.

    The odds represent each team's probability of reaching each round,
    sourced from ESPN's BPI (Basketball Power Index) tournament projections.

    Args:
        odds_url: URL to ESPN BPI tournament forecast page.
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

    prompt = f"""You are looking at ESPN's BPI (Basketball Power Index) tournament projections page.

This page should show each team's probability of advancing to each round of the NCAA tournament.
Look for a table or chart with columns like "Sweet 16 %", "Elite 8 %", "Final Four %", "Champion %".

Your task:
1. Find the tournament advancement probabilities table on this page.
2. If you don't see it immediately, look for tabs like "Tournament", "Forecast", "BPI",
   or "March Madness". You may need to click on a tab or link.
3. If this page doesn't have tournament projections, try navigating to:
   - ESPN's "Tournament Challenge" forecast page
   - ESPN's BPI page with a "Tournament" filter
4. For each team still alive, extract their advancement probabilities.

{tournament_context}

Return your results in this exact JSON format:
{schema}

CRITICAL rules:
- Probabilities must be between 0.0 and 1.0 (NOT percentages — convert 15% to 0.15).
- Probabilities are cumulative: r2 >= r3 >= r4 >= ff >= championship >= winner.
- Only include teams still alive in the tournament (not eliminated teams).
- Use team slugs (lowercase, underscores): duke, north_carolina, michigan_st, etc.
- If exact round-by-round probabilities aren't available, extract what IS available
  and set unavailable fields to null.
- If you can only find championship odds (e.g. from a futures/odds page), that's still
  useful — include it and set other round_probs to null.
- Scroll as needed to see all teams.
- Output ONLY valid JSON. No other text before or after.
- If you absolutely cannot find tournament advancement probabilities after thorough
  searching, return a JSON object with "error": "description of what you found instead".
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

    # Check for error response
    if isinstance(data, dict) and "error" in data:
        print(f"Agent could not find odds: {data['error']}")
        return None

    return data
