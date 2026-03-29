"""Data models for bracket analysis.

PLACEHOLDER - These schemas will be refined once the user provides
final field definitions. For now they serve as a guide for the
Claude agent prompts and data validation.
"""

# Schema for a single bracket pick (one game prediction)
BRACKET_PICK_SCHEMA = {
    "round": "int (1-6, where 1=Round of 64, 6=Championship)",
    "region": "str (East, West, South, Midwest, or Final Four)",
    "game_number": "int (sequential within the round/region)",
    "team1": "str (team name)",
    "seed1": "int (1-16)",
    "team2": "str (team name)",
    "seed2": "int (1-16)",
    "pick": "str (team name picked to win)",
}

# Schema for a single game result
GAME_RESULT_SCHEMA = {
    "round": "int (1-6)",
    "region": "str",
    "date": "str (YYYY-MM-DD)",
    "team1": "str",
    "score1": "int",
    "team2": "str",
    "score2": "int",
    "winner": "str",
    "status": "str (final, in_progress, scheduled)",
}

# Schema for odds on a single game
ODDS_SCHEMA = {
    "game_date": "str (YYYY-MM-DD)",
    "team1": "str",
    "team2": "str",
    "spread": "float (negative means team1 favored, e.g. -6.5)",
    "moneyline_team1": "int (e.g. -250)",
    "moneyline_team2": "int (e.g. +210)",
    "over_under": "float (e.g. 145.5)",
    "source": "str (ESPN/DraftKings)",
}


def bracket_pick_prompt_schema() -> str:
    """Return a JSON schema description for use in agent prompts."""
    return """{
    "round": <int 1-6>,
    "region": "<East|West|South|Midwest|Final Four>",
    "game_number": <int>,
    "team1": "<team name>",
    "seed1": <int 1-16>,
    "team2": "<team name>",
    "seed2": <int 1-16>,
    "pick": "<team name picked to win>"
}"""


def game_result_prompt_schema() -> str:
    """Return a JSON schema description for use in agent prompts."""
    return """{
    "round": <int 1-6>,
    "region": "<region name>",
    "date": "<YYYY-MM-DD>",
    "team1": "<team name>",
    "score1": <int>,
    "team2": "<team name>",
    "score2": <int>,
    "winner": "<team name>",
    "status": "<final|in_progress|scheduled>"
}"""


def odds_prompt_schema() -> str:
    """Return a JSON schema description for use in agent prompts."""
    return """{
    "game_date": "<YYYY-MM-DD>",
    "team1": "<team name>",
    "team2": "<team name>",
    "spread": <float>,
    "moneyline_team1": <int>,
    "moneyline_team2": <int>,
    "over_under": <float>,
    "source": "ESPN/DraftKings"
}"""
