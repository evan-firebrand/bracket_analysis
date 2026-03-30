"""Fetch NCAA tournament game results from ESPN using Claude computer use.

Output format matches docs/DATA_CONTRACT.md:
- Single results object keyed by slot_id
- Each result has winner, loser (team slugs), and score string
- Only completed games included
"""

from src.agent import extract_json_from_response, run_agent
from src.browser import BrowserSession

# Import valid slot IDs for validation
from src.fetch_bracket import VALID_SLOT_IDS
from src.models import results_prompt_schema
from src.storage import load_tournament


def _validate_results(results: dict) -> dict:
    """Validate and clean results data."""
    valid = set(VALID_SLOT_IDS)
    cleaned = {}
    invalid = []

    for slot_id, result in results.items():
        if slot_id in valid:
            cleaned[slot_id] = result
        else:
            invalid.append(slot_id)

    if invalid:
        print(f"  Removed {len(invalid)} invalid slot IDs from results: {invalid[:5]}")

    return cleaned


def fetch_results(
    results_url: str,
    browser: BrowserSession,
    model: str = None,
    data_dir: str = "data",
) -> dict | None:
    """Fetch current NCAA tournament game results from ESPN bracket page.

    Args:
        results_url: URL to the ESPN NCAA tournament bracket page.
        browser: An active BrowserSession.
        model: Optional model override.
        data_dir: Path to data directory (to load tournament.json for context).

    Returns:
        Dict matching the results.json schema, or None if extraction failed.
    """
    schema = results_prompt_schema()

    # Provide valid slot IDs for reference
    slot_list = "\n".join(f"  {s}" for s in VALID_SLOT_IDS)

    # Load tournament structure if available
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

    prompt = f"""You are looking at the ESPN NCAA Men's Basketball Tournament bracket page.

Your task:
1. This page shows the full tournament bracket with completed game results (scores).
2. Scroll through ALL four regions (East, West, South, Midwest) plus Final Four.
3. For each game that shows a final score, extract the winner, loser, and score.
4. Games that haven't been played yet will show team names without scores — SKIP those.

{tournament_context}

Team slug rules:
- Lowercase, underscores for spaces, no special characters
- Examples: duke, north_carolina, michigan_st, st_johns, miami_fl, iowa_st, texas_am

Here are ALL valid slot IDs — use ONLY these:
{slot_list}

Return your results in this exact JSON format:
{schema}

CRITICAL rules:
- ONLY include games with final scores. Do NOT include upcoming/unplayed games.
- The "score" field is "winner_score-loser_score" e.g. "78-65" (winner's score FIRST).
- Scroll through the entire bracket to capture all completed games.
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

    # Validate slot IDs
    if "results" in data and isinstance(data["results"], dict):
        original = len(data["results"])
        data["results"] = _validate_results(data["results"])
        cleaned = len(data["results"])
        if original != cleaned:
            print(f"  Cleaned results: {original} → {cleaned}")

    return data
