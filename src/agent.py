"""Core Claude computer use agent loop."""

import json
import anthropic
from src.browser import BrowserSession

COMPUTER_USE_BETA = "computer-use-2025-11-24"
TOOL_TYPE = "computer_20251124"
DEFAULT_MODEL = "claude-sonnet-4-20250514"
MAX_ITERATIONS = 30


def extract_text(response) -> str:
    """Extract text content from a Claude response."""
    parts = []
    for block in response.content:
        if hasattr(block, "text"):
            parts.append(block.text)
    return "\n".join(parts)


def run_agent(
    task_prompt: str,
    start_url: str,
    browser: BrowserSession,
    model: str = DEFAULT_MODEL,
) -> str:
    """Run the Claude computer use agent loop to completion.

    Args:
        task_prompt: Instructions for Claude on what to do and extract.
        start_url: URL to navigate to before starting.
        browser: An active BrowserSession.
        model: Claude model to use.

    Returns:
        The final text response from Claude with extracted data.
    """
    client = anthropic.Anthropic()

    tools = [
        {
            "type": TOOL_TYPE,
            "name": "computer",
            "display_width_px": browser._width,
            "display_height_px": browser._height,
        }
    ]

    # Navigate to start URL and take initial screenshot
    print(f"Navigating to: {start_url}")
    browser.navigate(start_url)
    # Wait for JS SPA to load
    browser.page.wait_for_timeout(3000)
    screenshot_b64 = browser.screenshot()

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": task_prompt},
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": screenshot_b64,
                    },
                },
            ],
        }
    ]

    for iteration in range(MAX_ITERATIONS):
        print(f"  Agent iteration {iteration + 1}/{MAX_ITERATIONS}...")

        response = client.beta.messages.create(
            model=model,
            max_tokens=4096,
            tools=tools,
            messages=messages,
            betas=[COMPUTER_USE_BETA],
        )

        # Check if Claude is done (no more tool use)
        if response.stop_reason == "end_turn":
            result = extract_text(response)
            print(f"  Agent finished after {iteration + 1} iterations.")
            return result

        # Process tool use blocks
        assistant_content = []
        tool_results = []

        for block in response.content:
            assistant_content.append(block)

            if block.type == "tool_use":
                action_input = block.input
                action_name = action_input.get("action", "unknown")
                print(f"    Action: {action_name}")

                try:
                    screenshot_b64 = browser.execute_action(action_input)
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "image/png",
                                        "data": screenshot_b64,
                                    },
                                }
                            ],
                        }
                    )
                except Exception as e:
                    print(f"    Error executing action: {e}")
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {str(e)}",
                            "is_error": True,
                        }
                    )

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

    print("  Warning: Agent hit max iterations without completing.")
    return extract_text(response)


def extract_json_from_response(text: str) -> dict | list | None:
    """Try to extract JSON from Claude's text response.

    Handles responses where JSON is embedded in markdown code blocks
    or mixed with explanatory text.
    """
    # Try parsing the whole thing as JSON first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON in code blocks
    import re

    code_block_match = re.search(r"```(?:json)?\s*\n?([\s\S]*?)\n?```", text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    # Try to find a JSON array or object
    for pattern in [r"(\[[\s\S]*\])", r"(\{[\s\S]*\})"]:
        match = re.search(pattern, text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue

    return None
