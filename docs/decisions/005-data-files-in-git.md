# 005 — Data files tracked in git

## Status
Active

## Problem
The app needs a reliable, versioned source of tournament data, player brackets, results, and odds. A database would add infrastructure complexity (setup, credentials, migrations) that is out of scope for a small pool analysis app. External APIs (ESPN, DraftKings) are scraped and may change without notice.

## Decision
The four canonical data files are tracked directly in git as the live data source:

- `data/tournament.json` — bracket structure, teams, seeds, regions
- `data/results.json` — game outcomes as they happen
- `data/odds.json` — Vegas win probabilities from DraftKings
- `data/entries/player_brackets.json` — all player picks

Updates to these files are committed to `main` as the tournament progresses. There is no separate database layer.

## Consequences
- All data is readable by any tool that can read files — no database client needed.
- `git log data/results.json` gives a history of every result update.
- Data integrity is validated by `python scripts/validate_data.py` — run this after any manual data edit.
- Schemas are defined in `docs/DATA_CONTRACT.md` — all data must conform.
- Data updates should be committed on their own (or with the script that produced them), not mixed into feature PRs.
- This approach scales for a small pool (~10 players, 63 games). It is not appropriate for larger datasets.

## Source
Established at project inception. Documented in CLAUDE.md "Key things to know" and `docs/DATA_CONTRACT.md`.
