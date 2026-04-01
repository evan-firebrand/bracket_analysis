#!/usr/bin/env python3
"""Fetch multiple brackets from ESPN in a single browser session.

Navigates to the ESPN group page, clicks each member's bracket,
dumps debug output, extracts picks, and saves to player_brackets.json.

Usage:
    python scripts/fetch_batch_brackets.py --headless false
    python scripts/fetch_batch_brackets.py --members "Hugh452871778,tvenie's Picks 1"
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml
from playwright.sync_api import Page, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.extract_bracket import parse_picks_from_text, validate_bracket_tree


def slugify(name: str) -> str:
    """Convert member name to filesystem-safe string."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_").lower()


def dump_bracket_page(page: Page, member_name: str, debug_dir: Path) -> str | None:
    """Dump the current bracket page text/HTML/screenshot. Returns page text."""
    member_dir = debug_dir / slugify(member_name)
    member_dir.mkdir(parents=True, exist_ok=True)

    page_text = page.inner_text("body")
    page_html = page.content()

    (member_dir / "bracket_text.txt").write_text(page_text, encoding="utf-8")
    (member_dir / "bracket_page.html").write_text(page_html, encoding="utf-8")
    page.screenshot(path=str(member_dir / "bracket_screenshot.png"))
    print(f"    Saved debug output to {member_dir}/")
    return page_text


def click_member(page: Page, member_name: str) -> bool:
    """Find and click a member's bracket entry on the group page."""
    # The member names on ESPN group pages can be entry names or display names.
    # Try multiple selector strategies.
    for selector in [
        f"text={member_name}",
        f"a:has-text('{member_name}')",
        f"[class*='entry'] >> text={member_name}",
        f"td >> text={member_name}",
        f"tr >> text={member_name}",
    ]:
        try:
            el = page.locator(selector).first
            if el.is_visible(timeout=2000):
                # Scroll into view first
                el.scroll_into_view_if_needed()
                page.wait_for_timeout(500)
                el.click()
                print(f"    Clicked: {selector}")
                return True
        except Exception:
            continue
    return False


def scroll_to_find_member(page: Page, member_name: str, max_scrolls: int = 10) -> bool:
    """Scroll down on the group page to find a member, then click."""
    # First try without scrolling
    if click_member(page, member_name):
        return True

    # Scroll down to load more members
    for i in range(max_scrolls):
        page.evaluate("window.scrollBy(0, 600)")
        page.wait_for_timeout(1000)
        if click_member(page, member_name):
            return True

    return False


def fetch_all_brackets(
    group_url: str,
    members: list[str],
    headless: bool = True,
    debug_dir: Path = Path("data/debug"),
) -> dict[str, dict]:
    """Fetch multiple brackets in one browser session.

    Returns {member_name: {player_name, entry_name, picks}} for successful extractions.
    """
    tournament_path = Path("data/tournament.json")
    tournament = json.loads(tournament_path.read_text(encoding="utf-8"))

    results = {}

    print(f"Launching browser (headless={headless})...")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        )
        page = browser.new_page(
            viewport={"width": 1280, "height": 800},
            user_agent=ua,
        )

        for i, member in enumerate(members):
            print(f"\n[{i+1}/{len(members)}] Fetching: {member}")

            # Navigate to group page
            print("  Navigating to group page...")
            try:
                page.goto(group_url, wait_until="domcontentloaded", timeout=45000)
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  Failed to load group page: {e}")
                continue

            # Find and click the member
            print(f"  Looking for '{member}'...")
            if not scroll_to_find_member(page, member):
                print(f"  ERROR: Could not find '{member}' on the group page.")
                print("  Page text (first 2000 chars):")
                print(page.inner_text("body")[:2000])
                continue

            # Wait for bracket to load
            page.wait_for_timeout(5000)
            print("  Bracket page loaded.")

            # Dump debug output
            page_text = dump_bracket_page(page, member, debug_dir)
            if not page_text:
                print(f"  ERROR: Failed to dump bracket page for '{member}'.")
                continue

            # Extract picks
            print("  Extracting picks...")
            picks = parse_picks_from_text(page_text, tournament)

            if not picks:
                print(f"  ERROR: No picks extracted for '{member}'.")
                continue

            # Determine player name from the page text
            # ESPN shows "Name's Picks N" or "Name's Bracket" at the top
            player_name = member  # fallback
            entry_name = member

            # Try to extract from page text header
            lines = page_text.split("\n")
            for line in lines[20:40]:  # bracket name is usually near the top
                stripped = line.strip()
                if stripped and ("Picks" in stripped or "Bracket" in stripped):
                    entry_name = stripped
                    # Extract player name (before "'s")
                    if "'s " in stripped:
                        player_name = stripped.split("'s ")[0]
                    break

            # Validate bracket tree
            errors = validate_bracket_tree(picks, tournament)
            if errors:
                print(f"  WARNING: {len(errors)} bracket tree violations:")
                for e in errors:
                    print(f"    {e}")

            print(f"  Extracted {len(picks)} picks for {player_name}")
            if len(picks) != 63:
                print(f"  WARNING: Expected 63 picks, got {len(picks)}")

            results[member] = {
                "player_name": player_name,
                "entry_name": entry_name,
                "picks": picks,
            }

        browser.close()

    return results


def save_to_player_brackets(results: dict[str, dict], data_dir: str = "data"):
    """Merge extracted brackets into player_brackets.json."""
    filepath = Path(data_dir) / "entries" / "player_brackets.json"
    if filepath.exists():
        existing = json.loads(filepath.read_text(encoding="utf-8"))
    else:
        existing = {"entries": []}

    for member, data in results.items():
        # Remove existing entry for this player
        existing["entries"] = [
            e for e in existing["entries"]
            if e.get("player_name") != data["player_name"]
        ]
        existing["entries"].append(data)

    filepath.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"\nSaved {len(results)} brackets to {filepath}")
    print(f"Total entries in file: {len(existing['entries'])}")


def main():
    parser = argparse.ArgumentParser(description="Fetch multiple ESPN brackets")
    parser.add_argument("--headless", default=None, help="true/false")
    parser.add_argument(
        "--members",
        default=None,
        help="Comma-separated list of member names to fetch",
    )
    args = parser.parse_args()

    config_path = Path("config.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text())
        group_url = config.get("espn_group", {}).get("url", "")
        if not group_url:
            group_url = config.get("sources", {}).get("espn_group", "")
    else:
        print("Error: config.yaml not found")
        sys.exit(1)

    if not group_url:
        print("Error: No ESPN group URL in config.yaml")
        sys.exit(1)

    headless = args.headless != "false" if args.headless else True

    if args.members:
        members = [m.strip() for m in args.members.split(",")]
    else:
        members = [
            "Hugh452871778",
            "Hugh1778",
            "tvenie's Picks 1",
            "Elizabeth's Picks",
            "scrapr's Picks 1",
        ]

    print(f"Group URL: {group_url}")
    print(f"Members to fetch: {members}")
    print(f"Headless: {headless}")

    results = fetch_all_brackets(group_url, members, headless)

    if results:
        save_to_player_brackets(results)

        # Also save individual debug extractions
        for member, data in results.items():
            out_path = Path("data/entries") / f"{slugify(member)}_extracted.json"
            out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            print(f"  Individual: {out_path}")
    else:
        print("\nNo brackets extracted.")
        sys.exit(1)


if __name__ == "__main__":
    main()
