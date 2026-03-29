"""Fetch bracket picks from ESPN using Claude computer use.

Output format matches docs/DATA_CONTRACT.md:
- Picks are a map of slot_id → team_slug
- Team slugs: lowercase, underscores, no special chars
- Slot IDs: r1_east_1v16, r2_east_1, r3_east_1, r4_east_1, r5_semi1, championship
"""

from src.agent import extract_json_from_response, run_agent
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

# All 63 valid slot IDs for a standard 64-team bracket
VALID_SLOT_IDS = [
    # Round 1 - East (8 games)
    "r1_east_1v16", "r1_east_8v9", "r1_east_5v12", "r1_east_4v13",
    "r1_east_6v11", "r1_east_3v14", "r1_east_7v10", "r1_east_2v15",
    # Round 1 - West (8 games)
    "r1_west_1v16", "r1_west_8v9", "r1_west_5v12", "r1_west_4v13",
    "r1_west_6v11", "r1_west_3v14", "r1_west_7v10", "r1_west_2v15",
    # Round 1 - South (8 games)
    "r1_south_1v16", "r1_south_8v9", "r1_south_5v12", "r1_south_4v13",
    "r1_south_6v11", "r1_south_3v14", "r1_south_7v10", "r1_south_2v15",
    # Round 1 - Midwest (8 games)
    "r1_midwest_1v16", "r1_midwest_8v9", "r1_midwest_5v12", "r1_midwest_4v13",
    "r1_midwest_6v11", "r1_midwest_3v14", "r1_midwest_7v10", "r1_midwest_2v15",
    # Round 2 (16 games)
    "r2_east_1", "r2_east_2", "r2_east_3", "r2_east_4",
    "r2_west_1", "r2_west_2", "r2_west_3", "r2_west_4",
    "r2_south_1", "r2_south_2", "r2_south_3", "r2_south_4",
    "r2_midwest_1", "r2_midwest_2", "r2_midwest_3", "r2_midwest_4",
    # Round 3 - Sweet 16 (8 games)
    "r3_east_1", "r3_east_2", "r3_west_1", "r3_west_2",
    "r3_south_1", "r3_south_2", "r3_midwest_1", "r3_midwest_2",
    # Round 4 - Elite 8 (4 games)
    "r4_east_1", "r4_west_1", "r4_south_1", "r4_midwest_1",
    # Round 5 - Final Four (2 games)
    "r5_semi1", "r5_semi2",
    # Round 6 - Championship (1 game)
    "championship",
]


def _clean_picks(picks: dict) -> dict:
    """Filter picks to only valid slot IDs and warn about extras."""
    valid = set(VALID_SLOT_IDS)
    cleaned = {}
    extras = []

    for slot_id, team_slug in picks.items():
        if slot_id in valid:
            cleaned[slot_id] = team_slug
        else:
            extras.append(slot_id)

    if extras:
        print(f"  Removed {len(extras)} invalid slot IDs: {extras[:5]}{'...' if len(extras) > 5 else ''}")

    missing = valid - set(cleaned.keys())
    if missing:
        print(f"  Missing {len(missing)} slot IDs: {sorted(missing)[:5]}{'...' if len(missing) > 5 else ''}")

    return cleaned


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

    slot_list = "\n".join(f"  {s}" for s in VALID_SLOT_IDS)

    prompt = f"""You are looking at an ESPN Tournament Challenge group page.

Your task:
1. Find the member named "{target_member}" in the group standings/leaderboard.
2. Click on their bracket entry to view their full bracket.
3. Once you can see the bracket, extract ALL of their picks for every game.
4. Scroll as needed to see all regions and rounds.

CRITICAL: The tournament has EXACTLY 63 games. Your output must have EXACTLY 63 picks.
Do NOT include First Four / play-in games. Only the main 64-team bracket.

The bracket structure per region (4 regions: East, West, South, Midwest):
- Round 1: 8 games per region (1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15)
- Round 2: 4 games per region
- Sweet 16: 2 games per region
- Elite 8: 1 game per region
- Final Four: 2 games (r5_semi1, r5_semi2)
- Championship: 1 game

Here are ALL 63 valid slot IDs — use ONLY these exact keys:
{slot_list}

For each slot, record which team this person PICKED to win (not the actual result).
If you see a pick was wrong (crossed out/red), still record what they originally picked.

{TEAM_SLUG_INSTRUCTIONS}

Return your results in this exact JSON format:
{schema}

Output ONLY valid JSON. No other text.
"""

    kwargs = {"task_prompt": prompt, "start_url": group_url, "browser": browser}
    if model:
        kwargs["model"] = model

    raw_response = run_agent(**kwargs)
    data = extract_json_from_response(raw_response)

    if data is None:
        print("Warning: Could not parse JSON from agent response.")
        print(f"Raw response (first 500 chars): {raw_response[:500]}")
        return None

    # Post-process: filter to only valid slot IDs
    if "picks" in data and isinstance(data["picks"], dict):
        original_count = len(data["picks"])
        data["picks"] = _clean_picks(data["picks"])
        cleaned_count = len(data["picks"])
        if original_count != cleaned_count:
            print(f"  Cleaned picks: {original_count} → {cleaned_count}")

    return data
