#!/usr/bin/env python3
"""Fetch a bracket from ESPN using Playwright DOM scraping (no Claude API needed).

Navigates to the ESPN Tournament Challenge group page, finds a member's
bracket, and extracts picks directly from the DOM.

Usage:
    python scripts/fetch_espn_bracket.py
    python scripts/fetch_espn_bracket.py --member "Rebecca" --headless false
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml
from playwright.sync_api import sync_playwright


def fetch_bracket(group_url: str, target_member: str, headless: bool = True) -> dict | None:
    """Navigate ESPN group page and extract a member's bracket picks via DOM."""

    print(f"  Launching browser (headless={headless})...")

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

        # Step 1: Navigate to group page
        print("  Navigating to group page...")
        try:
            page.goto(group_url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(5000)  # Wait for SPA to render
        except Exception as e:
            print(f"  Failed to load group page: {e}")
            browser.close()
            return None

        # Step 2: Find and click the target member's bracket
        print(f"  Looking for {target_member}'s bracket...")

        # Try clicking on the member name — ESPN uses various selectors
        clicked = False
        for selector in [
            f"text={target_member}",
            f"a:has-text('{target_member}')",
            f"[class*='entry'] >> text={target_member}",
            f"td >> text={target_member}",
            f"tr >> text={target_member}",
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=2000):
                    el.click()
                    clicked = True
                    print(f"  Clicked: {selector}")
                    break
            except Exception:
                continue

        if not clicked:
            print(f"  Could not find {target_member} on the page.")
            print("  Page text (first 2000 chars):")
            print(page.inner_text("body")[:2000])
            browser.close()
            return None

        # Wait for bracket page to load
        page.wait_for_timeout(5000)
        print("  Bracket page loaded. Extracting data...")

        # Step 3: Extract bracket data from the DOM
        # Dump the page content for analysis
        page_text = page.inner_text("body")
        page_html = page.content()

        # Save debug output
        debug_dir = Path("data/debug")
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / "bracket_text.txt").write_text(page_text)
        (debug_dir / "bracket_page.html").write_text(page_html)
        page.screenshot(path=str(debug_dir / "bracket_screenshot.png"))
        print("  Saved debug output to data/debug/")

        # Try to extract matchup data from the DOM
        # ESPN bracket pages typically have matchup containers with team names and seeds
        picks = {}

        # Look for common ESPN bracket element patterns
        matchup_selectors = [
            "[class*='matchup']",
            "[class*='Matchup']",
            "[class*='game']",
            "[class*='bracket']",
            "[data-testid*='matchup']",
        ]

        for selector in matchup_selectors:
            elements = page.locator(selector).all()
            if elements:
                print(f"  Found {len(elements)} elements with selector: {selector}")
                for i, el in enumerate(elements[:5]):
                    try:
                        print(f"    [{i}]: {el.inner_text()[:100]}")
                    except Exception:
                        pass

        # Also try extracting all team name elements
        team_selectors = [
            "[class*='team-name']",
            "[class*='TeamName']",
            "[class*='teamName']",
            "[class*='pick']",
            "[class*='Pick']",
            "[class*='winner']",
        ]

        for selector in team_selectors:
            elements = page.locator(selector).all()
            if elements:
                print(f"  Found {len(elements)} elements with selector: {selector}")
                for i, el in enumerate(elements[:5]):
                    try:
                        print(f"    [{i}]: {el.inner_text()[:100]}")
                    except Exception:
                        pass

        browser.close()

    if not picks:
        print("\n  Could not auto-extract picks from DOM.")
        print("  Check data/debug/bracket_text.txt and bracket_page.html")
        print("  to identify the right CSS selectors for this page.")
        return None

    return {
        "player_name": target_member,
        "entry_name": f"{target_member}'s Bracket",
        "picks": picks,
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch ESPN bracket via Playwright")
    parser.add_argument("--member", default=None, help="Member name to fetch")
    parser.add_argument("--headless", default=None, help="true/false")
    args = parser.parse_args()

    config_path = Path("config.yaml")
    if config_path.exists():
        config = yaml.safe_load(config_path.read_text())
        group_url = config.get("sources", {}).get("espn_group", "")
    else:
        group_url = ""

    if not group_url:
        print("Error: No ESPN group URL in config.yaml")
        sys.exit(1)

    target = args.member or "Rebecca"
    headless = args.headless != "false" if args.headless else True

    print(f"Fetching {target}'s bracket from ESPN group...")
    print(f"URL: {group_url}")

    data = fetch_bracket(group_url, target, headless)

    if data and data.get("picks"):
        # Save to player_brackets.json
        filepath = Path("data/entries/player_brackets.json")
        if filepath.exists():
            existing = json.loads(filepath.read_text())
        else:
            existing = {"entries": []}

        entries = [e for e in existing["entries"] if e.get("player_name") != target]
        entries.append(data)
        existing["entries"] = entries
        filepath.write_text(json.dumps(existing, indent=2))

        pick_count = len(data["picks"])
        print(f"\nDone! {pick_count} picks saved to: {filepath}")
    else:
        print("\nNo picks extracted. Review the debug output in data/debug/")
        print("You may need to adjust CSS selectors based on the page structure.")
        sys.exit(1)


if __name__ == "__main__":
    main()
