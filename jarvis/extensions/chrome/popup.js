const statusDot = document.getElementById("statusDot");
const statusText = document.getElementById("statusText");
const serverUrl = document.getElementById("serverUrl");
const btnConnect = document.getElementById("btnConnect");
const btnDisconnect = document.getElementById("btnDisconnect");
const btnSendPage = document.getElementById("btnSendPage");
const versionEl = document.getElementById("version");

const manifest = chrome.runtime.getManifest();
versionEl.textContent = `JARVIS Browser Bridge v${manifest.version}`;

function updateUI(status) {
  if (status.connected) {
    statusDot.className = "status-dot connected";
    statusText.textContent = "Connected to JARVIS server";
    btnConnect.style.display = "none";
    btnDisconnect.style.display = "block";
    btnSendPage.disabled = false;
  } else {
    statusDot.className = "status-dot disconnected";
    if (status.reconnectAttempts > 0) {
      statusText.textContent = `Disconnected (reconnect attempt ${status.reconnectAttempts})`;
      statusDot.className = "status-dot connecting";
    } else {
      statusText.textContent = "Not connected";
    }
    btnConnect.style.display = "block";
    btnDisconnect.style.display = "none";
    btnSendPage.disabled = true;
  }

  serverUrl.textContent = status.serverUrl || "";
}

function refreshStatus() {
  chrome.runtime.sendMessage({ type: "getStatus" }, (response) => {
    if (response) updateUI(response);
  });
}

refreshStatus();
const statusInterval = setInterval(refreshStatus, 2000);

btnConnect.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "connect" }, () => {
    statusDot.className = "status-dot connecting";
    statusText.textContent = "Connecting...";
    setTimeout(refreshStatus, 1500);
  });
});

btnDisconnect.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "disconnect" }, () => {
    refreshStatus();
  });
});

btnSendPage.addEventListener("click", async () => {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab) return;

  chrome.runtime.sendMessage({
    type: "sendToServer",
    payload: {
      type: "event",
      event: "user_shared_page",
      tabId: tab.id,
      url: tab.url,
      title: tab.title,
    },
  });

  btnSendPage.textContent = "Sent!";
  setTimeout(() => {
    btnSendPage.textContent = "Send this page to JARVIS";
  }, 2000);
});
