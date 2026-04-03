// Background service worker: WebSocket connection to JARVIS server
// Uses chrome.alarms to survive MV3 service worker termination.

const DEFAULT_CONFIG = {
  serverUrl: "ws://localhost:8741/ws/extension",
  httpBaseUrl: "http://localhost:8741",
  reconnectIntervalMs: 3000,
  maxReconnectAttempts: 50,
  pingIntervalMs: 25000,
  alarmName: "jarvis-keepalive",
  alarmPeriodMinutes: 0.4, // ~24 seconds (minimum Chrome allows is ~0.33)
};

let ws = null;
let config = { ...DEFAULT_CONFIG };
let reconnectAttempts = 0;
let reconnectTimer = null;
let pingTimer = null;
let isConnected = false;

// --- Config ---

async function loadConfig() {
  try {
    const stored = await chrome.storage.local.get(["jarvisConfig"]);
    if (stored.jarvisConfig) {
      config = { ...DEFAULT_CONFIG, ...stored.jarvisConfig };
    }
  } catch (e) {
    console.warn("[JARVIS] Failed to load config from storage:", e);
  }
}

// --- Connection ---

function connect() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return;
  }

  console.log(`[JARVIS] Connecting to ${config.serverUrl}...`);

  try {
    ws = new WebSocket(config.serverUrl);
  } catch (e) {
    console.error("[JARVIS] WebSocket creation failed:", e);
    scheduleReconnect();
    return;
  }

  ws.onopen = () => {
    console.log("[JARVIS] Connected to JARVIS server.");
    isConnected = true;
    reconnectAttempts = 0;

    // Persist connected state so the alarm handler knows to maintain the connection
    chrome.storage.local.set({ jarvisConnected: true });

    updateBadge("on");

    ws.send(JSON.stringify({
      type: "handshake",
      client: "chrome_extension",
      version: chrome.runtime.getManifest().version,
    }));

    startPingInterval();
  };

  ws.onmessage = async (event) => {
    try {
      const msg = JSON.parse(event.data);
      await handleServerMessage(msg);
    } catch (e) {
      console.error("[JARVIS] Failed to parse server message:", e, event.data);
    }
  };

  ws.onclose = (event) => {
    console.log(`[JARVIS] Disconnected (code: ${event.code}, reason: ${event.reason})`);
    isConnected = false;
    ws = null;
    stopPingInterval();
    chrome.storage.local.set({ jarvisConnected: false });
    updateBadge("off");
    scheduleReconnect();
  };

  ws.onerror = (error) => {
    console.error("[JARVIS] WebSocket error:", error);
  };
}

function disconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
  stopPingInterval();
  if (ws) {
    ws.close(1000, "Extension disconnect");
    ws = null;
  }
  isConnected = false;
  chrome.storage.local.set({ jarvisConnected: false, jarvisUserDisconnected: true });
  updateBadge("off");
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  if (reconnectAttempts >= config.maxReconnectAttempts) {
    console.warn("[JARVIS] Max reconnect attempts reached. Relying on alarm for future retries.");
    updateBadge("off");
    // Do NOT set "error" badge permanently. The alarm will keep retrying.
    return;
  }

  reconnectAttempts++;
  const delay = Math.min(config.reconnectIntervalMs * Math.pow(1.5, reconnectAttempts - 1), 30000);
  console.log(`[JARVIS] Reconnecting in ${Math.round(delay / 1000)}s (attempt ${reconnectAttempts})...`);

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connect();
  }, delay);
}

// --- Keepalive Ping ---

function startPingInterval() {
  stopPingInterval();
  pingTimer = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, config.pingIntervalMs);
}

function stopPingInterval() {
  if (pingTimer) {
    clearInterval(pingTimer);
    pingTimer = null;
  }
}

// --- Alarm-based keepalive (survives service worker termination) ---

