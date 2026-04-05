# CLAUDE.md — Agent Context for bracket_analysis

## What is this repo?

NCAA tournament bracket analysis app. Scores bracket picks, compares players head-to-head, runs scenario simulations (brute-force + Monte Carlo), and presents everything in a Streamlit web UI. Data collected from ESPN and DraftKings.

## Key things to know

- **Analysis layer**: `core/` contains pure Python scoring, scenario engines, comparisons, and data loading. No Streamlit imports.
- **Plugin system**: `analyses/` has auto-discovered Streamlit plugins (presentation only — business logic goes in `core/`).
- **Web UI**: `app.py` is the Streamlit entry point. Loads `AnalysisContext` and renders plugins.
- **Data contract**: `docs/DATA_CONTRACT.md` defines exact schemas. All data uses team slugs and slot IDs.
- **Data files**: `data/tournament.json`, `data/results.json`, `data/odds.json`, `data/entries/player_brackets.json` — tracked in git.
- **ESPN bracket fetching**: `src/extract_bracket.py` uses Playwright DOM extraction. Requires `ANTHROPIC_API_KEY`.
- **CI**: Ruff lint + pytest + PR validation on every PR to main.

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py                    # launch web UI
pytest                                  # run tests
ruff check .                            # lint
python scripts/validate_data.py         # validate data integrity
python scripts/run_scenarios.py         # CLI scenario analysis
python scripts/fetch_espn_bracket.py    # fetch bracket from ESPN (needs ANTHROPIC_API_KEY)
```

## How to extend

To add a new analysis plugin:
1. Create `analyses/<name>.py` with required attrs: `TITLE`, `DESCRIPTION`, `CATEGORY`, `ORDER`, `ICON`, `render(ctx)`
2. Put business logic in `core/` — plugins are presentation only
3. The plugin auto-discovers on app restart

To add a new data source:
1. Create a script in `scripts/`
2. Use `src/storage.py` for reading/writing data files
3. Follow schemas in `docs/DATA_CONTRACT.md`

## Project structure

```
core/scoring.py        — ESPN scoring (10/20/40/80/160/320 per round)
core/scenarios.py      — Brute-force + Monte Carlo scenario engines
core/tournament.py     — Game tree traversal, remaining slots, team paths
core/comparison.py     — H2H diffs, pick popularity, chalk scores
core/context.py        — Central data object (loads + caches everything)
core/loader.py         — Data loading + bracket tree validation
core/models.py         — Dataclasses (Team, GameSlot, Results, PlayerEntry, etc.)
core/narrative.py      — Template-based text descriptions
analyses/              — Auto-discovered Streamlit plugins (presentation only)
app.py                 — Streamlit web UI entry point
src/extract_bracket.py — ESPN bracket extraction via Playwright DOM
src/models.py          — Prompt schema helpers
src/storage.py         — JSON file read/write
scripts/               — CLI: validation, scenarios, bracket fetching, CI scripts
tests/                 — pytest test suite
docs/DATA_CONTRACT.md  — Data schemas
config.yaml            — Configuration
pyproject.toml         — pytest + ruff config
.github/workflows/     — CI pipeline (lint, test, PR validation, review checklist)
```

## Analysis integrity

**The scope of a claim must never exceed the scope of the evidence.**

When analysis is narrowed (e.g. comparing two players instead of the full pool), any conclusions must stay within that narrowed scope. Before publishing or presenting any finding:

1. **Label the scope.** State explicitly what was analyzed and what was excluded. "This compares Player A vs Player B only" means you cannot claim outcomes about the full leaderboard.
2. **Validate every claim against its evidence.** If a conclusion requires data outside the current scope (e.g. other players, other systems, other time periods), either widen the analysis or qualify the claim.
3. **Red-team before publishing.** Ask: "Is there a scenario where this claim is false?" If the answer requires context outside the analysis scope, the claim is leaking.
4. **Distinguish relative from absolute.** "A beats B" (relative, bilateral) is not the same as "A wins" (absolute, pool-wide). Use precise language.

This applies to all analysis — bracket comparisons, data summaries, narratives, dashboards. A correct number with the wrong framing is a wrong answer.

### Scope block (Layer 1)

Before presenting any analysis findings, output a scope block in the working conversation:

```
SCOPE: [what was analyzed]
EXCLUDED: [what was not analyzed]
CAN CLAIM: [conclusions the evidence supports]
CANNOT CLAIM: [conclusions that would require broader data]
```

This block is for the working conversation only — it does not appear in final deliverables (narratives, dashboards, plugin text). Its purpose is to make scope visible so both the agent and the user can catch leaking claims before they're published.

### Red-team review (Layer 2)

Before presenting any analysis narrative, summary, or data-driven text intended for an audience, launch a red-team sub-agent. The agent receives the draft text and the underlying data, and its sole job is to find claims that are false, overstated, or unsupported by the analysis scope. See `.claude/agents/red-team-reviewer.md` for the agent definition.

The invoker is responsible for providing a complete evidence packet — scope declaration, all supporting data, and the draft text. If the agent flags a claim as unsupported, either provide the missing evidence or cut the claim. The burden of proof is on the claimant, not the reviewer.

If the red-team agent finds issues, fix them before presenting to the user. If it passes clean, proceed.

## Important constraints

- Requires `ANTHROPIC_API_KEY` environment variable for ESPN bracket fetching (not needed for analysis/UI)
- ESPN is a JS SPA — bracket fetching uses Playwright DOM extraction
- CI requires `ruff check` + `pytest` to pass before merge
- PR descriptions must include 6 required sections (see PR conventions below)

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
