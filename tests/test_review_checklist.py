"""Tests for diff-aware review checklist generation."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from review_checklist import generate_checklist  # noqa: E402


class TestGenerateChecklist:
    def test_core_change_triggers_test_reminder(self):
        items = generate_checklist(["core/scoring.py"])
        assert any("tests" in item.lower() for item in items)

    def test_data_contract_triggers_sync_reminder(self):
        items = generate_checklist(["docs/DATA_CONTRACT.md"])
        assert any("core/models.py" in item for item in items)
        assert any("src/models.py" in item for item in items)

    def test_plugin_change_triggers_attrs_reminder(self):
        items = generate_checklist(["analyses/leaderboard.py"])
        assert any("TITLE" in item for item in items)

    def test_plugin_init_does_not_trigger_attrs(self):
        items = generate_checklist(["analyses/__init__.py"])
        assert not any("TITLE" in item for item in items)

    def test_config_triggers_docs_reminder(self):
        items = generate_checklist(["config.yaml"])
        assert any("README.md" in item for item in items)

    def test_unrelated_file_triggers_nothing(self):
        items = generate_checklist(["README.md"])
        assert items == []

    def test_no_duplicate_rules(self):
        items = generate_checklist(["core/scoring.py", "core/loader.py", "core/models.py"])
        # "core-tests" rule should only appear once
        test_items = [i for i in items if "update or add tests" in i]
        assert len(test_items) == 1

    def test_ai_layer_change_triggers_ai_test_reminder(self):
        items = generate_checklist(["core/ai/agent.py"])
        assert any("test_ai_" in item for item in items)

    def test_empty_input(self):
        items = generate_checklist([])
        assert items == []
