"""Browser automation via Playwright and Claude Computer Use API."""
import asyncio
import base64
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("jarvis.tools.browser_agent")

MAX_STEPS = 30
VIEWPORT_WIDTH = 1024
VIEWPORT_HEIGHT = 768
SCREENSHOT_QUALITY = 75
DEFAULT_TIMEOUT_MS = 30000
DOWNLOAD_DIR = Path.home() / "Downloads" / "JARVIS"

JARVIS_HOME = Path(__file__).parent.parent.parent
BROWSER_PROFILE_DIR = JARVIS_HOME / "data" / "browser-profile"

COMPUTER_USE_BETA = "computer-use-2025-11-24"
COMPUTER_USE_TOOL_TYPE = "computer_20251124"
COMPUTER_USE_MODEL = "claude-sonnet-4-6"

KEY_TRANSLATION = {
    "ctrl": "Control", "control": "Control", "cmd": "Meta", "command": "Meta",
    "super": "Meta", "meta": "Meta", "alt": "Alt", "option": "Alt", "shift": "Shift",
    "return": "Enter", "enter": "Enter", "esc": "Escape", "escape": "Escape",
    "del": "Delete", "delete": "Delete", "backspace": "Backspace", "space": " ", "tab": "Tab",
    "up": "ArrowUp", "down": "ArrowDown", "left": "ArrowLeft", "right": "ArrowRight",
    "arrowup": "ArrowUp", "arrowdown": "ArrowDown", "arrowleft": "ArrowLeft", "arrowright": "ArrowRight",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5", "f6": "F6", "f7": "F7", "f8": "F8",
    "f9": "F9", "f10": "F10", "f11": "F11", "f12": "F12",
    "home": "Home", "end": "End", "pageup": "PageUp", "pagedown": "PageDown",
    "page_up": "PageUp", "page_down": "PageDown", "insert": "Insert",
}


def _translate_key_combo(key_combo: str) -> str:
    """Translate key combinations from Claude format to Playwright format."""
    parts = key_combo.split("+")
    translated = []
    for part in parts:
        stripped = part.strip()
        lower = stripped.lower()
        if lower in KEY_TRANSLATION:
            translated.append(KEY_TRANSLATION[lower])
        else:
            # Keep as-is (single characters like 'a', 'l', '1', etc.)
            translated.append(stripped)
    return "+".join(translated)


