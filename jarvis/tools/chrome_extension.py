"""WebSocket bridge to JARVIS Chrome Extension for DOM-based browser automation."""

import asyncio
import json
import logging
import uuid
from typing import Optional

logger = logging.getLogger("jarvis.tools.chrome_extension")

_extension_ws = None
_pending_commands: dict[str, asyncio.Future] = {}

COMMAND_TIMEOUT = 15.0


def set_extension_ws(ws):
    """Register the Chrome extension's WebSocket connection."""
    global _extension_ws
    _extension_ws = ws
    logger.info("Chrome extension WebSocket registered.")


def clear_extension_ws():
    """Clear the extension WebSocket reference on disconnect."""
    global _extension_ws
    _extension_ws = None
    for cmd_id, future in _pending_commands.items():
        if not future.done():
            future.set_exception(ConnectionError("Chrome extension disconnected."))
    _pending_commands.clear()
    logger.info("Chrome extension WebSocket cleared.")


def is_extension_connected() -> bool:
    """Check if the Chrome extension is currently connected."""
    return _extension_ws is not None


async def handle_extension_message(data: dict):
    """Handle incoming message from the Chrome extension."""
    msg_type = data.get("type")

    if msg_type == "result":
        cmd_id = data.get("id")
        if cmd_id and cmd_id in _pending_commands:
            future = _pending_commands.pop(cmd_id)
            if not future.done():
                future.set_result(data)
        else:
            logger.warning("Received result for unknown command ID: %s", cmd_id)

    elif msg_type == "event":
        event_name = data.get("event", "unknown")
        logger.info(
            "Chrome extension event: %s (tab: %s, url: %s)",
            event_name,
            data.get("tabId", "?"),
            data.get("url", "?")[:80],
        )

    elif msg_type == "handshake":
        logger.info(
            "Chrome extension connected (version: %s)",
            data.get("version", "unknown"),
        )

    elif msg_type == "ping":
        if _extension_ws:
            try:
                await _extension_ws.send_json({"type": "pong"})
            except Exception:
                pass


async def _send_command(action: str, **params) -> dict:
    """Send a command to the Chrome extension and wait for the response."""
    if not is_extension_connected():
        raise ConnectionError(
            "Chrome extension is not connected. "
            "Install and enable the JARVIS Browser Bridge extension in Chrome."
        )

    cmd_id = f"cmd_{uuid.uuid4().hex[:12]}"
    command = {
        "type": "command",
        "id": cmd_id,
        "action": action,
        **params,
    }

    loop = asyncio.get_running_loop()
    future = loop.create_future()
    _pending_commands[cmd_id] = future

    try:
        await _extension_ws.send_json(command)
        result = await asyncio.wait_for(future, timeout=COMMAND_TIMEOUT)
        return result
    except asyncio.TimeoutError:
        _pending_commands.pop(cmd_id, None)
        raise TimeoutError(
            f"Chrome extension command '{action}' timed out after {COMMAND_TIMEOUT}s."
        )
    except Exception:
        _pending_commands.pop(cmd_id, None)
        raise


