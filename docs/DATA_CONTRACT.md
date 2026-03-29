# Data Contract — NCAA Bracket Analysis App

This document defines the **exact file formats, locations, and naming conventions** required by the bracket analysis app. The data processing agent must produce files that match these schemas exactly. The app runs `scripts/validate_data.py` after every data update — any schema violation will be rejected.

---

## Overview

| File | Path | Frequency | Producer |
|------|------|-----------|----------|
| Tournament structure | `data/tournament.json` | Once, before tournament starts | Data agent |
| Game results | `data/results.json` | After each game or batch | Data agent |
| Player brackets | `data/entries/player_brackets.json` | Once, after brackets lock | Data agent |
| Vegas odds | `data/odds.json` | 2x/day during tournament | Data agent |

All paths are relative to the repository root (`bracket_analysis/`).

---

## 1. Tournament Structure — `data/tournament.json`

**When to create:** Once, before the tournament starts (after First Four if applicable).

**Top-level keys:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `year` | integer | YES | Tournament year (e.g., `2026`) |
| `teams` | object | YES | Map of team_slug → team info |
| `slots` | array | YES | Ordered list of all game slots |

### `teams` object

Keys are **team slugs** (see naming conventions below). Each value:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | YES | Display name (e.g., `"Duke"`, `"North Carolina"`) |
| `seed` | integer | YES | Tournament seed (1-16) |
| `region` | string | YES | Region name (e.g., `"East"`, `"West"`, `"South"`, `"Midwest"`) |

### `slots` array

Each element represents one game in the bracket. **Order matters** — list Round 1 games first, then Round 2, etc.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `slot_id` | string | YES | Unique identifier (see naming conventions) |
| `round` | integer | YES | Round number: 1=R64, 2=R32, 3=Sweet16, 4=Elite8, 5=FinalFour, 6=Championship |
| `region` | string | YES | Region name, or `"Final Four"` for rounds 5-6 |
| `position` | integer | YES | Position within the region/round (1-based) |
| `top_team` | string or null | YES | Team slug for Round 1 (higher seed). `null` for rounds 2+ |
| `bottom_team` | string or null | YES | Team slug for Round 1 (lower seed). `null` for rounds 2+ |
| `feeds_into` | string or null | YES | `slot_id` of the next-round game this feeds into. `null` for the championship game |

### Full 64-team tournament slot counts

| Round | Number | Games | Example slot_id |
|-------|--------|-------|----------------|
| 1 (R64) | 1 | 32 | `r1_east_1v16`, `r1_east_8v9` |
| 2 (R32) | 2 | 16 | `r2_east_1`, `r2_east_2` |
| 3 (Sweet 16) | 3 | 8 | `r3_east_1`, `r3_east_2` |
| 4 (Elite 8) | 4 | 4 | `r4_east_1` |
| 5 (Final Four) | 5 | 2 | `r5_semi1`, `r5_semi2` |
| 6 (Championship) | 6 | 1 | `championship` |
| **Total** | | **63** | |

### Example

```json
{
  "year": 2026,
  "teams": {
    "duke": {"name": "Duke", "seed": 1, "region": "East"},
    "montana_st": {"name": "Montana St.", "seed": 16, "region": "East"},
    "north_carolina": {"name": "North Carolina", "seed": 8, "region": "East"},
    "vermont": {"name": "Vermont", "seed": 9, "region": "East"}
  },
  "slots": [
    {
      "slot_id": "r1_east_1v16",
      "round": 1,
      "region": "East",
      "position": 1,
      "top_team": "duke",
      "bottom_team": "montana_st",
      "feeds_into": "r2_east_1"
    },
    {
      "slot_id": "r1_east_8v9",
      "round": 1,
      "region": "East",
      "position": 2,
      "top_team": "north_carolina",
      "bottom_team": "vermont",
      "feeds_into": "r2_east_1"
    },
    {
      "slot_id": "r2_east_1",
      "round": 2,
      "region": "East",
      "position": 1,
      "top_team": null,
      "bottom_team": null,
      "feeds_into": "r3_east_1"
    }
  ]
}
```

---

## 2. Game Results — `data/results.json`

**When to update:** After each game finishes, or in batches after a session of games.

**Top-level keys:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `last_updated` | string | YES | ISO 8601 timestamp (e.g., `"2026-03-22T20:30:00Z"`) |
| `results` | object | YES | Map of slot_id → game result |

### `results` object

Keys are `slot_id` strings matching `tournament.json`. **Only include completed games.** A slot appearing in this object means the game is finished.

Each value:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `winner` | string | YES | Team slug of the winning team |
| `loser` | string | YES | Team slug of the losing team |
| `score` | string or null | NO | Display score (e.g., `"78-65"`). Not used for scoring, just for display. |

### Critical rules

- **Only completed games** should appear in `results`. Do NOT include pending/in-progress games.
- `winner` and `loser` must be valid team slugs from `tournament.json`.
- `winner` and `loser` must be the two teams that actually played in that slot (based on bracket progression).

### Example

```json
{
  "last_updated": "2026-03-22T20:30:00Z",
  "results": {
    "r1_east_1v16": {"winner": "duke", "loser": "montana_st", "score": "78-65"},
    "r1_east_8v9": {"winner": "vermont", "loser": "north_carolina", "score": "71-68"},
    "r2_east_1": {"winner": "duke", "loser": "vermont", "score": "80-74"}
  }
}
```

---

## 3. Player Brackets — `data/entries/player_brackets.json`

**When to create:** Once, after all brackets are locked (typically before the first game).

