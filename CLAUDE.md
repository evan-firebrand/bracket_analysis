# CLAUDE.md — Agent Context for bracket_analysis

## What is this repo?

NCAA tournament bracket analysis app. Contains tournament data (teams, results, bracket picks, odds) and tools to analyze, score, and compare brackets.

## Key things to know

- **Data contract**: `docs/DATA_CONTRACT.md` defines exact schemas. All data uses team slugs and slot IDs.
- **Data files are tracked in git**: `data/tournament.json`, `data/results.json`, `data/odds.json`, `data/entries/player_brackets.json`
- **Data was manually collected**: Brackets from ESPN + NCAA screenshot extraction, results from bracket images, odds from DraftKings screenshots. No automated scraping.
- **ESPN group URL**: Configured in `config.yaml` under `sources.espn_group`. Currently targets Rebecca's bracket.
- **NCAA support**: Deferred. Only ESPN is implemented.

- **DATA INTEGRITY IS CRITICAL**: Never use fake data or make guesses. All data must be verified against official sources\*\*

## How to run

```bash
pip install -r requirements.txt
# Validate data integrity
python scripts/validate_data.py
# Verify scores via point tallies
python scripts/verify_points.py
```

## How to update data

1. Edit the relevant JSON file in `data/`
2. Run `python scripts/validate_data.py` to check integrity
3. Run `python scripts/verify_points.py` to sanity-check scores

## How to extend

To add a new data source or scraping target:

1. Create `src/fetch_<thing>.py` following the pattern in existing modules
2. Write a detailed prompt telling Claude what to navigate and extract
3. Save with `storage.save_*()` or add a new save function

## Project structure

```
src/models.py         — Prompt schema helpers (aligned with docs/DATA_CONTRACT.md)
src/storage.py        — JSON file read/write
scripts/              — CLI tools (validation, verification)
config.yaml           — All configuration
data/                 — Tournament data (tracked in git)
docs/DATA_CONTRACT.md — Data schema definitions
```

## Important constraints

- Requires `ANTHROPIC_API_KEY` environment variable for any agent-based fetching
- ESPN is a JS SPA — cannot be scraped with simple HTTP requests
- Set `browser.headless: false` in config.yaml to watch the browser during development

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
