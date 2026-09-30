"""Browser automation via Playwright and a computer-use model (OpenAI or Claude)."""
import asyncio
import base64
import contextlib
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger("jarvis.tools.browser_agent")

MAX_STEPS = 30
VIEWPORT_WIDTH = 1024
VIEWPORT_HEIGHT = 768
SCREENSHOT_QUALITY = 75
DEFAULT_TIMEOUT_MS = 30000
DOWNLOAD_DIR = Path.home() / "Downloads" / "JARVIS"

JARVIS_HOME = Path(__file__).parent.parent.parent
BROWSER_PROFILE_DIR = JARVIS_HOME / "data" / "browser-profile"

# Anthropic path (LLM_PROVIDER=anthropic)
COMPUTER_USE_BETA = "computer-use-2025-11-24"
COMPUTER_USE_TOOL_TYPE = "computer_20251124"
COMPUTER_USE_MODEL = "claude-sonnet-4-6"

# Screenshots kept in the model's context. Older ones are replaced with a
# placeholder so cost and context don't grow with every step.
KEEP_SCREENSHOTS = 3
SCREENSHOT_MEDIA_TYPE = "image/jpeg"
_PLACEHOLDER_IMAGE = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)

# OpenAI button names -> Playwright button names
_OPENAI_BUTTONS = {"left": "left", "right": "right", "wheel": "middle"}

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
            with contextlib.suppress(Exception):
                await self._playwright.stop()

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
        """Capture the current page as a base64-encoded JPEG."""
        if not self._page:
            return ""
        try:
            screenshot_bytes = await self._page.screenshot(
                type="jpeg",
                quality=SCREENSHOT_QUALITY,
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

    async def execute_openai_action(self, action: dict[str, Any]) -> str:
        """Execute one OpenAI computer-tool action (click, type, keypress, ...)."""
        if not self._page:
            return "Error: no browser page available"
        kind = action.get("type", "")
        # For pointer actions, ``keys`` are modifiers held during the action.
        # For keypress, ``keys`` is the combo itself and is pressed below.
        held = [] if kind == "keypress" else [_translate_key_combo(k) for k in action.get("keys") or []]
        mouse = self._page.mouse
        keyboard = self._page.keyboard
        try:
            for key in held:
                await keyboard.down(key)
            try:
                if kind == "click":
                    button = action.get("button", "left")
                    if button in ("back", "forward"):
                        await (self._page.go_back() if button == "back" else self._page.go_forward())
                        return f"Navigated {button}"
                    await mouse.click(action["x"], action["y"], button=_OPENAI_BUTTONS.get(button, "left"))
                    with contextlib.suppress(Exception):
                        await self._page.wait_for_load_state("domcontentloaded", timeout=5000)
                    return f"Clicked {button} at ({action['x']}, {action['y']})"
                if kind == "double_click":
                    await mouse.dblclick(action["x"], action["y"])
                    return f"Double-clicked at ({action['x']}, {action['y']})"
                if kind == "move":
                    await mouse.move(action["x"], action["y"])
                    return f"Moved to ({action['x']}, {action['y']})"
                if kind == "drag":
                    path = action.get("path") or []
                    if len(path) < 2:
                        return "Drag needs at least two points"
                    await mouse.move(path[0]["x"], path[0]["y"])
                    await mouse.down()
                    for point in path[1:]:
                        await mouse.move(point["x"], point["y"], steps=5)
                    await mouse.up()
                    return f"Dragged through {len(path)} points"
                if kind == "scroll":
                    await mouse.move(action["x"], action["y"])
                    await mouse.wheel(action.get("scroll_x", 0), action.get("scroll_y", 0))
                    await asyncio.sleep(0.3)
                    return f"Scrolled ({action.get('scroll_x', 0)}, {action.get('scroll_y', 0)})"
                if kind == "type":
                    text = action.get("text", "")
                    await keyboard.type(text, delay=30)
                    return f"Typed: '{text[:50]}{'...' if len(text) > 50 else ''}'"
                if kind == "keypress":
                    combo = "+".join(_translate_key_combo(k) for k in action.get("keys") or [])
                    await keyboard.press(combo)
                    return f"Pressed key: {combo}"
                if kind == "wait":
                    await asyncio.sleep(2)
                    return "Waited 2s"
                if kind == "screenshot":
                    return "screenshot_taken"
                return f"Unknown action: {kind}"
            finally:
                for key in reversed(held):
                    await keyboard.up(key)
        except Exception as e:
            error_msg = str(e)[:200]
            logger.error("Browser action '%s' failed: %s", kind, error_msg)
            return f"Action '{kind}' failed: {error_msg}"

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

    async def run_task(self, task: str, start_url: str | None = None) -> str:
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

    def _system_prompt(self) -> str:
        return (
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

    async def _prepare(self, start_url: str | None) -> str:
        """Navigate to the start URL and return the first screenshot (or "")."""
        if start_url:
            nav_result = await self.navigate(start_url)
            logger.info("Browser: %s", nav_result)
        await asyncio.sleep(1)
        return await self.take_screenshot()

    def _closed_summary(self, actions_taken: list[str]) -> str:
        summary = "The browser window was closed while I was working. "
        if actions_taken:
            summary += f"I completed {len(actions_taken)} action(s) before it closed. "
        return summary + "I can try again if you reopen the browser."

    def _limit_summary(self, actions_taken: list[str]) -> str:
        summary = f"Browser task stopped after {MAX_STEPS} steps (safety limit). Actions taken:\n"
        return summary + "\n".join(actions_taken[-10:])

    async def _run_computer_use_loop(self, task: str, start_url: str | None = None) -> str:
        """Screenshot, ask the model for actions, execute them, repeat."""
        from jarvis.config import settings

        if settings.LLM_PROVIDER == "anthropic":
            return await self._run_anthropic_loop(task, start_url)
        return await self._run_openai_loop(task, start_url)

    async def _run_openai_loop(self, task: str, start_url: str | None) -> str:
        from jarvis.config import settings
        from jarvis.core.hardening import cloud_circuit
        from jarvis.core.providers import build_provider
        from jarvis.core.providers.openai_provider import OpenAIProvider

        provider = build_provider("openai")
        if not isinstance(provider, OpenAIProvider) or not provider.is_configured():
            return "Error: OPENAI_API_KEY not set. Cannot use computer use."

        screenshot_b64 = await self._prepare(start_url)
        if not screenshot_b64:
            return "Error: could not capture initial screenshot"

        base_kwargs: dict[str, Any] = {
            "model": settings.OPENAI_COMPUTER_USE_MODEL,
            "instructions": self._system_prompt(),
            "tools": [{"type": "computer"}],
            "store": False,
            "include": ["reasoning.encrypted_content"],
            "max_output_tokens": 4096,
        }
        items: list[dict[str, Any]] = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": f"Task: {task}\nHere is the current browser state. Begin working on the task."},
                {"type": "input_image", "image_url": f"data:{SCREENSHOT_MEDIA_TYPE};base64,{screenshot_b64}", "detail": "original"},
            ],
        }]
        actions_taken: list[str] = []

        for step in range(1, MAX_STEPS + 1):
            logger.info("Browser agent step %d/%d", step, MAX_STEPS)
            if not self._is_page_alive():
                return self._closed_summary(actions_taken)
            if not cloud_circuit.allow_request():
                return (f"Browser task paused at step {step}: the model API is temporarily "
                        "unavailable (circuit breaker open). Try again shortly.")
            try:
                response = await provider._create(input=items, **base_kwargs)
                cloud_circuit.record_success()
            except Exception as e:
                cloud_circuit.record_failure()
                logger.error("Browser agent API error: %s", e)
                return f"Browser task failed at step {step}: {str(e)[:200]}"

            output = list(getattr(response, "output", None) or [])
            items.extend(o.model_dump(mode="json", exclude_none=True) for o in output)
            calls = [o for o in output if getattr(o, "type", "") == "computer_call"]
            if not calls:
                final_text = (getattr(response, "output_text", "") or "").strip()
                logger.info("Browser agent completed: %s", final_text[:100])
                return final_text or f"Task completed after {step} steps."

            for call in calls:
                checks = list(getattr(call, "pending_safety_checks", None) or [])
                if checks:
                    # Never auto-acknowledge: a human has to review these.
                    reasons = "; ".join(c.message or c.code or "safety check" for c in checks)
                    return (f"I paused the browser task at step {step} because it needs your review: "
                            f"{reasons}. Tell me to continue once you've checked the page.")
                actions = [a.model_dump(mode="json", exclude_none=True) for a in (call.actions or [])]
                if not actions and getattr(call, "action", None) is not None:
                    actions = [call.action.model_dump(mode="json", exclude_none=True)]
                for action in actions:
                    logger.info("Browser agent action: %s", action)
                    result = await self.execute_openai_action(action)
                    if action.get("type") != "screenshot":
                        actions_taken.append(f"Step {step}: {action.get('type')} - {result}")
                await asyncio.sleep(0.5)
                shot = await self.take_screenshot()
                _prune_openai_screenshots(items)
                items.append({
                    "type": "computer_call_output",
                    "call_id": call.call_id,
                    "output": {
                        "type": "computer_screenshot",
                        "image_url": f"data:{SCREENSHOT_MEDIA_TYPE};base64,{shot}" if shot else _PLACEHOLDER_IMAGE,
                        "detail": "original",
                    },
                })

        return self._limit_summary(actions_taken)

    async def _run_anthropic_loop(self, task: str, start_url: str | None) -> str:
        from jarvis.config import settings
        from jarvis.core.hardening import cloud_circuit

        if not settings.ANTHROPIC_API_KEY:
            return "Error: ANTHROPIC_API_KEY not set. Cannot use Computer Use."
        import anthropic

        client: Any = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=3)

        screenshot_b64 = await self._prepare(start_url)
        if not screenshot_b64:
            return "Error: could not capture initial screenshot"

        computer_tool = {
            "type": COMPUTER_USE_TOOL_TYPE,
            "name": "computer",
            "display_width_px": VIEWPORT_WIDTH,
            "display_height_px": VIEWPORT_HEIGHT,
        }
        messages: list[Any] = [{
            "role": "user",
            "content": [
                {"type": "text", "text": f"Task: {task}"},
                {"type": "image", "source": {"type": "base64", "media_type": SCREENSHOT_MEDIA_TYPE, "data": screenshot_b64}},
                {"type": "text", "text": "Here is the current browser state. Begin working on the task."},
            ],
        }]
        actions_taken: list[str] = []

        for step in range(1, MAX_STEPS + 1):
            logger.info("Browser agent step %d/%d", step, MAX_STEPS)
            if step > 1:
                await asyncio.sleep(0.3)
            if not self._is_page_alive():
                return self._closed_summary(actions_taken)
            if not cloud_circuit.allow_request():
                return (f"Browser task paused at step {step}: the model API is temporarily "
                        "unavailable (circuit breaker open). Try again shortly.")
            try:
                response = await client.beta.messages.create(
                    model=COMPUTER_USE_MODEL,
                    max_tokens=1024,
                    system=self._system_prompt(),
                    tools=[computer_tool],
                    messages=messages,
                    betas=[COMPUTER_USE_BETA],
                )
                cloud_circuit.record_success()
            except Exception as e:
                cloud_circuit.record_failure()
                logger.error("Browser agent API error: %s", e)
                return f"Browser task failed at step {step}: {str(e)[:200]}"

            assistant_content = response.content
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason != "tool_use":
                final_text = "".join(getattr(b, "text", "") for b in assistant_content)
                logger.info("Browser agent completed: %s", final_text[:100])
                return final_text or f"Task completed after {step} steps."

            tool_results = []
            for block in assistant_content:
                if block.type != "tool_use":
                    continue
                tool_input = block.input
                action = str(tool_input.get("action", "screenshot"))
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
                content: list[dict[str, Any]] = []
                if new_screenshot:
                    content.append({"type": "image", "source": {
                        "type": "base64", "media_type": SCREENSHOT_MEDIA_TYPE, "data": new_screenshot,
                    }})
                content.append({"type": "text", "text": result_text})
                tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

            _prune_anthropic_screenshots(messages)
            messages.append({"role": "user", "content": tool_results})

        return self._limit_summary(actions_taken)


