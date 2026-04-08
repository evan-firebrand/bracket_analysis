# CLAUDE.md — Agent Context for bracket_analysis

## What is this repo?

NCAA tournament bracket analysis app. Contains tournament data (teams, results, bracket picks, odds) and tools to analyze, score, and compare brackets. Includes a Streamlit UI (`app.py`) and a plugin-based analysis system.

## Key things to know

- **Data contract**: `docs/DATA_CONTRACT.md` defines exact schemas. All data uses team slugs and slot IDs.
- **Data files are tracked in git**: `data/tournament.json`, `data/results.json`, `data/odds.json`, `data/entries/player_brackets.json`
- **Data was manually collected**: Brackets from ESPN + NCAA screenshot extraction, results from bracket images, odds from DraftKings screenshots. No automated scraping.
- **ESPN group URL**: Configured in `config.yaml` under `sources.espn_group`. Currently targets Rebecca's bracket.
- **Analysis plugins**: `analyses/` directory — each `.py` file is auto-discovered and rendered as a tab in the UI.
- **NCAA support**: Deferred. Only ESPN is implemented.

## How to run

```bash
pip install -r requirements.txt
# Run the Streamlit UI (primary entry point)
streamlit run app.py
# Validate data integrity
python scripts/validate_data.py
# Verify scores via point tallies
python scripts/verify_points.py
```

## How to update data

**DATA INTEGRITY IS CRITICAL** — the app's scoring and simulation depend entirely on correct JSON data.

1. Edit the relevant JSON file in `data/`
2. Run `python scripts/validate_data.py` to check structural integrity
3. Run `python scripts/verify_points.py` to sanity-check scores
4. Run `python scripts/verify_results.py` to cross-check results

## How to extend

### Add an analysis view (plugin)

1. Create `analyses/<name>.py` with these required module-level attributes:
   - `TITLE: str` — display name
   - `DESCRIPTION: str` — short description shown in sidebar
   - `CATEGORY: str` — groups tabs in the UI (e.g. `"standings"`, `"simulation"`)
   - `ORDER: int` — sort order within category
   - `ICON: str` — emoji shown in sidebar
2. Implement `render(ctx: AnalysisContext) -> None` using Streamlit calls
3. The plugin is auto-discovered on next `streamlit run app.py` — no registration needed

### Add a data source

1. Create `src/fetch_<thing>.py` following the pattern in existing modules
2. Save with `src/storage.py` helpers or add a new save function
3. Update `docs/DATA_CONTRACT.md` if adding new schema fields

## Project structure

```
app.py                — Streamlit entry point; loads plugins + AnalysisContext
analyses/             — Analysis plugins (auto-discovered); one file per view
core/                 — Shared business logic
  loader.py           — Loads and parses data files
  models.py           — Domain types (Team, BracketEntry, GameResult, etc.)
  scoring.py          — Points calculation + leaderboard
  tournament.py       — Bracket tree traversal
  comparison.py       — Head-to-head + group pick analysis
  scenarios.py        — What-if simulation
  context.py          — AnalysisContext: the single object passed to every plugin
  narrative.py        — Text formatting helpers
src/                  — Data fetching + storage utilities
  extract_bracket.py  — ESPN bracket extraction helpers
  models.py           — Prompt schema helpers (aligned with docs/DATA_CONTRACT.md)
  storage.py          — JSON file read/write
scripts/              — CLI tools
  validate_data.py    — Structural + contract validation
  verify_points.py    — Score sanity check
  verify_results.py   — Results cross-check
  fetch_espn_bracket.py     — Fetch one bracket from ESPN
  fetch_batch_brackets.py   — Batch-fetch multiple brackets
  validate_pr.py      — CI: validate PR description sections
  review_checklist.py — CI: post diff-aware checklist comments
config.yaml           — All configuration
data/                 — Tournament data (tracked in git)
docs/DATA_CONTRACT.md — Data schema definitions
```

## Important constraints

- Requires `ANTHROPIC_API_KEY` environment variable for any agent-based fetching
- ESPN is a JS SPA — cannot be scraped with simple HTTP requests
- Data files are the source of truth — edit them carefully and always re-validate

## PR conventions

Before opening a PR, do a self-assessment. Every PR description MUST include these 6 sections with real content (not just template placeholders):

- **## Requirements** — What was asked for. Copy or summarize the original request.
- **## Solution** — What was built. Describe the approach and key files changed.
- **## Issues & Revisions** — Problems found during implementation, honest self-assessment, what changed from the first attempt to the final version. There are ALWAYS issues — be specific and honest.
- **## Decisions** — Design choices, tradeoffs, alternatives you considered.
- **## Testing** — What you tested, how, and results with numbers (e.g. "14 → 30 tests, all passing").
- **## Scope** — Was there scope creep? Unmet requirements? What was deferred and why?

CI hard-fails if any section is missing or empty. Thin sections (≤1 line) get an advisory comment. A PR template is provided — fill in every section before submitting.

After opening a PR, subscribe to PR activity (`subscribe_pr_activity`) and wait for CI to complete. CI will post a review checklist comment based on which files you changed (e.g. "core/ changed — did you add tests?"). Review each checklist item and address any gaps before requesting human review.
