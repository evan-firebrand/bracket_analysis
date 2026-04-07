#!/usr/bin/env python3
"""Generate a diff-aware review checklist based on which files changed in a PR.

Reads changed file paths from the CHANGED_FILES env var (newline-separated)
or stdin. Outputs a markdown checklist of relevant review reminders.
"""

from __future__ import annotations

import os
import sys

# Each rule: (name, file_match function, checklist item)
RULES: list[tuple[str, callable, str]] = [
    (
        "core-tests",
        lambda f: f.startswith("core/") and f.endswith(".py"),
        "Changes in `core/` — did you update or add tests in `tests/`?",
    ),
    (
        "data-contract-sync",
        lambda f: f in ("core/models.py", "docs/DATA_CONTRACT.md"),
        "Data models or contract changed — are `core/models.py` and `docs/DATA_CONTRACT.md` still in sync?",
    ),
    (
        "prompt-schema-sync",
        lambda f: f in ("docs/DATA_CONTRACT.md", "src/models.py"),
        "Data contract or prompt schemas changed — do `src/models.py` prompts still match `docs/DATA_CONTRACT.md`?",
    ),
    (
        "scoring-tests",
        lambda f: f == "core/scoring.py",
        "Scoring logic changed — did you update `tests/test_scoring.py`?",
    ),
    (
        "plugin-attrs",
        lambda f: f.startswith("analyses/") and f.endswith(".py") and f != "analyses/__init__.py",
        "Analysis plugin changed — does it have all required attrs"
        " (TITLE, DESCRIPTION, CATEGORY, ORDER, ICON, render)?",
    ),
    (
        "pr-validation-sync",
        lambda f: f == "scripts/validate_pr.py",
        "PR validation changed — did you update `.github/PULL_REQUEST_TEMPLATE.md` and `CLAUDE.md` to match?",
    ),
    (
        "config-docs",
        lambda f: f == "config.yaml",
        "Config changed — did you document new keys in `README.md` or `CLAUDE.md`?",
    ),
    (
        "claude-md-sync",
        lambda f: (f.startswith("core/") and f.endswith(".py"))
        or f.startswith("analyses/")
        or f == "docs/DATA_CONTRACT.md",
        "Architecture may have changed — did you update `CLAUDE.md` and/or add a `docs/decisions/` ADR?",
    ),
    (
        "adr-status",
        lambda f: f.startswith("docs/decisions/") and f.endswith(".md") and "README" not in f,
        "ADR changed — is the `## Status` field set correctly (Active / Superseded / Deprecated)?",
    ),
]


def generate_checklist(changed_files: list[str]) -> list[str]:
    """Return checklist items triggered by the changed files."""
    triggered: list[str] = []
    seen_rules: set[str] = set()

    for filepath in changed_files:
        filepath = filepath.strip()
        if not filepath:
            continue
        for rule_name, match_fn, message in RULES:
            if rule_name not in seen_rules and match_fn(filepath):
                triggered.append(message)
                seen_rules.add(rule_name)

    return triggered


def format_checklist(items: list[str]) -> str:
    """Format checklist items as a markdown comment body."""
    lines = ["### Review Checklist", ""]
    lines.append("Based on the files changed in this PR:")
    lines.append("")
    for item in items:
        lines.append(f"- [ ] {item}")
    return "\n".join(lines)


def main() -> None:
    raw = os.environ.get("CHANGED_FILES", "")
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read()

    changed_files = [f for f in raw.strip().splitlines() if f.strip()]

    if not changed_files:
        print("No changed files provided.")
        return

    items = generate_checklist(changed_files)

    if not items:
        print("No review checklist items triggered.")
        return

    output = format_checklist(items)
    print(output)


if __name__ == "__main__":
    main()