function ensureAlarm() {
  chrome.alarms.get(config.alarmName, (alarm) => {
    if (!alarm) {
      chrome.alarms.create(config.alarmName, {
        delayInMinutes: 0.1,
        periodInMinutes: config.alarmPeriodMinutes,
      });
      console.log("[JARVIS] Keepalive alarm created.");
    }
  });
}

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name !== config.alarmName) return;

  // Check if user explicitly disconnected (don't auto-reconnect in that case)
  const stored = await chrome.storage.local.get(["jarvisUserDisconnected"]);
  if (stored.jarvisUserDisconnected) {
    return;
  }

  // If already connected and WebSocket is open, nothing to do
  if (ws && ws.readyState === WebSocket.OPEN) {
    return;
  }

  // Service worker may have been killed and restarted. All in-memory state is gone.
  // Do a lightweight HTTP health check before attempting the full WebSocket connection.
  console.log("[JARVIS] Alarm fired. Checking if JARVIS server is reachable...");

  try {
    const healthUrl = config.httpBaseUrl + "/health/ping";
    const response = await fetch(healthUrl, {
      method: "GET",
      signal: AbortSignal.timeout(3000),
    });

    if (response.ok) {
      console.log("[JARVIS] Server is reachable. Establishing WebSocket connection...");
      reconnectAttempts = 0; // Reset since the server is confirmed alive
      connect();
    } else {
      console.log(`[JARVIS] Server responded with ${response.status}. Will retry on next alarm.`);
    }
  } catch (e) {
    // Server not reachable yet. Silently wait for next alarm cycle.
    console.log("[JARVIS] Server not reachable. Will retry on next alarm.");
  }
});

// --- Badge / Status Indicator ---

function updateBadge(status) {
  const badges = {
    on: { text: "", color: "#22c55e" },
    off: { text: "!", color: "#6b7280" },
    error: { text: "X", color: "#ef4444" },
    busy: { text: "...", color: "#f59e0b" },
  };

  const badge = badges[status] || badges.off;
  chrome.action.setBadgeText({ text: badge.text });
  chrome.action.setBadgeBackgroundColor({ color: badge.color });
}

// --- Server Message Handler ---

function sendToServer(msg) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(msg));
    return true;
  }
  console.warn("[JARVIS] Cannot send; not connected.");
  return false;
}

async function handleServerMessage(msg) {
  if (msg.type === "pong") return;  // Keepalive response

  if (msg.type !== "command") {
    console.log("[JARVIS] Non-command message:", msg.type);
    return;
  }

  const { id, action } = msg;
  updateBadge("busy");

  try {
    let result;

    switch (action) {
      case "get_tabs":
        result = await handleGetTabs();
        break;
      case "new_tab":
        result = await handleNewTab(msg.url || "about:blank");
        break;
      case "close_tab":
        result = await handleCloseTab(msg.tabId);
        break;
      case "switch_tab":
        result = await handleSwitchTab(msg.tabId);
        break;
      case "navigate":
        result = await handleNavigate(msg.url, msg.tabId);
        break;
      case "screenshot":
        result = await handleScreenshot(msg.tabId);
        break;
      case "click":
      case "type":
      case "select":
      case "scroll":
      case "read_page":
      case "read_element":
      case "find_elements":
      case "fill_form":
      case "wait_for":
        result = await routeToContentScript(msg);
        break;
      case "execute_js":
        result = await handleExecuteJs(msg.code, msg.tabId);
        break;

      default:
        result = { success: false, error: `Unknown action: ${action}` };
    }

    sendToServer({ type: "result", id, ...result });
  } catch (e) {
    console.error(`[JARVIS] Command '${action}' failed:`, e);
    sendToServer({
      type: "result",
      id,
      success: false,
      error: e.message || String(e),
    });
  } finally {
    updateBadge(isConnected ? "on" : "off");
  }
}

// --- Tab / DOM Handlers ---