class BrowserAgent:
    """Autonomous browser agent powered by Claude Computer Use API."""

    def __init__(self):
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._initialized = False
        self._task_running = False

    async def initialize(self, sync_chrome: bool = True) -> bool:
        """Launch Chromium with a persistent profile (sessions survive restarts).

        Args:
            sync_chrome: If True, automatically import cookies from Chrome
                on first launch to carry over existing login sessions.
        """
        if self._initialized:
            return True

        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()

            DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
            BROWSER_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

            await self._launch_persistent_browser()

            self._initialized = True
            logger.info("Browser agent initialized (persistent profile, %dx%d viewport)",
                        VIEWPORT_WIDTH, VIEWPORT_HEIGHT)

            if sync_chrome and self._context:
                try:
                    from jarvis.tools.chrome_sync import sync_chrome_cookies
                    result = await sync_chrome_cookies(self._context)
                    logger.info("Chrome cookie sync: %s", result.split("\n")[0])
                except Exception as e:
                    logger.warning("Chrome cookie auto-sync failed (non-fatal): %s", e)

            return True

        except ImportError:
            logger.error(
                "Playwright not installed. Run: pip install playwright && playwright install chromium"
            )
            return False
        except Exception as e:
            logger.error("Failed to initialize browser agent: %s", e)
            return False

    async def _launch_persistent_browser(self):
        """Launch Chromium with persistent user data directory."""
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(BROWSER_PROFILE_DIR),
            headless=False,
            viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            args=[
                "--disable-blink-features=AutomationControlled",
                f"--window-size={VIEWPORT_WIDTH},{VIEWPORT_HEIGHT}",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            accept_downloads=True,
        )

        self._context.on("page", self._on_new_page)  # Handle new tabs/popups

        pages = self._context.pages
        if pages:
            self._page = pages[0]
        else:
            self._page = await self._context.new_page()
        self._page.set_default_timeout(DEFAULT_TIMEOUT_MS)

    async def _on_new_page(self, page):
        """Handle new pages (popups, new tabs) by focusing on them."""
        self._page = page
        page.set_default_timeout(DEFAULT_TIMEOUT_MS)
        logger.info("Browser: new page opened: %s", page.url[:80])

    async def shutdown(self):
        """Close the browser context and clean up; persistent profile survives restarts."""
        try:
            if self._context:
                await self._context.close()
        except Exception as e:
            logger.warning("Error during browser shutdown: %s", e)

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        self._page = None
        self._context = None
        self._browser = None
        self._initialized = False
        logger.info("Browser agent shut down.")

    def _is_page_alive(self) -> bool:
        """Check if the current page/context is still usable."""
        try:
            return (
                self._page is not None
                and not self._page.is_closed()
                and self._context is not None
            )
        except Exception:
            return False

    async def _ensure_ready(self) -> bool:
        """Ensure the browser is initialized and the page is alive; reinitialize if stale."""
        if self._initialized and self._is_page_alive():
            return True

        if self._initialized:
            logger.warning("Browser page/context is stale. Reinitializing...")
            await self.shutdown()

        return await self.initialize()

    async def take_screenshot(self) -> str:
        """Capture the current page as a base64-encoded PNG."""
        if not self._page:
            return ""
        try:
            screenshot_bytes = await self._page.screenshot(
                type="png",
                full_page=False,
            )
            return base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as e:
            logger.error("Screenshot failed: %s", e)
            return ""

    async def execute_action(self, action: str, **params) -> str:
        """Execute a computer use action on the browser page.

        Maps Claude Computer Use actions to Playwright API calls.
        Returns a status message.
        """
        if not self._page:
            return "Error: no browser page available"

        try:
            if action == "screenshot":
                return "screenshot_taken"

            elif action == "left_click":
                x, y = params.get("coordinate", [0, 0])
                await self._page.mouse.click(x, y)
                await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                return f"Clicked at ({x}, {y})"

            elif action == "right_click":
                x, y = params.get("coordinate", [0, 0])
                await self._page.mouse.click(x, y, button="right")
                return f"Right-clicked at ({x}, {y})"

            elif action == "double_click":
                x, y = params.get("coordinate", [0, 0])
                await self._page.mouse.dblclick(x, y)
                return f"Double-clicked at ({x}, {y})"

            elif action == "triple_click":
                x, y = params.get("coordinate", [0, 0])
                await self._page.mouse.click(x, y, click_count=3)
                return f"Triple-clicked at ({x}, {y})"

            elif action == "type":
                text = params.get("text", "")
                await self._page.keyboard.type(text, delay=30)
                return f"Typed: '{text[:50]}{'...' if len(text) > 50 else ''}'"

            elif action == "key":
                raw_combo = params.get("text", "")
                key_combo = _translate_key_combo(raw_combo)
                if key_combo != raw_combo:
                    logger.debug("Key translated: '%s' -> '%s'", raw_combo, key_combo)
                await self._page.keyboard.press(key_combo)
                return f"Pressed key: {key_combo}"

            elif action == "scroll":
                x, y = params.get("coordinate", [VIEWPORT_WIDTH // 2, VIEWPORT_HEIGHT // 2])
                direction = params.get("scroll_direction", "down")
                amount = params.get("scroll_amount", 3)
                delta_x = delta_y = 0
                if direction == "down":
                    delta_y = amount * 100
                elif direction == "up":
                    delta_y = -(amount * 100)
                elif direction == "right":
                    delta_x = amount * 100
                elif direction == "left":
                    delta_x = -(amount * 100)
                await self._page.mouse.wheel(delta_x, delta_y)
                await asyncio.sleep(0.3)
                return f"Scrolled {direction} by {amount} at ({x}, {y})"

            elif action == "left_click_drag":
                sx, sy = params.get("start_coordinate", [0, 0])
                ex, ey = params.get("coordinate", [0, 0])
                await self._page.mouse.move(sx, sy)
                await self._page.mouse.down()
                await self._page.mouse.move(ex, ey, steps=10)
                await self._page.mouse.up()
                return f"Dragged from ({sx},{sy}) to ({ex},{ey})"

            elif action == "wait":
                duration = min(params.get("duration", 2), 10)
                await asyncio.sleep(duration)
                return f"Waited {duration}s"

            else:
                return f"Unknown action: {action}"

        except Exception as e:
            error_msg = str(e)[:200]
            logger.error("Browser action '%s' failed: %s", action, error_msg)
            return f"Action '{action}' failed: {error_msg}"

    async def navigate(self, url: str) -> str:
        """Navigate to a URL and sync Chrome cookies for the target domain."""
        ok = await self._ensure_ready()
        if not ok:
            return "Error: browser not initialized"
        try:
            if self._context:
                try:
                    from jarvis.tools.chrome_sync import sync_chrome_for_url
                    await sync_chrome_for_url(self._context, url)
                except Exception as e:
                    logger.debug("Cookie sync for %s skipped: %s", url[:50], e)

            await self._page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT_MS)
            return f"Navigated to: {self._page.url}"
        except Exception as e:
            return f"Navigation failed: {str(e)[:200]}"

    async def run_task(self, task: str, start_url: Optional[str] = None) -> str:
        """Execute a multi-step browser task using Claude Computer Use.

        Args:
            task: Natural language description of what to do
                  (e.g., "Go to LinkedIn and apply for software engineer jobs in NYC")
            start_url: Optional URL to navigate to before starting

        Returns:
            Summary of what was accomplished
        """
        if self._task_running:
            return "Error: another browser task is already running. Wait for it to finish."

        ok = await self._ensure_ready()
        if not ok:
            return "Error: failed to initialize browser. Is Playwright installed?"

        self._task_running = True
        try:
            return await self._run_computer_use_loop(task, start_url)
        finally:
            self._task_running = False

    async def _run_computer_use_loop(self, task: str, start_url: Optional[str] = None) -> str:
        """Core loop: screenshot, send to Claude, execute action, repeat; handles rate limits."""
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        if not api_key:
            return "Error: ANTHROPIC_API_KEY not set. Cannot use Computer Use."

        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=120.0)

        max_retries = 3
        base_backoff_seconds = 5.0
        inter_step_delay = 0.3

        if start_url:
            nav_result = await self.navigate(start_url)
            logger.info("Browser: %s", nav_result)

        await asyncio.sleep(1)

        screenshot_b64 = await self.take_screenshot()
        if not screenshot_b64:
            return "Error: could not capture initial screenshot"

        computer_tool = {
            "type": COMPUTER_USE_TOOL_TYPE,
            "name": "computer",
            "display_width_px": VIEWPORT_WIDTH,
            "display_height_px": VIEWPORT_HEIGHT,
        }

        system_prompt = (
            "You are a browser automation agent. You can see a browser window and "
            "interact with it using mouse clicks, keyboard input, and scrolling. "
            "Complete the user's task step by step. After each action, you will "
            "receive a new screenshot showing the result.\n\n"
            "IMPORTANT RULES:\n"
            "- Act directly on visible page elements. Do NOT waste steps refreshing, "
            "reloading, or re-navigating to the same page you are already on.\n"
            "- If the page content is already visible, interact with it immediately "
            "(click links, buttons, thumbnails, etc.).\n"
            "- Do NOT try to use the browser address bar or navigate away unless the "
            "task explicitly requires going to a different URL.\n"
            "- Scroll down if the target element is not visible in the current viewport.\n"
            "- Click on form fields before typing into them.\n"
            "- Use Tab to move between form fields when appropriate.\n"
            "- If a page is loading, use the wait action (1-2 seconds).\n"
            "- If you encounter a CAPTCHA, describe it and say you need human help.\n"
            "- If you need to upload a file, describe what file is needed.\n"
            "- When the task is complete, respond with a text summary of what you did.\n"
            "- If you get stuck after 2-3 attempts at the same action, explain why "
            "and suggest an alternative approach.\n"
            "- Minimize the number of steps. Prefer direct clicks over keyboard shortcuts "
            "for navigation.\n\n"
            "KEYBOARD NOTES:\n"
            "- Use 'Control' (not 'ctrl') for modifier keys.\n"
            "- Use 'Meta' (not 'cmd' or 'super') for the Command/Windows key.\n"
            "- Use 'Alt' (not 'option') for the Alt/Option key.\n"
            "- Common combos: 'Control+a' (select all), 'Control+c' (copy), "
            "'Meta+l' (address bar on Mac).\n\n"
            f"VIEWPORT: {VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT} pixels\n"
            f"DOWNLOADS: {DOWNLOAD_DIR}\n"
        )

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"Task: {task}"},
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                    {"type": "text", "text": "Here is the current browser state. Begin working on the task."},
                ],
            }
        ]

        step = 0
        actions_taken = []

        while step < MAX_STEPS:
            step += 1
            logger.info("Browser agent step %d/%d", step, MAX_STEPS)

            if step > 1:
                await asyncio.sleep(inter_step_delay)

            if not self._is_page_alive():
                logger.warning("Browser closed during task at step %d. Aborting.", step)
                summary = "The browser window was closed while I was working. "
                if actions_taken:
                    summary += f"I completed {len(actions_taken)} action(s) before it closed. "
                summary += "I can try again if you reopen the browser."
                return summary

            response = None
            for attempt in range(max_retries + 1):
                try:
                    response = await client.beta.messages.create(
                        model=COMPUTER_USE_MODEL,
                        max_tokens=1024,
                        system=system_prompt,
                        tools=[computer_tool],
                        messages=messages,
                        betas=[COMPUTER_USE_BETA],
                    )
                    break  # Success
                except anthropic.RateLimitError as e:
                    if attempt < max_retries:
                        wait_time = base_backoff_seconds * (2 ** attempt)
                        logger.warning(
                            "Rate limited at step %d (attempt %d/%d). "
                            "Backing off %.1fs before retry.",
                            step, attempt + 1, max_retries, wait_time,
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        error_msg = f"Rate limited after {max_retries + 1} attempts: {str(e)[:200]}"
                        logger.error("Browser agent: %s", error_msg)
                        return f"Browser task paused at step {step} due to rate limiting. {error_msg}"
                except Exception as e:
                    error_msg = f"Claude API error: {str(e)[:200]}"
                    logger.error("Browser agent: %s", error_msg)
                    return f"Browser task failed at step {step}: {error_msg}"

            if response is None:
                return f"Browser task failed at step {step}: no response received."

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason == "end_turn":
                final_text = ""
                for block in assistant_content:
                    if hasattr(block, "text"):
                        final_text += block.text
                if not final_text:
                    final_text = f"Task completed after {step} steps."
                logger.info("Browser agent completed: %s", final_text[:100])
                return final_text

            tool_results = []
            for block in assistant_content:
                if block.type == "tool_use":
                    tool_input = block.input
                    action = tool_input.get("action", "screenshot")

                    logger.info("Browser agent action: %s (params: %s)",
                                action, {k: v for k, v in tool_input.items() if k != "action"})

                    if action == "screenshot":
                        result_text = "Here is the current screenshot."
                    else:
                        action_params = {k: v for k, v in tool_input.items() if k != "action"}
                        result_text = await self.execute_action(action, **action_params)
                        actions_taken.append(f"Step {step}: {action} - {result_text}")
                        await asyncio.sleep(0.5)

                    new_screenshot = await self.take_screenshot()

                    tool_result_content = []
                    if new_screenshot:
                        tool_result_content.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": new_screenshot,
                            },
                        })
                    tool_result_content.append({
                        "type": "text",
                        "text": result_text,
                    })

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": tool_result_content,
                    })

            messages.append({"role": "user", "content": tool_results})

        summary = f"Browser task stopped after {MAX_STEPS} steps (safety limit). Actions taken:\n"
        summary += "\n".join(actions_taken[-10:])
        return summary


