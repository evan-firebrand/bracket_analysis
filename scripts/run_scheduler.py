#!/usr/bin/env python3
"""Run the twice-daily scheduler for fetching results and odds."""

import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from src.browser import BrowserSession
from src.fetch_odds import fetch_odds
from src.fetch_results import fetch_results
from src.storage import save_odds, save_results


def fetch_and_save():
    """Run a single fetch cycle for results and odds."""
    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    results_url = config["results"]["url"]
    odds_url = config["odds"]["url"]
    headless = config["browser"]["headless"]
    width = config["browser"]["viewport_width"]
    height = config["browser"]["viewport_height"]
    model = config["anthropic"].get("model")
    data_dir = config.get("data_dir", "data")

    print("=== Scheduled fetch starting ===")

    with BrowserSession(headless=headless, width=width, height=height) as browser:
        # Results
        print("Fetching results...")
        results_data = fetch_results(results_url, browser, model, data_dir)
        if results_data and "results" in results_data:
            save_results(results_data, data_dir)
            print(f"  {len(results_data['results'])} completed games saved.")
        else:
            print("  Warning: results fetch failed.")

        # Odds
        print("Fetching odds...")
        odds_data = fetch_odds(odds_url, browser, model, data_dir)
        if odds_data and ("teams" in odds_data or "games" in odds_data):
            save_odds(odds_data, data_dir)
            count = len(odds_data.get('games', odds_data.get('teams', {})))
            print(f"  {count} odds entries saved.")
        else:
            print("  Warning: odds fetch failed.")

    print("=== Scheduled fetch complete ===\n")


def main():
    load_dotenv()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set. Create a .env file or export it.")
        sys.exit(1)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    schedule = config.get("schedule", {})
    times = schedule.get("results_times", ["08:00", "20:00"])
    tz = schedule.get("timezone", "US/Eastern")

    hours = ",".join(t.split(":")[0] for t in times)
    minutes = times[0].split(":")[1] if len(times) > 0 else "0"

    scheduler = BlockingScheduler()
    scheduler.add_job(
        fetch_and_save,
        "cron",
        hour=hours,
        minute=minutes,
        timezone=tz,
    )

    print(f"Scheduler started. Will fetch results + odds at {times} {tz}")
    print("Press Ctrl+C to stop.\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("Scheduler stopped.")


if __name__ == "__main__":
    main()
