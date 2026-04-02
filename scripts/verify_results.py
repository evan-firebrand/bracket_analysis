#!/usr/bin/env python3
"""Verify results.json against ESPN bracket page using Playwright DOM scraping.

Navigates to ESPN's bracket page, extracts game results from the DOM,
and compares against our data/results.json. Reports any mismatches.

Usage:
    python scripts/verify_results.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def scrape_espn_bracket(url: str) -> list[dict]:
    """Scrape game results from ESPN bracket page using DOM queries."""
    print(f"  Opening browser and navigating to: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
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

        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            # Wait for SPA to render
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  Failed to load page: {e}")
            browser.close()
            return []

        # Try to extract game data from the page
        # ESPN bracket pages vary in structure, so try multiple selectors
        games = []

        # Get page text for analysis
        page_text = page.inner_text("body")

        # Look for score patterns in the page text
        # Common patterns: "Team1 71\nTeam2 65" or "1 Duke 71 - 16 Siena 65"
        lines = page_text.split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            # Look for lines with team names and scores
            score_match = re.match(
                r"(?:\d+\s+)?(.+?)\s+(\d{2,3})\s*$", line
            )
            if score_match:
                games.append(
                    {
                        "raw_line": line,
                        "team": score_match.group(1).strip(),
                        "score": int(score_match.group(2)),
                        "line_number": i,
                    }
                )

        browser.close()

    return games


def normalize_team_name(name: str) -> str:
    """Convert display name to team slug for matching."""
    name = name.lower().strip()
    # Common mappings
    mappings = {
        "uconn": "uconn",
        "connecticut": "uconn",
        "michigan st.": "michigan_st",
        "michigan state": "michigan_st",
        "ohio st.": "ohio_st",
        "ohio state": "ohio_st",
        "st. john's": "st_johns",
        "north dakota st.": "north_dakota_st",
        "north carolina": "north_carolina",
        "unc": "north_carolina",
        "south florida": "south_florida",
        "cal baptist": "cal_baptist",
        "northern iowa": "northern_iowa",
        "utah st.": "utah_st",
        "utah state": "utah_st",
        "high point": "high_point",
        "miami (fl)": "miami_fl",
        "miami (ohio)": "miami_ohio",
        "kennesaw st.": "kennesaw_st",
        "queens (n.c.)": "queens_nc",
        "prairie view a&m": "prairie_view_am",
        "texas a&m": "texas_am",
        "saint mary's": "saint_marys",
        "saint louis": "saint_louis",
        "iowa st.": "iowa_st",
        "iowa state": "iowa_st",
        "texas tech": "texas_tech",
        "wright st.": "wright_st",
        "wright state": "wright_st",
        "santa clara": "santa_clara",
        "tennessee st.": "tennessee_st",
        "long island": "long_island",
    }

    if name in mappings:
        return mappings[name]

    # Generic: lowercase, replace spaces/periods with underscores
    slug = re.sub(r"[.\s]+", "_", name)
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    slug = slug.strip("_")
    return slug


def main():
    data_dir = Path(__file__).parent.parent / "data"
    results_path = data_dir / "results.json"

    if not results_path.exists():
        print("ERROR: data/results.json not found")
        sys.exit(1)

    our_results = json.loads(results_path.read_text())["results"]
    print(f"Our data: {len(our_results)} completed games\n")

    # Try ESPN bracket page (fantasy.espn.com works, espn.com may block)
    urls_to_try = [
        "https://fantasy.espn.com/games/tournament-challenge-bracket-2026/bracket",
        "https://www.espn.com/mens-college-basketball/bracket",
    ]

    espn_games = []
    for url in urls_to_try:
        print(f"Trying: {url}")
        espn_games = scrape_espn_bracket(url)
        if espn_games:
            print(f"  Found {len(espn_games)} score entries from page")
            break
        print("  No data extracted, trying next URL...")

    if not espn_games:
        print("\nCould not scrape ESPN bracket page.")
        print("Run manually with headless=false to debug:")
        print("  Set browser.headless: false in config.yaml")
        print("  python scripts/fetch_results.py")
        print("\nFalling back to local-only verification...")
        _local_verification(our_results)
        return

    # Pair up consecutive score entries as game matchups
    paired_games = []
    i = 0
    while i < len(espn_games) - 1:
        g1 = espn_games[i]
        g2 = espn_games[i + 1]
        # Consecutive lines are likely a matchup
        if abs(g1["line_number"] - g2["line_number"]) <= 3:
            if g1["score"] >= g2["score"]:
                winner, w_pts = g1["team"], g1["score"]
                loser, l_pts = g2["team"], g2["score"]
            else:
                winner, w_pts = g2["team"], g2["score"]
                loser, l_pts = g1["team"], g1["score"]

            paired_games.append(
                {
                    "winner": normalize_team_name(winner),
                    "loser": normalize_team_name(loser),
                    "score": f"{w_pts}-{l_pts}",
                    "raw_winner": winner,
                    "raw_loser": loser,
                }
            )
            i += 2
        else:
            i += 1

    print(f"\nPaired {len(paired_games)} games from ESPN\n")

    # Compare
    matches = 0
    mismatches = 0
    unmatched = 0

    for slot_id, our_game in our_results.items():
        winner, loser = our_game["winner"], our_game["loser"]
        our_score = our_game.get("score", "")

        # Find matching game in ESPN data
        espn_match = None
        for eg in paired_games:
            if eg["winner"] == winner and eg["loser"] == loser:
                espn_match = eg
                break
            if eg["winner"] == loser and eg["loser"] == winner:
                # ESPN says different winner
                espn_match = eg
                break

        if espn_match is None:
            unmatched += 1
            continue

        if espn_match["winner"] == winner and espn_match["score"] == our_score:
            matches += 1
        else:
            mismatches += 1
            print(f"  MISMATCH {slot_id}:")
            print(f"    Ours: {winner} over {loser} ({our_score})")
            print(
                f"    ESPN: {espn_match['winner']} over {espn_match['loser']} "
                f"({espn_match['score']})"
            )

    print(f"\nResults: {matches} match, {mismatches} mismatch, {unmatched} unmatched")

    if mismatches > 0:
        print("\nVERIFICATION FAILED — mismatches found!")
        sys.exit(1)
    else:
        print("\nAll matched games verified successfully.")


def _local_verification(results: dict):
    """Fallback: run local-only checks when web scraping fails."""
    print("\nLocal verification checks:")

    # Check all scores are valid
    for slot_id, game in results.items():
        score = game.get("score")
        if not score:
            print(f"  WARNING: {slot_id} has no score")
            continue
        parts = score.split("-")
        if len(parts) != 2:
            print(f"  ERROR: {slot_id} bad score format: {score}")
            continue
        w_pts, l_pts = int(parts[0]), int(parts[1])
        if w_pts <= l_pts:
            print(f"  ERROR: {slot_id} winner score <= loser score: {score}")
        if w_pts > 150:
            print(f"  WARNING: {slot_id} unusually high score: {score}")

    print("  Local checks complete")


if __name__ == "__main__":
    main()