def _prune_openai_screenshots(items: list[dict[str, Any]]) -> None:
    """Keep the last KEEP_SCREENSHOTS - 1 screenshots (a new one is about to be added)."""
    outputs = [i for i in items if i.get("type") == "computer_call_output"]
    for item in outputs[: max(0, len(outputs) - (KEEP_SCREENSHOTS - 1))]:
        item["output"] = {**item["output"], "image_url": _PLACEHOLDER_IMAGE}


def _prune_anthropic_screenshots(messages: list[Any]) -> None:
    """Replace screenshots in older tool results with a text placeholder."""
    result_msgs = [
        m for m in messages
        if m.get("role") == "user" and isinstance(m.get("content"), list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
    ]
    for msg in result_msgs[: max(0, len(result_msgs) - (KEEP_SCREENSHOTS - 1))]:
        for block in msg["content"]:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                block["content"] = [
                    part if part.get("type") != "image" else {"type": "text", "text": "[earlier screenshot omitted]"}
                    for part in block["content"]
                ]


_browser_agent: BrowserAgent | None = None


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


async def browser_navigate(url: str) -> list[dict[str, Any]]:
    """Navigate the browser to a specific URL and return screenshot."""
    agent = _get_browser_agent()
    ok = await agent._ensure_ready()
    if not ok:
        return [{"type": "text", "text": "Error: failed to initialize browser"}]

    result = await agent.navigate(url)
    screenshot_b64 = await agent.take_screenshot()

    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"{result}\nHere is what the browser is currently showing:"}
    ]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": SCREENSHOT_MEDIA_TYPE,
                "data": screenshot_b64,
            },
        })
    else:
        content.append({"type": "text", "text": "(Screenshot capture failed)"})

    return content


