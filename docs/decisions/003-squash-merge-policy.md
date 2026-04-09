# 003 — Squash merge policy

## Status
Active

## Problem
In PR #9, a squash merge to `main` caused real tournament data to be silently lost. The squash collapsed multiple commits into one, and the merge resolved in a way that dropped data-carrying commits from the history. The loss wasn't caught until after merge because the squash obscured what had changed.

## Decision
All PRs merge to `main` via squash merge. This is a deliberate tradeoff: a linear, readable `git log` on `main` at the cost of intra-PR commit granularity not being preserved in the branch history.

The consequence is that **PR descriptions are the canonical record of implementation decisions, what was tried, and what was deferred.** The squash commit on `main` contains only the PR title. `git log` alone is not sufficient to understand why a change was made — the PR description must be read for full context.

To partially mitigate this: when squash-merging on GitHub, fill in the commit body (the second text box in the merge UI) with 2-3 lines summarizing key decisions and deferrals. This makes `git log` more useful without requiring GitHub access.

## Consequences
- `git log --oneline` gives a clean feature-by-feature history — one line per merged PR.
- Full context (decisions, issues, revisions, scope) requires reading the PR description on GitHub.
- Agents starting a session should treat PR descriptions as primary documentation, not supplementary.
- `git bisect` and blame are less granular — a bug introduced across multiple commits within a PR appears as one commit on `main`.

## Source
Policy established after the data loss incident in PR #9 ("Restore real tournament data lost in PR #8 squash merge"). The squash convention was implicit before that; the lesson from #9 made it explicit.
