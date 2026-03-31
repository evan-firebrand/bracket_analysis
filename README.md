# Bracket Analysis

NCAA Tournament bracket analysis app. Scores bracket picks, compares players head-to-head, and runs simulations using Vegas odds.

## Data

All tournament data lives in `data/` and is tracked in git. See `docs/DATA_CONTRACT.md` for exact schemas.

| File | Contents | Records |
|------|----------|---------|
| `data/tournament.json` | 64 teams, 63 slots, bracket tree | 64 teams |
| `data/results.json` | Completed game results with scores | 60 games (through Elite 8) |
| `data/odds.json` | DraftKings betting lines by round | 58 games (R1 + R32 + S16 + FF) |
| `data/entries/player_brackets.json` | Player bracket picks | Evan (63 picks), Rebecca (63 picks via ESPN) |

### Data Sources

- **Brackets**: Rebecca's from ESPN Tournament Challenge group; Evan's from NCAA.com bracket screenshots
- **Results**: Extracted from NCAA bracket images, QA'd region-by-region with zoomed images
- **Odds**: DraftKings game lines (spreads, moneylines, totals) entered from screenshots
- **Tournament structure**: Generated from results + odds data (teams, seeds, regions, bracket tree)

All data uses **team slugs** (lowercase, underscored: `duke`, `north_carolina`, `michigan_st`) and **slot IDs** (`r1_east_1v16`, `r2_east_1`, `r5_semi1`, `championship`).

## Architecture

```
data/                       # Tournament data (tracked in git)
  tournament.json           # Teams, seeds, regions, bracket tree
  results.json              # Game results keyed by slot_id
  odds.json                 # DraftKings lines by round
  entries/
    player_brackets.json    # All player bracket picks

src/
  models.py                 # Prompt schema helpers
  storage.py                # JSON file read/write

scripts/
  validate_data.py          # Structural + score sanity validation
  verify_points.py          # Team point tally cross-check
  verify_results.py         # Web cross-reference against ESPN

docs/
  DATA_CONTRACT.md          # Exact schemas for all data files

config.yaml                 # Data directory and source URLs
```

## Validation

Three layers of data verification:

```bash
# Layer 1: Structural validation (slot IDs, team refs, bracket tree, score sanity)
python scripts/validate_data.py

# Layer 2: Team point tallies for manual cross-reference
python scripts/verify_points.py
python scripts/verify_points.py --team duke

# Layer 3: Web cross-reference against ESPN (requires Playwright)
python scripts/verify_results.py
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # only needed for verify_results.py
```

## Updating Data

1. Edit the relevant JSON file in `data/`
2. Run `python scripts/validate_data.py` — must pass
3. Run `python scripts/verify_points.py` — spot-check totals
4. Commit and push

## Current Status

- [x] Tournament structure (64 teams, 63 slots)
- [x] Game results through Elite 8 (60 games, QA verified)
- [x] Betting odds R1 + R32 + S16 + FF (58 games)
- [x] Evan's NCAA bracket picks (63 picks, tree-consistent)
- [x] Rebecca's ESPN bracket picks (63 picks)
- [x] Data validation + verification scripts
- [ ] Elite 8 odds (4 games missing)
- [ ] Final Four + Championship results (upcoming)
- [ ] NCAA bracket support (deferred)
