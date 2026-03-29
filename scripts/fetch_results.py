#!/usr/bin/env python3
"""CLI: Fetch game results and odds from ESPN."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from dotenv import load_dotenv
from src.browser import BrowserSession
from src.fetch_results import fetch_results
from src.fetch_odds import fetch_odds
from src.storage import save_results, save_odds


def main():
    load_dotenv()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set. Create a .env file or export it.")
        sys.exit(1)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    results_url = config["results"]["url"]
    odds_url = config["odds"]["url"]
    headless = config["browser"]["headless"]
    width = config["browser"]["viewport_width"]
    height = config["browser"]["viewport_height"]
    model = config["anthropic"].get("model")
    data_dir = config.get("data_dir", "data")

    with BrowserSession(headless=headless, width=width, height=height) as browser:
        # Fetch game results
        print(f"Fetching game results from: {results_url}")
        results_data = fetch_results(
            results_url=results_url,
            browser=browser,
            model=model,
            data_dir=data_dir,
        )

        if results_data and "results" in results_data:
            path = save_results(results_data, data_dir=data_dir)
            game_count = len(results_data["results"])
            print(f"Results saved ({game_count} completed games): {path}")
        else:
            print("Warning: Failed to fetch results.")

        # Fetch odds
        print(f"\nFetching odds from: {odds_url}")
        odds_data = fetch_odds(
            odds_url=odds_url,
            browser=browser,
            model=model,
            data_dir=data_dir,
        )

        if odds_data and "teams" in odds_data:
            path = save_odds(odds_data, data_dir=data_dir)
            team_count = len(odds_data["teams"])
            print(f"Odds saved ({team_count} teams): {path}")
        else:
            print("Warning: Failed to fetch odds.")

    if not results_data and not odds_data:
        sys.exit(1)

    print("\nDone!")


if __name__ == "__main__":
    main()
