# JARVIS Chrome Extension: Architecture & Design

## Problem Statement

JARVIS currently uses **Playwright with Claude Computer Use** for browser automation.
This approach has several limitations:

1. **Separate browser instance**: Playwright runs its own Chromium, not the user's
   actual Chrome. Cookie sync via `pycookiecheat` is fragile and platform-specific.
2. **Vision-only interaction**: Every action requires a screenshot round-trip to Claude's
   Computer Use API, which is expensive ($0.02-0.05 per step) and slow (2-5 seconds per step).
3. **Rate limiting**: Rapid screenshot loops hit Anthropic's API rate limits, causing
   30-60 second backoff delays mid-task.
4. **No DOM access**: The agent can only "see" the page via screenshots. It cannot read
   text, query selectors, check element states, or extract structured data directly.
5. **No real session state**: Even with cookie sync, some sites detect Playwright's
   automation fingerprint and block or degrade the experience.

## Solution: JARVIS Chrome Extension

Build a Chrome extension that runs inside the user's actual Chrome browser and
communicates with JARVIS's backend server via WebSocket/HTTP. This gives JARVIS
direct access to the DOM, native authentication, and the ability to interact with
pages programmatically without vision-based guessing.

## Architecture Overview

```
+------------------+          WebSocket           +------------------+
|  Chrome Extension | <========================> |  JARVIS Server    |
|  (content script  |     ws://localhost:8741     |  (FastAPI)        |
|   + background    |     /ws/extension           |                   |
|   service worker) |                             |  brain.py         |
+------------------+                              |  llm.py           |
        |                                         |  executor.py      |
        v                                         +------------------+
  User's actual Chrome                                    |
  (all tabs, sessions,                                    v
   logins, extensions)                            Claude API (Sonnet/Opus)
```

## Extension Components

### 1. Background Service Worker (`background.js`)

The persistent (Manifest V3) service worker that:

- Maintains a WebSocket connection to `ws://localhost:8741/ws/extension`
- Routes commands from JARVIS to the correct tab's content script
- Handles tab management (create, close, switch, list)
- Sends tab/navigation events back to JARVIS
- Manages extension lifecycle and reconnection logic

Key capabilities:
- `chrome.tabs.*` API for tab management
- `chrome.scripting.*` API for injecting scripts
- `chrome.downloads.*` API for download management
- `chrome.cookies.*` API for cookie access (replaces pycookiecheat entirely)
- `chrome.history.*` and `chrome.bookmarks.*` for context

### 2. Content Script (`content.js`)

Injected into every page (or on-demand). Provides:

- **DOM querying**: Find elements by CSS selector, XPath, text content, ARIA labels
- **Element interaction**: Click, type, select, scroll to element, hover
- **Page reading**: Extract text, links, tables, form values, structured data
- **Screenshot**: `html2canvas` or native `chrome.tabs.captureVisibleTab` for screenshots
- **Mutation observer**: Watch for page changes and report them back
- **Form filling**: Intelligent form detection and auto-fill

### 3. Popup UI (`popup.html`)

Minimal UI showing:
- Connection status to JARVIS server
- Current active task (if any)
- Quick actions (e.g., "Send this page to JARVIS")
- Extension settings (server URL, auto-connect, etc.)

## Communication Protocol

### WebSocket Messages (JARVIS -> Extension)

```json
{
  "type": "command",
  "id": "cmd_123",
  "action": "click",
  "target": {
    "selector": "button.submit",
    "text": "Submit",
    "index": 0
  },
  "tabId": 12345
}
```

Supported actions:

| Action | Description | Parameters |
|--------|-------------|------------|
| `navigate` | Go to URL | `url`, `tabId?` |
| `click` | Click element | `selector` or `text` or `coordinate` |
| `type` | Type text into element | `selector`, `text`, `clear?` |
| `select` | Select dropdown option | `selector`, `value` or `text` |
| `scroll` | Scroll page | `direction`, `amount`, `selector?` |
| `read_page` | Extract page content | `format` (text/html/markdown) |
| `read_element` | Read specific element | `selector`, `attribute?` |
| `find_elements` | Query DOM | `selector` or `text`, `limit?` |
| `screenshot` | Capture visible tab | `tabId?` |
| `get_tabs` | List all tabs | none |
| `new_tab` | Open new tab | `url` |
| `close_tab` | Close tab | `tabId` |
| `switch_tab` | Activate tab | `tabId` |
| `execute_js` | Run JavaScript | `code`, `tabId?` |
| `wait_for` | Wait for element/condition | `selector`, `timeout?` |
| `fill_form` | Auto-fill a form | `fields: {selector: value}` |
| `download` | Download a file | `url`, `filename?` |

### WebSocket Messages (Extension -> JARVIS)

```json
{
  "type": "result",
  "id": "cmd_123",
  "success": true,
  "data": { ... }
}

{
  "type": "event",
  "event": "page_loaded",
  "tabId": 12345,
  "url": "https://example.com",
  "title": "Example"
}
```

Events pushed to JARVIS:

| Event | Description |
|-------|-------------|
| `page_loaded` | Tab finished loading |
| `tab_created` | New tab opened |
| `tab_closed` | Tab was closed |
| `tab_activated` | User switched tabs |
| `download_complete` | File download finished |
| `form_detected` | Page has fillable forms |
| `error` | Something went wrong |