async def chrome_navigate(url: str, tab_id: int = None, new_tab: bool = False) -> str:
    """Navigate a Chrome tab to a URL; avoids navigating JARVIS UI tabs."""
    try:
        if not tab_id and not new_tab:
            try:
                tabs_result = await _send_command("get_tabs")
                if tabs_result.get("success"):
                    tabs = tabs_result.get("data", [])
                    active_tab = next((t for t in tabs if t.get("active")), None)
                    if active_tab:
                        active_url = (active_tab.get("url") or "").lower()
                        jarvis_patterns = [
                            "localhost:3000", "localhost:3741",
                            "0.0.0.0:3000", "0.0.0.0:3741",
                            ".trycloudflare.com",
                        ]
                        is_jarvis_tab = any(p in active_url for p in jarvis_patterns)
                        if is_jarvis_tab:
                            # Find an existing non-JARVIS, non-extension tab to reuse
                            reuse_tab = None
                            for t in tabs:
                                t_url = (t.get("url") or "").lower()
                                skip = (
                                    any(p in t_url for p in jarvis_patterns)
                                    or t_url.startswith("chrome://")
                                    or t_url.startswith("chrome-extension://")
                                    or t_url == "about:blank"
                                )
                                if not skip and t.get("id") != active_tab.get("id"):
                                    reuse_tab = t
                                    break
                            if reuse_tab:
                                tab_id = reuse_tab["id"]
                                logger.info(
                                    "Active tab is JARVIS UI; reusing tab %s instead.",
                                    tab_id,
                                )
                            else:
                                new_tab = True
                                logger.info(
                                    "Active tab is JARVIS UI; opening new tab for navigation."
                                )
            except Exception as e:
                logger.debug("Tab check failed (proceeding with default): %s", e)

        if new_tab:
            result = await _send_command("new_tab", url=url)
        else:
            params = {"url": url}
            if tab_id:
                params["tabId"] = tab_id
            result = await _send_command("navigate", **params)

        if result.get("success"):
            data = result.get("data", {})
            return f"Navigated to {url} (tab {data.get('tabId', '?')})"
        else:
            return f"Navigation failed: {result.get('error', 'unknown error')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_click(selector: str = "", text: str = "", index: int = 0) -> str:
    """Click an element in the active Chrome tab by selector or text."""
    try:
        target = {}
        if selector:
            target["selector"] = selector
        if text:
            target["text"] = text
        if index:
            target["index"] = index

        result = await _send_command("click", target=target)

        if result.get("success"):
            clicked = result.get("data", {}).get("clicked", {})
            desc = clicked.get("text", clicked.get("selector", "element"))[:80]
            return f"Clicked: {desc}"
        else:
            return f"Click failed: {result.get('error', 'element not found')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_type(selector: str, text: str, clear: bool = False) -> str:
    """Type text into an input field in the active Chrome tab."""
    try:
        result = await _send_command(
            "type",
            target={"selector": selector},
            text=text,
            clear=clear,
        )

        if result.get("success"):
            return f"Typed '{text[:50]}' into {selector}"
        else:
            return f"Type failed: {result.get('error', 'element not found')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_read_page(format: str = "text") -> str:
    """Read the content of the active Chrome tab; faster than OCR."""
    try:
        result = await _send_command("read_page", format=format)

        if result.get("success"):
            data = result.get("data", {})
            title = data.get("title", "")
            url = data.get("url", "")
            text = data.get("text", "")

            output = f"Page: {title}\nURL: {url}\n\n{text}"

            links = data.get("links", [])
            if links:
                output += "\n\nLinks:\n"
                for link in links[:20]:
                    output += f"  - [{link.get('text', '')}]({link.get('href', '')})\n"

            return output[:15000]  # Cap output size
        else:
            return f"Read failed: {result.get('error', 'unknown error')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_find_elements(selector: str = "", text: str = "", limit: int = 10) -> str:
    """Find elements on the active Chrome tab matching a selector or text."""
    try:
        target = {}
        if selector:
            target["selector"] = selector
        if text:
            target["text"] = text

        result = await _send_command("find_elements", target=target, limit=limit)

        if result.get("success"):
            data = result.get("data", {})
            count = data.get("count", 0)
            elements = data.get("elements", [])

            if count == 0:
                return "No matching elements found."

            output = f"Found {count} element(s):\n"
            for i, el in enumerate(elements):
                tag = el.get("tag", "?")
                el_text = el.get("text", "")[:60]
                sel = el.get("selector", "")
                href = el.get("href", "")
                visible = "visible" if el.get("visible") else "hidden"

                line = f"  {i + 1}. <{tag}> {el_text}"
                if href:
                    line += f" [href={href[:60]}]"
                line += f" ({visible})"
                output += line + "\n"

            return output
        else:
            return f"Find failed: {result.get('error', 'unknown error')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_screenshot() -> list:
    """Take a screenshot of the active Chrome tab using captureVisibleTab API."""
    try:
        result = await _send_command("screenshot")

        if result.get("success"):
            data = result.get("data", {})
            screenshot_b64 = data.get("screenshot", "")
            url = data.get("url", "unknown")
            title = data.get("title", "")

            if screenshot_b64:
                return [
                    {
                        "type": "text",
                        "text": f"Chrome screenshot of: {title} ({url})",
                    },
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": screenshot_b64,
                        },
                    },
                ]
            return [{"type": "text", "text": "Screenshot captured but no image data returned."}]
        else:
            return [{"type": "text", "text": f"Screenshot failed: {result.get('error', 'unknown')}"}]
    except (ConnectionError, TimeoutError) as e:
        return [{"type": "text", "text": f"Error: {e}"}]


async def chrome_get_tabs() -> str:
    """List all open Chrome tabs."""
    try:
        result = await _send_command("get_tabs")

        if result.get("success"):
            tabs = result.get("data", [])
            if not tabs:
                return "No tabs open."

            output = f"Open Chrome tabs ({len(tabs)}):\n"
            for tab in tabs:
                active = " (active)" if tab.get("active") else ""
                output += (
                    f"  Tab {tab.get('id')}: {tab.get('title', 'Untitled')[:60]}{active}\n"
                    f"    URL: {tab.get('url', 'about:blank')}\n"
                )
            return output
        else:
            return f"Failed to list tabs: {result.get('error', 'unknown')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_execute_js(code: str) -> str:
    """Execute JavaScript in the active Chrome tab (MAIN world context)."""
    try:
        result = await _send_command("execute_js", code=code)

        if result.get("success"):
            return f"JS result: {result.get('data', {}).get('result', 'undefined')}"
        else:
            return f"JS error: {result.get('error', 'unknown')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_fill_form(fields: dict) -> str:
    """Fill multiple form fields at once in the active Chrome tab."""
    try:
        result = await _send_command("fill_form", fields=fields)

        if result.get("success"):
            filled = result.get("data", {}).get("filled", [])
            success_count = sum(1 for f in filled if f.get("success"))
            return f"Filled {success_count}/{len(filled)} form fields."
        else:
            return f"Form fill failed: {result.get('error', 'unknown')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"


async def chrome_scroll(direction: str = "down", amount: int = 3) -> str:
    """Scroll the active Chrome tab."""
    try:
        result = await _send_command("scroll", direction=direction, amount=amount)

        if result.get("success"):
            data = result.get("data", {})
            return (
                f"Scrolled {direction} by {amount}. "
                f"Position: {data.get('scrollY', '?')}px / {data.get('scrollHeight', '?')}px"
            )
        else:
            return f"Scroll failed: {result.get('error', 'unknown')}"
    except (ConnectionError, TimeoutError) as e:
        return f"Error: {e}"
