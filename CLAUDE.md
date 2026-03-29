# CLAUDE.md — Agent Context for bracket_analysis

## What is this repo?

Data collection layer for an NCAA tournament bracket analysis app. Uses Claude's computer use API to control a headless browser and scrape ESPN for bracket picks, game results, and betting odds.

## Key things to know

- **Claude computer use beta**: `computer_20251124` with `client.beta.messages.create()` — see `src/agent.py`
- **Browser**: Playwright Chromium (headless). Actions in `src/browser.py`, agent loop in `src/agent.py`
- **ESPN group URL**: Configured in `config.yaml` under `espn_group.url`. Currently targets Rebecca's bracket.
- **Data contract**: `docs/DATA_CONTRACT.md` defines exact schemas. All data uses team slugs and slot IDs.
- **Data output**: Single JSON files — `data/tournament.json`, `data/results.json`, `data/odds.json`, `data/entries/player_brackets.json` (all gitignored)
- **NCAA support**: Deferred. Only ESPN is implemented.

## How to run

```bash
pip install -r requirements.txt && playwright install chromium
# Set ANTHROPIC_API_KEY in .env
python scripts/fetch_brackets.py     # fetch bracket picks
python scripts/fetch_results.py      # fetch results + odds
python scripts/run_scheduler.py      # start twice-daily scheduler
```

## How to extend

To add a new data source or scraping target:
1. Create `src/fetch_<thing>.py` following the pattern in `fetch_bracket.py`
2. Write a detailed prompt telling Claude what to navigate and extract
3. Call `run_agent(prompt, url, browser)` — it returns Claude's text response
4. Use `extract_json_from_response()` to parse the JSON
5. Save with `storage.save_*()` or add a new save function

## Project structure

```
src/agent.py          — Core agent loop (reusable for any web task)
src/browser.py        — Playwright browser + action execution
src/fetch_bracket.py  — ESPN bracket extraction
src/fetch_results.py  — Game results extraction
src/fetch_odds.py     — Betting odds extraction
src/models.py         — Prompt schema helpers (aligned with docs/DATA_CONTRACT.md)
src/storage.py        — JSON file read/write
scripts/              — CLI entry points + scheduler
config.yaml           — All configuration
```

## Important constraints

- Requires `ANTHROPIC_API_KEY` environment variable
- ESPN is a JS SPA — cannot be scraped with simple HTTP requests, must use browser
- Agent loop has a 30-iteration safety cap (`MAX_ITERATIONS` in `agent.py`)
- Set `browser.headless: false` in config.yaml to watch the browser during development