## Integration with JARVIS

### New Tool: `chrome_extension`

Register new tools in `tools_schema.py` that use the extension instead of Playwright:

```python
# New tool functions that communicate via the Chrome extension
async def chrome_navigate(url: str, tab_id: int = None) -> str: ...
async def chrome_click(selector: str = "", text: str = "") -> str: ...
async def chrome_type(selector: str, text: str, clear: bool = False) -> str: ...
async def chrome_read_page(format: str = "text") -> str: ...
async def chrome_find_elements(selector: str = "", text: str = "") -> list: ...
async def chrome_screenshot() -> list: ...
async def chrome_get_tabs() -> str: ...
async def chrome_execute_js(code: str) -> str: ...
async def chrome_fill_form(fields: dict) -> str: ...
```

### Hybrid Mode: Extension + Computer Use Fallback

The best approach is a hybrid:

1. **Extension-first**: Use the Chrome extension for all DOM-based interactions
   (clicking, typing, reading, navigating). This is fast, free, and reliable.
2. **Computer Use fallback**: For tasks that need visual understanding (e.g.,
   "click the blue button next to the user's avatar"), fall back to a single
   screenshot via the extension + Claude vision for element identification,
   then execute via the extension's DOM methods.

This reduces Computer Use API calls from ~10-30 per task to 0-2 per task.

### Cost Comparison

| Approach | Steps for "Play 2nd YouTube video" | API Calls | Estimated Cost |
|----------|-------------------------------------|-----------|----------------|
| Current (Playwright + Computer Use) | ~10-15 steps | 10-15 | $0.20-0.75 |
| Extension + DOM only | 2-3 steps | 1 (brain decides) | $0.01-0.03 |
| Extension + Hybrid (1 screenshot) | 3-4 steps | 2 (brain + 1 vision) | $0.03-0.06 |

## Implementation Plan

### Phase 1: Chrome Extension MVP (Week 1-2)

1. Create Manifest V3 extension scaffold
2. Implement background service worker with WebSocket client
3. Implement core content script (click, type, read, navigate)
4. Add `/ws/extension` endpoint to JARVIS server
5. Register basic chrome extension tools in tools_schema.py
6. Test with simple tasks (navigate, click link, read page text)

### Phase 2: Smart Interaction (Week 3)

1. Add element discovery (find by text, ARIA role, proximity)
2. Add form detection and intelligent filling
3. Add screenshot via `chrome.tabs.captureVisibleTab`
4. Implement hybrid mode (extension screenshot + Claude vision for ambiguous targets)
5. Add tab management tools

### Phase 3: Advanced Features (Week 4+)

1. Page mutation observers for reactive task completion
2. Download management integration
3. Cookie/session access (retire pycookiecheat entirely)
4. Extension popup UI with task status
5. Support for multi-tab workflows
6. Extension auto-update and version management

## File Structure

```
jarvis/
  extensions/
    chrome/
      manifest.json           # Manifest V3 config
      background.js           # Service worker (WebSocket client)
      content.js              # DOM interaction script
      popup.html              # Extension popup UI
      popup.js                # Popup logic
      icons/                  # Extension icons
        icon-16.png
        icon-48.png
        icon-128.png
      styles/
        popup.css             # Popup styles
  tools/
    chrome_extension.py       # New tool implementations using extension
    browser_agent.py          # Existing (kept as fallback)
```

## Security Considerations

- The extension only connects to `localhost:8741` (JARVIS server). No external connections.
- The WebSocket connection is authenticated using the same PIN system JARVIS already uses.
- Content scripts run in an isolated world; they cannot access the page's JavaScript variables
  unless explicitly using `chrome.scripting.executeScript` with `world: "MAIN"`.
- The `execute_js` action should be used sparingly and logged for auditability.
- The extension should request only the minimum required permissions in `manifest.json`.

## Manifest V3 Permissions

```json
{
  "permissions": [
    "activeTab",
    "tabs",
    "scripting",
    "downloads",
    "cookies",
    "storage"
  ],
  "host_permissions": [
    "<all_urls>"
  ]
}
```

## Comparison with Claude Cowork's "Claude in Chrome"

Claude Cowork uses a Chrome extension called "Claude in Chrome" that provides similar
functionality. Key differences in our approach:

| Aspect | Claude in Chrome | JARVIS Extension |
|--------|-----------------|------------------|
| Connection | Cloud-based (Anthropic servers) | Local only (localhost:8741) |
| Auth | Anthropic account | Local PIN |
| DOM access | Yes, via content scripts | Yes, via content scripts |
| Screenshot | `captureVisibleTab` | `captureVisibleTab` + fallback to Playwright |
| Tool model | MCP tools (navigate, read_page, etc.) | JARVIS tool registry |
| Voice control | No | Yes (via JARVIS voice pipeline) |
| Offline mode | No | Yes (Ollama fallback for decisions) |
| Multi-tab | Yes | Yes (planned Phase 2) |

The JARVIS extension is essentially the same pattern but self-hosted and integrated
with JARVIS's voice, memory, and agentic systems.

## Next Steps

1. Scaffold the Chrome extension with Manifest V3
2. Add the WebSocket extension endpoint to `server.py`
3. Implement `chrome_extension.py` tool module
4. Register new tools in `tools_schema.py`
5. Test end-to-end with voice command -> brain -> extension -> DOM action -> result
