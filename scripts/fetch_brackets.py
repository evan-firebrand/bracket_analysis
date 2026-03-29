#!/usr/bin/env python3
"""CLI: Fetch bracket picks from ESPN."""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml
from dotenv import load_dotenv
from src.browser import BrowserSession
from src.fetch_bracket import fetch_espn_bracket
from src.storage import save_bracket


def main():
    load_dotenv()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set. Create a .env file or export it.")
        sys.exit(1)

    with open("config.yaml") as f:
        config = yaml.safe_load(f)

    espn = config["espn_group"]
    group_url = espn["url"]
    target = espn.get("target_member", "Rebecca")
    headless = config["browser"]["headless"]
    width = config["browser"]["viewport_width"]
    height = config["browser"]["viewport_height"]
    model = config["anthropic"].get("model")
    data_dir = config.get("data_dir", "data")

    print(f"Fetching {target}'s bracket from ESPN group...")
    print(f"Group URL: {group_url}")
    print(f"Browser: headless={headless}, {width}x{height}")

    with BrowserSession(headless=headless, width=width, height=height) as browser:
        data = fetch_espn_bracket(
            group_url=group_url,
            target_member=target,
            browser=browser,
            model=model,
        )

    if data:
        entry_id = target.lower().replace(" ", "_")
        path = save_bracket(data, source="espn", entry_id=entry_id, data_dir=data_dir)
        print(f"Done! Bracket saved to: {path}")
    else:
        print("Failed to fetch bracket data.")
        sys.exit(1)


if __name__ == "__main__":
    main()