async function handleGetTabs() {
  const tabs = await chrome.tabs.query({});
  const tabList = tabs.map((t) => ({
    id: t.id,
    url: t.url,
    title: t.title,
    active: t.active,
    windowId: t.windowId,
  }));
  return { success: true, data: tabList };
}

async function handleNewTab(url) {
  const tab = await chrome.tabs.create({ url, active: true });
  return { success: true, data: { tabId: tab.id, url: tab.url } };
}

async function handleCloseTab(tabId) {
  const id = tabId || (await getActiveTabId());
  if (!id) return { success: false, error: "No tab to close." };
  await chrome.tabs.remove(id);
  return { success: true, data: { closedTabId: id } };
}

async function handleSwitchTab(tabId) {
  if (!tabId) return { success: false, error: "tabId required." };
  await chrome.tabs.update(tabId, { active: true });
  const tab = await chrome.tabs.get(tabId);
  if (tab.windowId) {
    await chrome.windows.update(tab.windowId, { focused: true });
  }
  return { success: true, data: { tabId, url: tab.url, title: tab.title } };
}

async function handleNavigate(url, tabId) {
  const id = tabId || (await getActiveTabId());
  if (!id) return { success: false, error: "No active tab." };
  await chrome.tabs.update(id, { url });

  return new Promise((resolve) => {
    const listener = (updatedTabId, changeInfo) => {
      if (updatedTabId === id && changeInfo.status === "complete") {
        chrome.tabs.onUpdated.removeListener(listener);
        resolve({ success: true, data: { tabId: id, url } });
      }
    };
    chrome.tabs.onUpdated.addListener(listener);

    // Safety timeout (15 seconds)
    setTimeout(() => {
      chrome.tabs.onUpdated.removeListener(listener);
      resolve({ success: true, data: { tabId: id, url, note: "Navigation timed out but may still be loading." } });
    }, 15000);
  });
}

async function handleScreenshot(tabId) {
  const id = tabId || (await getActiveTabId());
  if (!id) return { success: false, error: "No active tab." };

  // Ensure the tab is active (captureVisibleTab only captures the active tab)
  const tab = await chrome.tabs.get(id);
  if (!tab.active) {
    await chrome.tabs.update(id, { active: true });
    await new Promise((r) => setTimeout(r, 300)); // Brief settle
  }

  const dataUrl = await chrome.tabs.captureVisibleTab(tab.windowId, {
    format: "png",
    quality: 85,
  });

  // Strip the data URL prefix to get raw base64
  const base64 = dataUrl.replace(/^data:image\/png;base64,/, "");
  return { success: true, data: { screenshot: base64, url: tab.url, title: tab.title } };
}

