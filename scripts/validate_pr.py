#!/usr/bin/env python3
"""Validate that a PR description contains all required sections with real content."""

from __future__ import annotations

import os
import re
import sys

REQUIRED_SECTIONS = [
    "Requirements",
    "Solution",
    "Issues & Revisions",
    "Decisions",
    "Testing",
    "Scope",
    "Squash Commit",
]

MIN_LINES_FOR_DETAIL = 2


def validate_pr_body(body: str) -> tuple[list[str], list[str]]:
    """Validate PR body has all required sections filled in.

    Returns:
        (errors, warnings) where errors block merge and warnings are advisory.
    """
    errors: list[str] = []
    warnings: list[str] = []

    if not body or not body.strip():
        return ["PR body is empty"], []

    for section in REQUIRED_SECTIONS:
        pattern = rf"^##\s+{re.escape(section)}\s*$"
        match = re.search(pattern, body, re.MULTILINE)

        if not match:
            errors.append(f"Missing required section: '## {section}'")
            continue

        # Extract content between this header and the next ## header (or end)
        start = match.end()
        next_header = re.search(r"^##\s+", body[start:], re.MULTILINE)
        content = body[start : start + next_header.start()] if next_header else body[start:]

        # Strip HTML comments and whitespace
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        content = content.strip()

        if not content:
            errors.append(f"Section '## {section}' is empty (placeholder comments don't count)")
            continue

        # Check for thin content (advisory only)
        content_lines = [line for line in content.splitlines() if line.strip()]
        if len(content_lines) < MIN_LINES_FOR_DETAIL:
            warnings.append(
                f"Section '## {section}' has only {len(content_lines)} line(s) — consider adding more detail"
            )

    return errors, warnings


def main() -> None:
    body = os.environ.get("PR_BODY", "")
    if not body and not sys.stdin.isatty():
        body = sys.stdin.read()

    errors, warnings = validate_pr_body(body)

    if errors:
        print("PR description validation FAILED:")
        for err in errors:
            print(f"  ✗ {err}")

    if warnings:
        # Warnings go to stderr so CI can capture them separately
        for warn in warnings:
            print(f"  ⚠ {warn}", file=sys.stderr)

    if not errors and not warnings:
        print("PR description validation passed.")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
