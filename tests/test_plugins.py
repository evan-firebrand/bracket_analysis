"""Tests for the plugin auto-discovery system."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyses import discover_plugins, get_plugins_by_category


class TestPluginDiscovery:
    def test_discovers_built_in_plugins(self):
        plugins = discover_plugins()
        names = [p.name for p in plugins]
        assert "leaderboard" in names
        assert "my_bracket" in names

    def test_plugins_have_required_attrs(self):
        plugins = discover_plugins()
        for plugin in plugins:
            assert plugin.title
            assert plugin.description
            assert plugin.category
            assert plugin.order > 0
            assert plugin.icon
            assert callable(plugin.render)

    def test_plugins_sorted_by_category_then_order(self):
        plugins = discover_plugins()
        # Standings should come before my_bracket
        standings_idx = next(
            i for i, p in enumerate(plugins) if p.category == "standings"
        )
        my_bracket_idx = next(
            i for i, p in enumerate(plugins) if p.category == "my_bracket"
        )
        assert standings_idx < my_bracket_idx

    def test_group_by_category(self):
        plugins = discover_plugins()
        grouped = get_plugins_by_category(plugins)
        assert "standings" in grouped
        assert "my_bracket" in grouped
        assert len(grouped["standings"]) >= 1
        assert len(grouped["my_bracket"]) >= 1
