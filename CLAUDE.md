# CLAUDE.md — Agent Context for bracket_analysis

## What is this repo?

NCAA tournament bracket analysis app. Scores bracket picks, compares players head-to-head, runs scenario simulations (brute-force + Monte Carlo), and presents everything in a Streamlit web UI.

## Key things to know

- **Analysis layer**: `core/` contains pure Python scoring, scenario engines, comparisons, and data loading. No Streamlit imports.
- **Plugin system**: `analyses/` has auto-discovered Streamlit plugins (presentation only — business logic goes in `core/`).
- **Web UI**: `app.py` is the Streamlit entry point. Loads `AnalysisContext` and renders plugins.
- **Data contract**: `docs/DATA_CONTRACT.md` defines exact schemas. All data uses team slugs and slot IDs.
- **Data files**: `data/tournament.json`, `data/results.json`, `data/odds.json`, `data/entries/player_brackets.json` — tracked in git.
- **CI**: Ruff lint + pytest + PR validation on every PR to main.

## How to run

```bash
pip install -r requirements.txt
streamlit run app.py                    # launch web UI
pytest                                  # run tests
ruff check .                            # lint
python scripts/validate_data.py         # validate data integrity
python scripts/run_scenarios.py         # CLI scenario analysis
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
src/storage.py         — JSON file read/write
scripts/               — CLI: validation, scenarios, CI scripts
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

### Analysis workflow (Layer 2)

When producing any analysis narrative, summary, or data-driven text intended for an audience, follow this sequence:

**Step 1: Assemble the evidence packet first.** Before writing a single sentence of narrative, compile all supporting data: scores, scenarios, pick breakdowns, seedings, round-by-round results — everything a claim might need. If you're going to reference it, document it. You cannot claim what you haven't documented.

**Step 2: Write the narrative constrained by the evidence.** Every factual claim must trace to something in the evidence packet. If it's not in the packet, don't write it.

**Step 3: Self-review against the scope block.** Walk through every claim in the draft and check: (a) is this in the "CAN CLAIM" list? (b) does the evidence packet contain the supporting data? (c) is any conditional claim stated with its conditions? Fix issues before proceeding.

**Step 4: Red-team review.** Launch the red-team sub-agent (`.claude/agents/red-team-reviewer.md`) with the scope declaration, complete evidence packet, and draft text. The agent's sole job is to find claims that are false, overstated, or unsupported. The invoker is responsible for the completeness of the evidence packet. If the agent flags a claim as unsupported, either provide the missing evidence or cut the claim. The burden of proof is on the claimant, not the reviewer.

**Target: one self-review + one red-team pass = done.** If the red-team finds issues that a self-review should have caught (basic scope leaks, unverified claims, arithmetic errors), that's a process failure — not a reason for another loop.

## Git workflow

- **Branch strategy**: Never commit directly to `main`. One branch per feature/fix.
  - Branch naming: `feature/<short-desc>`, `fix/<short-desc>`
  - `main` is protected: CI must pass + branch must be up to date before merging
- **Commit messages**: Imperative mood, scoped — `fix(scoring): handle bye-week teams in round 1`
  - Type prefixes: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
- **Commit hygiene**: One logical change per commit. Stage specific files, not `git add -A`.
- **Before pushing**: Always run `ruff check . && pytest` locally first.
- **Keeping branches fresh**: `git fetch origin && git rebase origin/main` (rebase, not merge)

## Claude Code session discipline

- **One session = one atomic change** — one PR, one logical unit (no "fix X AND add Y")
- State the goal explicitly at the start of each session
- Confirm which branch you're on before any work begins: `git status`
- Review staged changes before Claude commits: `git diff --staged`
- If scope creeps mid-session, stop and open a separate branch for the secondary change
- The PR title should not require the word "and" — if it does, split it

## Important constraints

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

## Deployment

- **Hosting**: Streamlit Community Cloud (free, no credit card required)
  - Connect GitHub repo → auto-deploys on push to `main`
  - Apps sleep after 7 days of inactivity; restart automatically on next visit
- **CI/CD**: GitHub Actions (configured in `.github/workflows/`)
  - `lint-and-test`: runs ruff + pytest on every push/PR
  - `validate-pr`: hard-fails if any of the 6 PR description sections are missing or empty
  - `review-checklist`: posts advisory comments based on which files changed
  - Always fix CI locally before pushing: `ruff check . && pytest`
