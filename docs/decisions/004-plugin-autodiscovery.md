# 004 — Plugin autodiscovery contract

## Status
Active

## Problem
Hardcoding plugin registrations in `app.py` would require every new analysis view to modify the entry point. This creates merge conflicts when multiple plugins are added in parallel and makes the plugin list a maintenance burden.

## Decision
`analyses/` plugins are auto-discovered at app startup. Any `.py` file in `analyses/` (except `__init__.py`) that defines all required module-level attributes is automatically loaded and rendered.

Required attributes (all must be present at module level):
- `TITLE` — display name shown in navigation
- `DESCRIPTION` — one-line summary shown in plugin listings
- `CATEGORY` — grouping label for sidebar organization
- `ORDER` — integer controlling sort position within a category
- `ICON` — emoji or string used in the sidebar
- `render(ctx)` — callable that takes an `AnalysisContext` and renders the Streamlit UI

## Consequences
- Adding a new analysis view requires only creating `analyses/<name>.py` with the required attrs — no changes to `app.py`.
- Missing any required attribute causes the plugin to fail to load at startup with a clear error.
- Plugins must not contain business logic. All computation goes in `core/`; plugins call into `core/` and render results.
- The `plugin-attrs` CI review checklist rule will prompt a check for required attrs when `analyses/` files change.

## Source
Established at project inception. Documented in CLAUDE.md "How to extend" section.