_browser_agent: Optional[BrowserAgent] = None


def _get_browser_agent() -> BrowserAgent:
    """Get or create the singleton browser agent."""
    global _browser_agent
    if _browser_agent is None:
        _browser_agent = BrowserAgent()
    return _browser_agent
async def browse_web(task: str, url: str = "") -> str:
    """Execute a browser automation task using Claude Computer Use."""
    agent = _get_browser_agent()
    start_url = url if url else None
    logger.info("Browser task started: '%s' (url: %s)", task[:80], start_url or "blank")
    result = await agent.run_task(task, start_url)
    logger.info("Browser task result: %s", result[:200])
    return result


async def browser_navigate(url: str) -> list:
    """Navigate the browser to a specific URL and return screenshot."""
    agent = _get_browser_agent()
    ok = await agent._ensure_ready()
    if not ok:
        return [{"type": "text", "text": "Error: failed to initialize browser"}]

    result = await agent.navigate(url)
    screenshot_b64 = await agent.take_screenshot()

    content = [{"type": "text", "text": f"{result}\nHere is what the browser is currently showing:"}]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })
    else:
        content.append({"type": "text", "text": "(Screenshot capture failed)"})

    return content


async def browser_screenshot() -> list:
    """Take a screenshot of the current browser state."""
    agent = _get_browser_agent()
    if not agent._initialized or not agent._is_page_alive():
        return [{"type": "text", "text": "Browser is not open. Use browse_web or browser_navigate first."}]

    screenshot_b64 = await agent.take_screenshot()
    if not screenshot_b64:
        return [{"type": "text", "text": "Failed to capture screenshot."}]

    current_url = agent._page.url if agent._page else "unknown"
    return [
        {"type": "text", "text": f"Current URL: {current_url}\nHere is the current browser screenshot:"},
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        },
    ]


