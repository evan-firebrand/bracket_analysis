"""Fetch bracket picks from ESPN using Claude computer use.

Output format matches docs/DATA_CONTRACT.md:
- Picks are a map of slot_id → team_slug
- Team slugs: lowercase, underscores, no special chars
- Slot IDs: r1_east_1v16, r2_east_1, r3_east_1, r4_east_1, r5_semi1, championship
"""

from src.agent import run_agent, extract_json_from_response
from src.browser import BrowserSession
from src.models import bracket_picks_prompt_schema


TEAM_SLUG_INSTRUCTIONS = """
Team slug rules (CRITICAL — must follow exactly):
- Lowercase only
- Spaces become underscores
- No special characters
- Examples: duke, north_carolina, montana_st, st_marys, texas_am, uconn

Slot ID rules (CRITICAL — must follow exactly):
- Round 1: r1_{region}_{highseed}v{lowseed}  e.g. r1_east_1v16, r1_east_8v9
- Round 2: r2_{region}_{position}  e.g. r2_east_1, r2_east_2
- Round 3: r3_{region}_{position}  e.g. r3_east_1
- Round 4: r4_{region}_1  e.g. r4_east_1
- Final Four: r5_semi1, r5_semi2
- Championship: championship
- Region names in slot IDs are lowercase: east, west, south, midwest
"""


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
        Dict with player_name, entry_name, and picks (slot_id → team_slug),
        or None if extraction failed.
    """
    schema = bracket_picks_prompt_schema()

    prompt = f"""You are looking at an ESPN Tournament Challenge group page.

Your task:
1. Find the member named "{target_member}" in the group standings/leaderboard.
2. Click on their bracket entry to view their full bracket.
3. Once you can see the bracket, extract ALL of their picks for every game in the tournament.
4. Scroll as needed to see all regions and rounds (Round of 64 through Championship).

Return your results in this exact JSON format:
{schema}

{TEAM_SLUG_INSTRUCTIONS}

Important:
- Include ALL 63 game picks covering all 4 regions plus Final Four and Championship.
- The picks object must have exactly 63 keys (one per slot_id).
- Make sure to scroll through all four regions (East, West, South, Midwest) plus the Final Four.
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
        return None

    return data
