#!/usr/bin/env python3
"""One-off script to fetch Rebecca's bracket from ESPN.

Uses Claude computer use API with Playwright to navigate the ESPN
Tournament Challenge group page and extract bracket picks.

Usage:
    ANTHROPIC_API_KEY=sk-ant-... python scripts/fetch_espn_bracket.py
"""

import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import anthropic
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Valid slot IDs for a 64-team bracket
VALID_SLOT_IDS = [
    "r1_east_1v16", "r1_east_8v9", "r1_east_5v12", "r1_east_4v13",
    "r1_east_6v11", "r1_east_3v14", "r1_east_7v10", "r1_east_2v15",
    "r1_west_1v16", "r1_west_8v9", "r1_west_5v12", "r1_west_4v13",
    "r1_west_6v11", "r1_west_3v14", "r1_west_7v10", "r1_west_2v15",
    "r1_south_1v16", "r1_south_8v9", "r1_south_5v12", "r1_south_4v13",
    "r1_south_6v11", "r1_south_3v14", "r1_south_7v10", "r1_south_2v15",
    "r1_midwest_1v16", "r1_midwest_8v9", "r1_midwest_5v12", "r1_midwest_4v13",
    "r1_midwest_6v11", "r1_midwest_3v14", "r1_midwest_7v10", "r1_midwest_2v15",
    "r2_east_1", "r2_east_2", "r2_east_3", "r2_east_4",
    "r2_west_1", "r2_west_2", "r2_west_3", "r2_west_4",
    "r2_south_1", "r2_south_2", "r2_south_3", "r2_south_4",
    "r2_midwest_1", "r2_midwest_2", "r2_midwest_3", "r2_midwest_4",
    "r3_east_1", "r3_east_2", "r3_west_1", "r3_west_2",
    "r3_south_1", "r3_south_2", "r3_midwest_1", "r3_midwest_2",
    "r4_east_1", "r4_west_1", "r4_south_1", "r4_midwest_1",
    "r5_semi1", "r5_semi2", "championship",
]

GROUP_URL = "https://fantasy.espn.com/games/tournament-challenge-bracket-2026/group?id=5c58b8ab-f641-4c0a-8508-461911cc542f"
TARGET = "Rebecca"


def take_screenshot(page) -> str:
    return base64.b64encode(page.screenshot(type="png")).decode("utf-8")


def execute_action(page, action_input: dict) -> str:
    action = action_input.get("action")
    if action == "screenshot":
        pass
    elif action == "left_click":
        coord = action_input.get("coordinate", [0, 0])
        page.mouse.click(coord[0], coord[1])
    elif action == "type":
        page.keyboard.type(action_input.get("text", ""))
    elif action == "key":
        page.keyboard.press(action_input.get("text", ""))
    elif action == "scroll":
        coord = action_input.get("coordinate", [640, 400])
        direction = action_input.get("scroll_direction", "down")
        amount = action_input.get("scroll_amount", 3)
        page.mouse.move(coord[0], coord[1])
        delta_y = amount * 100 if direction == "down" else -amount * 100
        page.mouse.wheel(0, delta_y)
    elif action == "mouse_move":
        coord = action_input.get("coordinate", [0, 0])
        page.mouse.move(coord[0], coord[1])
    elif action == "wait":
        time.sleep(action_input.get("duration", 1))
    page.wait_for_timeout(500)
    return take_screenshot(page)


def extract_json(text: str):
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    for pattern in [r"(\{[\s\S]*\})", r"(\[[\s\S]*\])"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    return None


def main():
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Error: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    slot_list = "\n".join(f"  {s}" for s in VALID_SLOT_IDS)

    prompt = f"""You are looking at an ESPN Tournament Challenge group page.

Your task:
1. Find the member named "{TARGET}" in the group standings/leaderboard.
2. Click on their bracket entry to view their full bracket.
3. Once you can see the bracket, extract ALL of their picks for every game.
4. Scroll as needed to see all regions and rounds.

CRITICAL: The tournament has EXACTLY 63 games. Your output must have EXACTLY 63 picks.
Do NOT include First Four / play-in games. Only the main 64-team bracket.

Here are ALL 63 valid slot IDs — use ONLY these exact keys:
{slot_list}

For each slot, record which team this person PICKED to win (not the actual result).
If you see a pick was wrong (crossed out/red), still record what they originally picked.

Team slug rules:
- Lowercase, underscores for spaces, no special chars
- Examples: duke, north_carolina, montana_st, st_marys, texas_am, uconn

Return as JSON:
{{
    "player_name": "{TARGET}",
    "entry_name": "<bracket name if visible>",
    "picks": {{
        "<slot_id>": "<team_slug>",
        ...all 63 slots...
    }}
}}

Output ONLY valid JSON. No other text.
"""

    client = anthropic.Anthropic()
    tools = [{
        "type": "computer_20250124",
        "name": "computer",
        "display_width_px": 1280,
        "display_height_px": 800,
    }]

    print(f"Fetching {TARGET}'s bracket from ESPN group...")
    print(f"URL: {GROUP_URL}")

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

        print("Navigating...")
        page.goto(GROUP_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(3000)
        screenshot_b64 = take_screenshot(page)

        messages = [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": screenshot_b64}},
        ]}]

        for i in range(30):
            print(f"  Agent iteration {i + 1}/30...")
            response = client.beta.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4096,
                tools=tools,
                messages=messages,
                betas=["computer-use-2025-01-24"],
            )

            if response.stop_reason == "end_turn":
                text = "\n".join(b.text for b in response.content if hasattr(b, "text"))
                print(f"  Agent finished after {i + 1} iterations.")
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    action = block.input.get("action", "?")
                    print(f"    Action: {action}")
                    try:
                        ss = execute_action(page, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": [{"type": "image", "source": {
                                "type": "base64", "media_type": "image/png", "data": ss,
                            }}],
                        })
                    except Exception as e:
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        })

            messages.append({"role": "assistant", "content": response.content})
            messages.append({"role": "user", "content": tool_results})
        else:
            text = ""

        browser.close()

    data = extract_json(text)
    if data is None:
        print(f"Failed to parse JSON. Raw response:\n{text[:500]}")
        sys.exit(1)

    # Clean picks to valid slot IDs only
    if "picks" in data:
        valid = set(VALID_SLOT_IDS)
        cleaned = {k: v for k, v in data["picks"].items() if k in valid}
        removed = len(data["picks"]) - len(cleaned)
        if removed:
            print(f"  Removed {removed} invalid slot IDs")
        data["picks"] = cleaned

    # Save
    filepath = Path("data/entries/player_brackets.json")
    if filepath.exists():
        existing = json.loads(filepath.read_text())
    else:
        existing = {"entries": []}

    entries = [e for e in existing["entries"] if e.get("player_name") != TARGET]
    entries.append(data)
    existing["entries"] = entries

    filepath.write_text(json.dumps(existing, indent=2))
    pick_count = len(data.get("picks", {}))
    print(f"Done! {pick_count} picks saved to: {filepath}")
    if pick_count != 63:
        print(f"Warning: Expected 63 picks, got {pick_count}.")


if __name__ == "__main__":
    main()