async def sync_browser_sessions(domains: str = "") -> str:
    """Sync login sessions from Chrome into JARVIS's browser."""
    agent = _get_browser_agent()
    ok = await agent._ensure_ready()
    if not ok:
        return "Error: failed to initialize browser."

    from jarvis.tools.chrome_sync import sync_chrome_cookies

    domain_list = None
    if domains.strip():
        domain_list = [
            f".{d.strip().lstrip('.')}" for d in domains.split(",") if d.strip()
        ]

    return await sync_chrome_cookies(agent._context, domains=domain_list)


async def get_browser_state() -> list:
    """Get the current state of the browser: tabs, active URL, and screenshot."""
    agent = _get_browser_agent()
    if not agent._initialized or not agent._context:
        return [{"type": "text", "text": "Browser is not open. Use browse_web or browser_navigate to open it first."}]

    pages = agent._context.pages
    tab_info = []
    for i, page in enumerate(pages):
        is_active = (page is agent._page)
        marker = " (active)" if is_active else ""
        tab_info.append(f"  Tab {i + 1}: {page.url}{marker}")

    tabs_text = f"Open tabs ({len(pages)}):\n" + "\n".join(tab_info)

    title = ""
    if agent._page and not agent._page.is_closed():
        try:
            title = await agent._page.title()
        except Exception:
            pass

    active_info = f"Active tab: {agent._page.url}" if agent._page else "No active tab"
    if title:
        active_info += f"\nPage title: {title}"

    screenshot_b64 = await agent.take_screenshot()

    content = [
        {"type": "text", "text": f"{tabs_text}\n\n{active_info}\n\nCurrent view:"},
    ]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })

    return content


