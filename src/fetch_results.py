"""Fetch NCAA tournament game results from ESPN using Claude computer use.

Output format matches docs/DATA_CONTRACT.md:
- Single results object keyed by slot_id
- Each result has winner, loser (team slugs), and score string
- Only completed games included
"""

from src.agent import extract_json_from_response, run_agent
from src.browser import BrowserSession
from src.models import results_prompt_schema
from src.storage import load_tournament


def fetch_results(
    results_url: str,
    browser: BrowserSession,
    model: str = None,
    data_dir: str = "data",
) -> dict | None:
    """Fetch current NCAA tournament game results from ESPN scoreboard.

    Args:
        results_url: URL to the ESPN NCAA tournament scoreboard.
        browser: An active BrowserSession.
        model: Optional model override.
        data_dir: Path to data directory (to load tournament.json for context).

    Returns:
        Dict matching the results.json schema, or None if extraction failed.
    """
    schema = results_prompt_schema()

    # Load tournament structure if available, to give Claude context on slot IDs
    tournament = load_tournament(data_dir)
    tournament_context = ""
    if tournament:
        teams = tournament.get("teams", {})
        team_list = ", ".join(f"{slug} ({info['name']})" for slug, info in list(teams.items())[:10])
        tournament_context = f"""
The tournament structure has already been defined. Here are some of the team slugs in use:
{team_list}, ... etc.

Use these EXACT team slugs in your output. Team slugs are lowercase with underscores
(e.g. duke, north_carolina, montana_st).

Slot IDs follow this pattern:
- Round 1: r1_{{region}}_{{highseed}}v{{lowseed}} (e.g. r1_east_1v16)
- Round 2+: r2_{{region}}_{{position}} (e.g. r2_east_1)
- Final Four: r5_semi1, r5_semi2
- Championship: championship
"""

    prompt = f"""You are looking at the ESPN NCAA Men's Basketball Tournament scoreboard.

Your task:
1. Look at all the games shown on this page.
2. Scroll through to find all completed tournament games across all rounds.
3. For each completed game, extract the result.

{tournament_context}

Return your results in this exact JSON format:
{schema}

Important:
- ONLY include completed/final games. Do NOT include games that haven't happened yet.
- Use team slugs (lowercase, underscores): duke, north_carolina, montana_st, etc.
- Use slot IDs matching the bracket position of each game.
- The "score" field should be a string like "78-65" (winner's score first).
- Scroll down to see all games if they don't fit on one screen.
- Navigate between rounds/days if needed to see all completed games.
- Output ONLY valid JSON. No other text before or after.
"""

    kwargs = {"task_prompt": prompt, "start_url": results_url, "browser": browser}
    if model:
        kwargs["model"] = model

    raw_response = run_agent(**kwargs)
    data = extract_json_from_response(raw_response)

    if data is None:
        print("Warning: Could not parse JSON from agent response.")
        print(f"Raw response (first 500 chars): {raw_response[:500]}")
        return None

    return data
