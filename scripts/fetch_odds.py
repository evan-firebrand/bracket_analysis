#!/usr/bin/env python3
"""CLI: Fetch betting odds from DraftKings."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from dotenv import load_dotenv

from src.browser import BrowserSession
from src.fetch_odds import fetch_odds
from src.storage import save_odds


def main():
    load_dotenv()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set. Create a .env file or export it.")
        sys.exit(1)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    odds_url = config["odds"]["url"]
    headless = config["browser"]["headless"]
    width = config["browser"]["viewport_width"]
    height = config["browser"]["viewport_height"]
    model = config["anthropic"].get("model")
    data_dir = config.get("data_dir", "data")

    print(f"Fetching odds from: {odds_url}")
    print(f"Browser: headless={headless}, {width}x{height}")

    with BrowserSession(headless=headless, width=width, height=height) as browser:
        odds_data = fetch_odds(
            odds_url=odds_url,
            browser=browser,
            model=model,
            data_dir=data_dir,
        )

    if odds_data and ("games" in odds_data or "teams" in odds_data):
        path = save_odds(odds_data, data_dir=data_dir)
        count = len(odds_data.get("games", odds_data.get("teams", {})))
        print(f"Done! {count} odds entries saved to: {path}")
    else:
        print("Failed to fetch odds data.")
        sys.exit(1)


if __name__ == "__main__":
    main()