**Top-level keys:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `entries` | array | YES | Array of player entry objects |

### Each entry object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `player_name` | string | YES | Display name (e.g., `"Alice"`) — must be unique across entries |
| `entry_name` | string | NO | Bracket name (e.g., `"Alice's Bold Bracket"`). Defaults to player_name if omitted. |
| `picks` | object | YES | Map of slot_id → team_slug for all 63 games |

### `picks` object

- Keys: every `slot_id` from `tournament.json` (all 63 must be present)
- Values: team slugs from `tournament.json`

### Critical validation rules

1. **All 63 slots must have a pick.** Missing slots = validation error.
2. **All team slugs must exist** in `tournament.json`.
3. **Bracket tree consistency:** If a player picks team X in round N slot S, then team X must also be their pick in one of the two feeder slots that feed into S. Example: if you pick "duke" to win `r2_east_1`, then "duke" must be your pick for either `r1_east_1v16` or `r1_east_8v9` (whichever feeds into `r2_east_1`).

### Example

```json
{
  "entries": [
    {
      "player_name": "Alice",
      "entry_name": "Alice's Chalk Bracket",
      "picks": {
        "r1_east_1v16": "duke",
        "r1_east_8v9": "north_carolina",
        "r2_east_1": "duke",
        "r3_east_1": "duke",
        "r4_east_1": "duke",
        "r5_semi1": "duke",
        "championship": "duke"
      }
    },
    {
      "player_name": "Bob",
      "entry_name": "Bob's Upset Special",
      "picks": {
        "r1_east_1v16": "montana_st",
        "r1_east_8v9": "vermont",
        "r2_east_1": "vermont",
        "r3_east_1": "vermont",
        "r4_east_1": "vermont",
        "r5_semi1": "vermont",
        "championship": "vermont"
      }
    }
  ]
}
```

---

## 4. Vegas Odds — `data/odds.json`

**When to update:** 2x/day during the tournament.

**Top-level keys:**

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `last_updated` | string | YES | ISO 8601 timestamp |
| `source` | string | YES | Odds source (e.g., `"FanDuel"`, `"DraftKings"`, `"ESPN BPI"`) |
| `teams` | object | YES | Map of team_slug → probability data |

### Each team object

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `championship` | float | YES | Probability of winning the tournament (0.0 to 1.0) |
| `round_probs` | object | YES | Map of round key → probability of reaching at least that round |

### `round_probs` keys

| Key | Meaning |
|-----|---------|
| `r2` | Probability of reaching Round of 32 (winning R1) |
| `r3` | Probability of reaching Sweet 16 |
| `r4` | Probability of reaching Elite 8 |
| `ff` | Probability of reaching Final Four |
| `championship` | Probability of reaching the Championship game |
| `winner` | Probability of winning it all (same as top-level `championship`) |

These are **cumulative** — probability of reaching *at least* that round. So `r2` >= `r3` >= `r4` etc.

### Rules

- **Only include alive teams.** Eliminated teams can be omitted entirely.
- Probabilities should be between 0.0 and 1.0 (not percentages).
- If exact matchup probabilities aren't available, team-level round advancement probs are sufficient.
- **Fallback:** If this file is missing or stale, the app falls back to seed-based historical win rates.

### Example

```json
{
  "last_updated": "2026-03-22T14:00:00Z",
  "source": "FanDuel",
  "teams": {
    "duke": {
      "championship": 0.15,
      "round_probs": {
        "r2": 0.95,
        "r3": 0.78,
        "r4": 0.55,
        "ff": 0.38,
        "championship": 0.22,
        "winner": 0.15
      }
    },
    "houston": {
      "championship": 0.12,
      "round_probs": {
        "r2": 0.93,
        "r3": 0.72,
        "r4": 0.50,
        "ff": 0.32,
        "championship": 0.18,
        "winner": 0.12
      }
    }
  }
}
```

---

## Naming Conventions

### Team slugs

- Lowercase
- Underscores for spaces
- No special characters
- Examples: `duke`, `north_carolina`, `montana_st`, `st_marys`, `texas_am`
- **Must be consistent across ALL four files.** If tournament.json uses `"north_carolina"`, then results.json and player_brackets.json must also use `"north_carolina"` (not `"unc"` or `"UNC"` or `"North Carolina"`).

### Slot IDs

- Format: `r{round}_{region}_{matchup_or_position}`
- Region names: lowercase (e.g., `east`, `west`, `south`, `midwest`)
- Round 1 examples: `r1_east_1v16`, `r1_east_8v9`, `r1_west_2v15`
- Round 2+ examples: `r2_east_1`, `r2_east_2`, `r3_east_1`
- Final Four: `r5_semi1`, `r5_semi2`
- Championship: `championship`

### Region names (in `region` fields)

- Use title case in the data: `"East"`, `"West"`, `"South"`, `"Midwest"`
- Use `"Final Four"` for rounds 5 and 6

---

## Validation

After producing any data file, run:

```bash
python scripts/validate_data.py
```

This checks:
- All required fields are present
- All team slugs are consistent across files
- All slot_ids in results/entries exist in tournament.json
- All player bracket picks form valid bracket trees
- Winner/loser in results are valid teams

**The app will not load data that fails validation.**

---

## File Location Summary

```
bracket_analysis/
└── data/
    ├── tournament.json                  # Tournament structure (64 teams, 63 slots)
    ├── results.json                     # Game outcomes (updated after each game)
    ├── odds.json                        # Vegas odds (updated 2x/day)
    └── entries/
        └── player_brackets.json         # All player picks (written once)
```
