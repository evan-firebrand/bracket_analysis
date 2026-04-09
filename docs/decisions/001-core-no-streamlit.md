# 001 — core/ has no Streamlit imports

## Status
Active

## Problem
If `core/` imported Streamlit, the business logic layer would become coupled to the UI framework. This makes unit testing harder (Streamlit requires a running app context), prevents reuse of core logic in CLI scripts or other interfaces, and makes it impossible to reason about scoring and scenario logic independently of the UI.

## Decision
`core/` contains only pure Python. No Streamlit imports anywhere in `core/`. Presentation logic — rendering, layout, widgets, charts — belongs exclusively in `analyses/` plugins or `app.py`.

## Consequences
- When writing new business logic (scoring, comparisons, scenarios, narrative), it goes in `core/` with no UI dependencies.
- When writing new UI (charts, tables, interactive controls), it goes in `analyses/` and calls into `core/`.
- `core/` functions can be called from CLI scripts (`scripts/`) and tests without any Streamlit context.
- If you find yourself wanting to import Streamlit in `core/`, that's a signal to split the function: put the logic in `core/` and the rendering in `analyses/`.

## Source
Established at project inception. Documented in CLAUDE.md "Key things to know" section. Enforced by the `plugin-attrs` review checklist rule.
