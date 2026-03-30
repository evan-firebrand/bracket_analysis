"""Playwright browser lifecycle and action execution for Claude computer use."""

import base64

from playwright.sync_api import Browser, Page, sync_playwright


class BrowserSession:
    """Manages a headless Chromium browser for Claude computer use."""

    def __init__(self, headless: bool = True, width: int = 1280, height: int = 800):
        self._headless = headless
        self._width = width
        self._height = height
        self._playwright = None
        self._browser: Browser | None = None
        self._page: Page | None = None

    def start(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self._headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
        )
        self._page = self._browser.new_page(
            viewport={"width": self._width, "height": self._height},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        )

    def stop(self):
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
        self._browser = None
        self._page = None
        self._playwright = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    @property
    def page(self) -> Page:
        if self._page is None:
            raise RuntimeError("Browser not started. Call start() first.")
        return self._page

    def navigate(self, url: str, retries: int = 3):
        import time
        for attempt in range(retries):
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                return
            except Exception as e:
                if attempt < retries - 1:
                    wait = 2 ** (attempt + 1)
                    print(f"  Navigation failed (attempt {attempt + 1}), retrying in {wait}s: {e}")
                    time.sleep(wait)
                else:
                    raise

    def screenshot(self) -> str:
        """Take a screenshot and return base64-encoded PNG."""
        png_bytes = self.page.screenshot(type="png")
        return base64.b64encode(png_bytes).decode("utf-8")

    def click(self, x: int, y: int):
        self.page.mouse.click(x, y)

    def double_click(self, x: int, y: int):
        self.page.mouse.dblclick(x, y)

    def right_click(self, x: int, y: int):
        self.page.mouse.click(x, y, button="right")

    def type_text(self, text: str):
        self.page.keyboard.type(text)

    def press_key(self, key: str):
        self.page.keyboard.press(key)

    def scroll(self, x: int, y: int, direction: str, amount: int):
        self.page.mouse.move(x, y)
        delta_y = -amount * 100 if direction == "up" else amount * 100
        delta_x = -amount * 100 if direction == "left" else 0
        if direction == "right":
            delta_x = amount * 100
            delta_y = 0
        self.page.mouse.wheel(delta_x, delta_y)

    def mouse_move(self, x: int, y: int):
        self.page.mouse.move(x, y)

    def drag(self, start_x: int, start_y: int, end_x: int, end_y: int):
        self.page.mouse.move(start_x, start_y)
        self.page.mouse.down()
        self.page.mouse.move(end_x, end_y)
        self.page.mouse.up()

    def execute_action(self, action_input: dict) -> str:
        """Execute a Claude computer use action and return a screenshot.

        Args:
            action_input: The 'input' dict from a Claude tool_use block.

        Returns:
            Base64-encoded PNG screenshot after executing the action.
        """
        action = action_input.get("action")

        if action == "screenshot":
            pass  # just return screenshot below

        elif action == "left_click":
            coord = action_input.get("coordinate", [0, 0])
            self.click(coord[0], coord[1])

        elif action == "right_click":
            coord = action_input.get("coordinate", [0, 0])
            self.right_click(coord[0], coord[1])

        elif action == "double_click":
            coord = action_input.get("coordinate", [0, 0])
            self.double_click(coord[0], coord[1])

        elif action == "triple_click":
            coord = action_input.get("coordinate", [0, 0])
            self.page.mouse.click(coord[0], coord[1], click_count=3)

        elif action == "middle_click":
            coord = action_input.get("coordinate", [0, 0])
            self.page.mouse.click(coord[0], coord[1], button="middle")

        elif action == "type":
            text = action_input.get("text", "")
            self.type_text(text)

        elif action == "key":
            key = action_input.get("text", "")
            self.press_key(key)

        elif action == "scroll":
            coord = action_input.get("coordinate", [640, 400])
            direction = action_input.get("scroll_direction", "down")
            amount = action_input.get("scroll_amount", 3)
            self.scroll(coord[0], coord[1], direction, amount)

        elif action == "mouse_move":
            coord = action_input.get("coordinate", [0, 0])
            self.mouse_move(coord[0], coord[1])

        elif action == "left_click_drag":
            start = action_input.get("start_coordinate", [0, 0])
            end = action_input.get("coordinate", [0, 0])
            self.drag(start[0], start[1], end[0], end[1])

        elif action == "wait":
            import time
            duration = action_input.get("duration", 1)
            time.sleep(duration)

        else:
            print(f"Warning: Unknown action '{action}', taking screenshot only.")

        # Small delay to let the page settle after action
        self.page.wait_for_timeout(500)

        return self.screenshot()
