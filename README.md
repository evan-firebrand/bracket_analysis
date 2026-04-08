# Bracket Analysis

NCAA Tournament bracket analysis app. Scores bracket picks, compares players head-to-head, and runs simulations using Vegas odds.

## Data

All tournament data lives in `data/` and is tracked in git. See `docs/DATA_CONTRACT.md` for exact schemas.

| File | Contents | Records |
|------|----------|---------|
| `data/tournament.json` | 64 teams, 63 slots, bracket tree | 64 teams |
| `data/results.json` | Completed game results with scores | 60 games (through Elite 8) |
| `data/odds.json` | DraftKings betting lines by round | 58 games (R1 + R32 + S16 + FF) |
| `data/entries/player_brackets.json` | Player bracket picks | 7 players (Evan, Rebecca, Elizabeth, Hugh, tvenie, scrapr + 1 more) |

### Data Sources

- **Brackets**: Rebecca's from ESPN Tournament Challenge group; Evan's from NCAA.com bracket screenshots
- **Results**: Extracted from NCAA bracket images, QA'd region-by-region with zoomed images
- **Odds**: DraftKings game lines (spreads, moneylines, totals) entered from screenshots
- **Tournament structure**: Generated from results + odds data (teams, seeds, regions, bracket tree)

All data uses **team slugs** (lowercase, underscored: `duke`, `north_carolina`, `michigan_st`) and **slot IDs** (`r1_east_1v16`, `r2_east_1`, `r5_semi1`, `championship`).

## Architecture

```
core/                       # Pure Python analysis (no Streamlit imports)
  scoring.py                # ESPN scoring engine (10/20/40/80/160/320)
  scenarios.py              # Brute-force + Monte Carlo scenario engines
  tournament.py             # Game tree traversal, remaining slots, team paths
  comparison.py             # H2H diffs, pick popularity, chalk scores
  context.py                # Central data object (loads + caches everything)
  loader.py                 # Data loading + bracket tree validation
  models.py                 # Dataclasses (Team, GameSlot, Results, PlayerEntry)
  narrative.py              # Template-based text descriptions (fallback)
  metrics.py                # Win equity, separation, must-have outcomes
  awards.py                 # End-of-tournament superlatives
  recap.py                  # Round recap generation
  superlatives.py           # Player distinction logic
  ai/                       # Claude integration (Anthropic tool-use)
    client.py               # Anthropic client singleton
    tools.py                # Tool schemas + adapters wrapping core/ functions
    agent.py                # Claude tool-use loop: prompt → tool_use → execute
    lenses.py               # System prompts + model config per output mode
    evidence.py             # Evidence packet capture + audit logging
    cache.py                # Content cache keyed on (lens, viewer, data_hash)

analyses/                   # Auto-discovered Streamlit plugins (presentation only)
  leaderboard.py            # Standings and rankings
  my_bracket.py             # Individual bracket view
  head_to_head.py           # Player comparison diffs
  group_picks.py            # Group-wide pick analysis
  win_probability.py        # Win% dashboard and critical games
  scenarios_whatif.py       # Game-by-game what-if tool
  race.py                   # Race to the finish tracker
  my_position.py            # Win equity, separation, must-have outcomes, danger games
  threats.py                # Who you need to beat and how likely you are to do it
  rooting_guide.py          # What to root for, what to fear, what doesn't matter
  pool_exposure.py          # Where the pool is crowded and where you're alone
  round_recap.py            # Round results, upsets, and standings impact
  superlatives.py           # End-of-tournament awards and distinctions
  ask_claude.py             # Freeform AI chat about brackets, scenarios, and odds

app.py                      # Streamlit web UI entry point

data/                       # Tournament data (tracked in git)
  tournament.json           # Teams, seeds, regions, bracket tree
  results.json              # Game results keyed by slot_id
  odds.json                 # DraftKings lines by round
  entries/
    player_brackets.json    # All player bracket picks (7 players)

src/
  extract_bracket.py        # ESPN bracket extraction via Playwright DOM
  models.py                 # Prompt schema helpers
  storage.py                # JSON file read/write

scripts/
  validate_data.py          # Structural + score sanity validation
  verify_points.py          # Team point tally cross-check
  verify_results.py         # Web cross-reference against ESPN
  generate_content.py       # Pre-generate AI content to warm the cache
  fetch_espn_bracket.py     # Fetch bracket from ESPN group
  fetch_batch_brackets.py   # Batch fetch multiple brackets
  validate_pr.py            # PR description validation (used by CI)
  review_checklist.py       # Diff-aware review checklist (used by CI)

tests/                      # pytest test suite
  test_scoring.py           # Scoring engine tests
  test_scenarios.py         # Scenario engine tests
  test_comparisons.py       # Comparison logic tests
  test_plugins.py           # Plugin discovery tests
  test_odds_integration.py  # Odds integration tests
  test_ai_agent.py          # AI agent loop tests
  test_ai_tools.py          # AI tool schema tests
  test_ai_cache.py          # Content cache tests
  test_ai_evidence.py       # Evidence capture tests
  test_ai_context.py        # AI context integration tests
  test_validate_pr.py       # PR validation tests
  test_review_checklist.py  # Review checklist tests
  fixtures/                 # Test data (mini tournament)

docs/
  DATA_CONTRACT.md          # Exact schemas for all data files
  decisions/                # Architecture Decision Records (ADRs)

.github/
  workflows/ci.yml          # CI: ruff + pytest + PR validation + review checklist
  PULL_REQUEST_TEMPLATE.md  # 7-section PR template (incl. Squash Commit)

config.yaml                 # Data directory and source URLs
pyproject.toml              # pytest + ruff config
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

## Web UI

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app loads `AnalysisContext` (tournament, results, entries) and renders analysis plugins from `analyses/`. Plugins auto-discover — add a new `.py` file to `analyses/` and it appears in the sidebar.

## Testing & CI

```bash
pytest              # run tests
ruff check .        # lint
```

CI runs both on every PR to `main`. Additionally:
- **PR validation**: hard-fails if any of the 7 required sections are missing from the PR description
- **Review checklist**: posts an advisory comment based on which files changed

## Setup

```bash
pip install -r requirements.txt
playwright install chromium   # only needed for ESPN bracket fetching and verify_results.py
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
