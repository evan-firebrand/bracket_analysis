"""Tests for PR description validation."""

from __future__ import annotations

import sys
from pathlib import Path

# Add scripts to path so we can import validate_pr
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from validate_pr import validate_pr_body  # noqa: E402

VALID_PR_BODY = """## Requirements
User requested a new scoring algorithm for bracket analysis.
The algorithm should weight later rounds more heavily.

## Solution
Created core/scoring.py with weighted round multipliers.
Updated the leaderboard to use the new scoring function.

## Issues & Revisions
Initially implemented flat scoring (10 pts per correct pick).
Realized this didn't match the standard ESPN scoring format.
Revised to use 10/20/40/80/160/320 per round.

## Decisions
Chose ESPN-standard scoring over custom weights because users
expect familiar point values. Kept the multiplier configurable
in config.yaml for future flexibility.

## Testing
Added 8 new tests for scoring edge cases.
Total: 12 -> 20 tests, all passing.
Tested with both complete and partial bracket data.

## Scope
No scope creep. All requirements met.
Deferred: custom scoring profiles (not requested).

## Squash Commit
feat(scoring): add weighted round multipliers

ESPN-standard 10/20/40/80/160/320 scoring. Custom profiles deferred.
"""


class TestValidatePrBody:
    def test_valid_pr_body(self):
        errors, warnings = validate_pr_body(VALID_PR_BODY)
        assert errors == []
        assert warnings == []

    def test_empty_body(self):
        errors, warnings = validate_pr_body("")
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_none_body(self):
        errors, warnings = validate_pr_body(None)
        assert len(errors) == 1
        assert "empty" in errors[0].lower()

    def test_missing_section(self):
        body = VALID_PR_BODY.replace("## Scope", "## Other")
        errors, warnings = validate_pr_body(body)
        assert len(errors) == 1
        assert "Scope" in errors[0]

    def test_section_with_only_html_comment(self):
        body = VALID_PR_BODY.replace(
            "No scope creep. All requirements met.\nDeferred: custom scoring profiles (not requested).",
            "<!-- Was there scope creep? -->",
        )
        errors, warnings = validate_pr_body(body)
        assert any("Scope" in e and "empty" in e for e in errors)

    def test_section_with_content_and_comment(self):
        body = VALID_PR_BODY.replace(
            "No scope creep. All requirements met.",
            "<!-- Scope section -->\nNo scope creep. All requirements met.",
        )
        errors, warnings = validate_pr_body(body)
        assert errors == []

    def test_all_sections_missing(self):
        errors, warnings = validate_pr_body("Just some random text with no sections.")
        assert len(errors) == 7

    def test_thin_content_warns(self):
        body = VALID_PR_BODY.replace(
            "No scope creep. All requirements met.\nDeferred: custom scoring profiles (not requested).",
            "No issues.",
        )
        errors, warnings = validate_pr_body(body)
        assert errors == []
        assert any("Scope" in w for w in warnings)

    def test_rich_content_no_warning(self):
        errors, warnings = validate_pr_body(VALID_PR_BODY)
        assert warnings == []
