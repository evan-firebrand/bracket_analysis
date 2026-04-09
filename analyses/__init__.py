"""Plugin auto-discovery system for analysis modules.

Each .py file in the analyses/ directory (except __init__.py) is a plugin.
Plugins must define: TITLE, DESCRIPTION, CATEGORY, ORDER, ICON, render(ctx).
Optionally: summarize(ctx) -> str | None.
"""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Category display order and labels
CATEGORY_ORDER = ["standings", "my_bracket", "matchups", "scenarios", "stories", "ai"]
CATEGORY_LABELS = {
    "standings": "Standings",
    "my_bracket": "My Bracket",
    "matchups": "Matchups",
    "scenarios": "Scenarios",
    "stories": "Stories & Insights",
    "ai": "Ask Claude",
}

REQUIRED_ATTRS = ["TITLE", "DESCRIPTION", "CATEGORY", "ORDER", "ICON", "render"]


@dataclass
class Plugin:
    name: str  # module name
    title: str
    description: str
    category: str
    order: int
    icon: str
    render: Callable
    summarize: Callable | None = None


def discover_plugins() -> list[Plugin]:
    """Scan the analyses/ directory and load all valid plugins."""
    plugins = []
    package_path = str(Path(__file__).parent)

    for _importer, modname, _ispkg in pkgutil.iter_modules([package_path]):
        if modname.startswith("_"):
            continue

        try:
            module = importlib.import_module(f"analyses.{modname}")
        except Exception as e:
            print(f"Warning: Failed to import plugin '{modname}': {e}")
            continue

        # Validate required attributes
        missing = [attr for attr in REQUIRED_ATTRS if not hasattr(module, attr)]
        if missing:
            print(
                f"Warning: Plugin '{modname}' missing required attributes: {missing}"
            )
            continue

        plugins.append(Plugin(
            name=modname,
            title=module.TITLE,
            description=module.DESCRIPTION,
            category=module.CATEGORY,
            order=module.ORDER,
            icon=module.ICON,
            render=module.render,
            summarize=getattr(module, "summarize", None),
        ))

    # Sort by category order, then by plugin order within category
    def sort_key(p: Plugin) -> tuple[int, int]:
        cat_idx = (
            CATEGORY_ORDER.index(p.category)
            if p.category in CATEGORY_ORDER
            else len(CATEGORY_ORDER)
        )
        return (cat_idx, p.order)

    plugins.sort(key=sort_key)
    return plugins


def get_plugins_by_category(plugins: list[Plugin]) -> dict[str, list[Plugin]]:
    """Group plugins by category, maintaining order."""
    grouped: dict[str, list[Plugin]] = {}
    for plugin in plugins:
        grouped.setdefault(plugin.category, []).append(plugin)
    return grouped
