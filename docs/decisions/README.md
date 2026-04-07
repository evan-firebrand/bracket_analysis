# Architecture Decision Records (ADRs)

This folder documents the structural constraints and design decisions for the bracket_analysis project. Each ADR captures a rule, why it exists, and what it means day-to-day.

## Why ADRs?

Architectural constraints often live only in PR descriptions or tribal knowledge. ADRs make them searchable from the repo so new agents and contributors can find the "why" without digging through git history.

## Format

Each ADR follows this structure:

```markdown
# 00N — Title

## Status
Active | Superseded | Deprecated

## Problem
What would go wrong without this constraint?

## Decision
The rule, stated plainly.

## Consequences
What this means for agents and contributors day-to-day.

## Source
Where this was established — PR number, commit, or original design decision.
```

## Adding a new ADR

1. Use the next sequential number (`00N`)
2. File name: `00N-short-description.md`
3. Fill all five sections — no empty sections
4. If a new decision supersedes an old one, update the old ADR's Status to `Superseded` and reference the new ADR number

## Index

| # | Title | Status |
|---|---|---|
| 001 | core/ has no Streamlit imports | Active |
| 002 | comparison imports from scenarios, not the reverse | Active |
| 003 | Squash merge policy | Active |
| 004 | Plugin autodiscovery contract | Active |
| 005 | Data files tracked in git | Active |