async def browser_switch_tab(tab_number: int) -> list:
    """Switch to a different browser tab by its number (1-based).

    Use get_browser_state first to see which tabs are open.
    Returns a screenshot of the newly active tab.
    """
    agent = _get_browser_agent()
    if not agent._initialized or not agent._context:
        return [{"type": "text", "text": "Browser is not open."}]

    pages = agent._context.pages
    idx = tab_number - 1
    if idx < 0 or idx >= len(pages):
        return [{"type": "text", "text": f"Invalid tab number {tab_number}. There are {len(pages)} tab(s) open."}]

    agent._page = pages[idx]
    await agent._page.bring_to_front()

    screenshot_b64 = await agent.take_screenshot()
    content = [
        {"type": "text", "text": f"Switched to tab {tab_number}: {agent._page.url}"},
    ]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": screenshot_b64,
            },
        })
    return content


async def browser_upload_file(file_path: str, selector: str = "") -> str:
    """Upload a file to a file input on the current page."""
    import os
    agent = _get_browser_agent()
    if not agent._initialized or not agent._is_page_alive():
        return "Error: browser is not open."

    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"

    try:
        if selector:
            file_input = agent._page.locator(selector)
        else:
            file_input = agent._page.locator('input[type="file"]').first

        await file_input.set_input_files(file_path)
        filename = os.path.basename(file_path)
        return f"Uploaded '{filename}' to the file input successfully."
    except Exception as e:
        return f"File upload failed: {str(e)[:200]}"


async def close_browser() -> str:
    """Close the browser when you are done with web tasks."""
    agent = _get_browser_agent()
    if agent._initialized:
        await agent.shutdown()
        return "Browser closed."
    return "Browser was not open."
