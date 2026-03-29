# Bracket Analysis

NCAA Tournament bracket analysis tool that uses Claude's computer use API to control a headless browser for data collection.

## What This Does

This is the **data collection layer** of a broader bracket analysis app. It handles three tasks:

1. **Bracket Fetching** — Navigates to an ESPN Tournament Challenge group page, finds a specific member's bracket (currently Rebecca), and extracts all 63 game picks as structured JSON.

2. **Results Fetching** — Navigates to the ESPN NCAA tournament scoreboard and extracts completed game scores/results.

3. **Odds Fetching** — Extracts DraftKings betting lines (spread, moneyline, over/under) from ESPN game pages.

All three use **Claude's computer use API** (`computer_20251124` beta) to control a Playwright Chromium browser. Claude sees screenshots, decides what to click/scroll/type, and extracts data visually.

## Architecture

```
scripts/                    # CLI entry points (run these)
  fetch_brackets.py         # Fetch bracket picks on demand
  fetch_results.py          # Fetch game results + odds on demand
  run_scheduler.py          # Twice-daily automated fetcher (8am/8pm ET)

src/                        # Core modules
  browser.py                # Playwright browser lifecycle + action execution
  agent.py                  # Claude computer use agent loop
  fetch_bracket.py          # ESPN bracket extraction logic + prompts
  fetch_results.py          # Game results extraction logic + prompts
  fetch_odds.py             # Odds extraction logic + prompts
  models.py                 # Data schemas (PLACEHOLDER - see below)
  storage.py                # JSON file storage (read/write to data/)

data/                       # Output directory (gitignored)
  brackets/                 # e.g. espn_rebecca_2026-03-29T120000.json
  results/                  # e.g. results_2026-03-29T120000.json
  odds/                     # e.g. odds_2026-03-29T120000.json

config.yaml                 # URLs, browser settings, schedule config
```

## How the Agent Loop Works

`src/agent.py` implements the core loop:

1. Opens a Playwright browser and navigates to a URL
2. Takes a screenshot and sends it to Claude via `client.beta.messages.create()` with the `computer_20251124` tool
3. Claude responds with actions (click, scroll, type, etc.) or a final text answer
4. If actions: execute them via Playwright, screenshot the result, send back to Claude
5. Loop until Claude returns extracted data as text (JSON)
6. Parse the JSON and save to `data/`

Max 30 iterations per run as a safety cap.

## Data Output Format

Each saved file is a JSON envelope:

```json
{
  "source": "espn",
  "entry_id": "rebecca",
  "fetched_at": "2026-03-29T12:00:00+00:00",
  "data": [ ... ]
}
```

**Data models in `src/models.py` are placeholders.** The schemas for bracket picks, game results, and odds will be finalized by the project owner. Current placeholder fields are reasonable defaults but may change.

## Configuration

**`config.yaml`** — All URLs, browser settings, and schedule config:
- `espn_group.url` — ESPN Tournament Challenge group page
- `espn_group.target_member` — Which member's bracket to fetch (default: "Rebecca")
- `results.url` / `odds.url` — ESPN scoreboard URL
- `browser.headless` — Set `false` to watch the browser during testing
- `schedule.results_times` — Cron times for automated fetching

**`.env`** — API key only:
```
ANTHROPIC_API_KEY=sk-ant-...
```

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
cp .env.example .env   # add your ANTHROPIC_API_KEY
```

## Usage

```bash
# One-off: fetch Rebecca's bracket from ESPN
python scripts/fetch_brackets.py

# One-off: fetch game results + odds
python scripts/fetch_results.py

# Start scheduler (runs at 8am + 8pm ET)
python scripts/run_scheduler.py
```

## For Other Agents / Downstream Consumers

- **Data lives in `data/`** as timestamped JSON files. Use `src/storage.load_latest()` to get the most recent file.
- **To add a new data source**: create a new `src/fetch_*.py` module following the pattern in `fetch_bracket.py`. Write a prompt, call `run_agent()`, parse the JSON.
- **To change what data is extracted**: modify the prompts in `src/fetch_*.py` and update schemas in `src/models.py`.
- **NCAA bracket support** is planned but deferred. The architecture supports multiple sources — just add a new fetch function.
- **The agent loop (`src/agent.py`)** is source-agnostic. It takes any prompt + URL and returns Claude's text response. Reuse it for any web scraping task.

## Dependencies

- `anthropic` — Claude API SDK (computer use beta)
- `playwright` — Headless Chromium browser
- `pyyaml` — Config file parsing
- `python-dotenv` — .env file loading
- `apscheduler` — Cron-style scheduling
- `Pillow` — Image processing (screenshot handling)

## Current Status

- [x] ESPN bracket fetching (Rebecca's picks from group page)
- [x] Game results fetching from ESPN scoreboard
- [x] Odds fetching (DraftKings lines from ESPN)
- [x] Twice-daily scheduler
- [x] JSON file storage with timestamps
- [ ] Data models — **placeholder, awaiting final field definitions**
- [ ] NCAA bracket support — deferred
- [ ] Bracket scoring / comparison — not yet implemented (downstream)