const _EXEC_JS_BLOCKED_PATTERNS = [
  /document\.cookie\s*=/i,
  /localStorage\s*\.\s*setItem/i,
  /XMLHttpRequest|fetch\s*\(/i,
  /window\.open\s*\(/i,
];

async function handleExecuteJs(code, tabId) {
  const id = tabId || (await getActiveTabId());
  if (!id) return { success: false, error: "No active tab." };

  // Restrict JS execution to localhost and JARVIS-related URLs only
  const tab = await chrome.tabs.get(id);
  const tabUrl = (tab.url || "").toLowerCase();
  const allowedPatterns = [
    "http://localhost",
    "http://127.0.0.1",
    "https://localhost",
    "https://127.0.0.1",
    "http://0.0.0.0",
  ];
  const isAllowed = allowedPatterns.some((p) => tabUrl.startsWith(p)) ||
    tabUrl.includes(".trycloudflare.com");

  if (!isAllowed) {
    return { success: false, error: "JS execution restricted to localhost and JARVIS tunnel URLs." };
  }

  // Block dangerous patterns
  const blocked = [
    /document\.cookie/i,
    /localStorage/i,
    /sessionStorage/i,
    /XMLHttpRequest|fetch\s*\(/i,
    /eval\s*\(/i,
    /Function\s*\(/i,
    /import\s*\(/i,
    /window\.open/i,
  ];

  for (const pattern of blocked) {
    if (pattern.test(code)) {
      return { success: false, error: `Blocked: code contains restricted pattern (${pattern.source}).` };
    }
  }

  const results = await chrome.scripting.executeScript({
    target: { tabId: id },
    func: (jsCode) => {
      try {
        const fn = new Function(jsCode);
        return { value: String(fn()), error: null };
      } catch (e) {
        return { value: null, error: e.message };
      }
    },
    args: [code],
    world: "ISOLATED",
  });

  const result = results?.[0]?.result;
  if (result?.error) {
    return { success: false, error: result.error };
  }
  return { success: true, data: { result: result?.value } };
}

// --- Content Script Router ---

async function routeToContentScript(msg) {
  const tabId = msg.tabId || (await getActiveTabId());
  if (!tabId) return { success: false, error: "No active tab." };

  // Ensure the content script is injected
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
  } catch (e) {
    // Content script may already be injected, or the page may not allow it
    console.debug("[JARVIS] Content script injection note:", e.message);
  }

  return new Promise((resolve) => {
    chrome.tabs.sendMessage(tabId, msg, (response) => {
      if (chrome.runtime.lastError) {
        resolve({
          success: false,
          error: `Content script error: ${chrome.runtime.lastError.message}`,
        });
      } else {
        resolve(response || { success: false, error: "No response from content script." });
      }
    });

    // Safety timeout
    setTimeout(() => {
      resolve({ success: false, error: "Content script response timed out (10s)." });
    }, 10000);
  });
}

// --- Utility ---

async function getActiveTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab?.id || null;
}

// --- Browser Event Listeners ---

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isConnected) {
    sendToServer({
      type: "event",
      event: "page_loaded",
      tabId,
      url: tab.url,
      title: tab.title,
    });
  }
});

chrome.tabs.onActivated.addListener(async (activeInfo) => {
  if (!isConnected) return;
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    sendToServer({
      type: "event",
      event: "tab_activated",
      tabId: activeInfo.tabId,
      url: tab.url,
      title: tab.title,
    });
  } catch (e) {
    // Tab may have been closed
  }
});

chrome.tabs.onCreated.addListener((tab) => {
  if (!isConnected) return;
  sendToServer({
    type: "event",
    event: "tab_created",
    tabId: tab.id,
    url: tab.url || "about:blank",
  });
});

chrome.tabs.onRemoved.addListener((tabId) => {
  if (!isConnected) return;
  sendToServer({
    type: "event",
    event: "tab_closed",
    tabId,
  });
});

// --- Message handler for popup and content scripts ---

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === "getStatus") {
    sendResponse({
      connected: isConnected,
      serverUrl: config.serverUrl,
      reconnectAttempts,
    });
    return true;
  }

  if (msg.type === "connect") {
    // Clear user-disconnected flag so the alarm resumes auto-reconnect
    chrome.storage.local.set({ jarvisUserDisconnected: false });
    reconnectAttempts = 0;
    connect();
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "disconnect") {
    disconnect();
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "updateConfig") {
    config = { ...config, ...msg.config };
    chrome.storage.local.set({ jarvisConfig: config });
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "sendToServer") {
    const sent = sendToServer(msg.payload);
    sendResponse({ ok: sent });
    return true;
  }
});

// --- Lifecycle events ---

chrome.runtime.onInstalled.addListener(() => {
  console.log("[JARVIS] Extension installed/updated. Setting up keepalive alarm.");
  chrome.storage.local.set({ jarvisUserDisconnected: false });
  ensureAlarm();
});

chrome.runtime.onStartup.addListener(() => {
  console.log("[JARVIS] Chrome started. Setting up keepalive alarm.");
  chrome.storage.local.set({ jarvisUserDisconnected: false });
  ensureAlarm();
});

// --- Startup ---

loadConfig().then(() => {
  console.log("[JARVIS] Background service worker started. Connecting...");
  ensureAlarm();
  connect();
});