async def browser_screenshot() -> list[dict[str, Any]]:
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
                "media_type": SCREENSHOT_MEDIA_TYPE,
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


async def get_browser_state() -> list[dict[str, Any]]:
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
        with contextlib.suppress(Exception):
            title = await agent._page.title()

    active_info = f"Active tab: {agent._page.url}" if agent._page else "No active tab"
    if title:
        active_info += f"\nPage title: {title}"

    screenshot_b64 = await agent.take_screenshot()

    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"{tabs_text}\n\n{active_info}\n\nCurrent view:"},
    ]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": SCREENSHOT_MEDIA_TYPE,
                "data": screenshot_b64,
            },
        })

    return content


async def browser_switch_tab(tab_number: int) -> list[dict[str, Any]]:
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
    content: list[dict[str, Any]] = [
        {"type": "text", "text": f"Switched to tab {tab_number}: {agent._page.url}"},
    ]
    if screenshot_b64:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": SCREENSHOT_MEDIA_TYPE,
                "data": screenshot_b64,
            },
        })
    return content


async def browser_upload_file(file_path: str, selector: str = "") -> str:
    """Upload a file to a file input on the current page."""
    agent = _get_browser_agent()
    if not agent._initialized or not agent._is_page_alive():
        return "Error: browser is not open."

    if not os.path.exists(file_path):
        return f"Error: file not found: {file_path}"

    try:
        file_input = agent._page.locator(selector) if selector else agent._page.locator('input[type="file"]').first

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
