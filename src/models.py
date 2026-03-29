"""Data models for bracket analysis.

These match the data contract defined in docs/DATA_CONTRACT.md.
The app uses team slugs (lowercase, underscored) and slot IDs
(e.g. r1_east_1v16) as keys across all data files.
"""


def tournament_prompt_schema() -> str:
    """JSON schema description for tournament structure extraction."""
    return """{
    "year": 2026,
    "teams": {
        "<team_slug>": {"name": "<Display Name>", "seed": <1-16>, "region": "<East|West|South|Midwest>"},
        ...
    },
    "slots": [
        {
            "slot_id": "<e.g. r1_east_1v16>",
            "round": <1-6>,
            "region": "<region or Final Four>",
            "position": <int>,
            "top_team": "<team_slug or null>",
            "bottom_team": "<team_slug or null>",
            "feeds_into": "<slot_id or null>"
        },
        ...
    ]
}"""


def bracket_picks_prompt_schema() -> str:
    """JSON schema for player bracket picks extraction."""
    return """{
    "player_name": "<name>",
    "entry_name": "<bracket name>",
    "picks": {
        "<slot_id>": "<team_slug>",
        "r1_east_1v16": "duke",
        "r1_east_8v9": "north_carolina",
        "r2_east_1": "duke",
        ...all 63 slots...
    }
}"""


def results_prompt_schema() -> str:
    """JSON schema for game results extraction."""
    return """{
    "last_updated": "<ISO 8601 timestamp>",
    "results": {
        "<slot_id>": {
            "winner": "<team_slug>",
            "loser": "<team_slug>",
            "score": "<score string e.g. 78-65>"
        },
        ...only completed games...
    }
}"""


def odds_prompt_schema() -> str:
    """JSON schema for Vegas odds extraction.

    Odds are team-level round advancement probabilities (0.0 to 1.0),
    NOT per-game spreads or moneylines.
    """
    return """{
    "last_updated": "<ISO 8601 timestamp>",
    "source": "ESPN/DraftKings",
    "teams": {
        "<team_slug>": {
            "championship": <float 0.0-1.0>,
            "round_probs": {
                "r2": <prob of reaching Round of 32>,
                "r3": <prob of reaching Sweet 16>,
                "r4": <prob of reaching Elite 8>,
                "ff": <prob of reaching Final Four>,
                "championship": <prob of reaching Championship game>,
                "winner": <prob of winning it all>
            }
        },
        ...only alive teams...
    }
}"""


# Slot ID naming conventions for reference
SLOT_ID_EXAMPLES = {
    "Round 1 (R64)": "r1_east_1v16, r1_east_8v9, r1_west_2v15",
    "Round 2 (R32)": "r2_east_1, r2_east_2",
    "Round 3 (Sweet 16)": "r3_east_1, r3_east_2",
    "Round 4 (Elite 8)": "r4_east_1",
    "Round 5 (Final Four)": "r5_semi1, r5_semi2",
    "Round 6 (Championship)": "championship",
}

# Team slug convention: lowercase, underscores, no special chars
# Examples: duke, north_carolina, montana_st, st_marys, texas_am
