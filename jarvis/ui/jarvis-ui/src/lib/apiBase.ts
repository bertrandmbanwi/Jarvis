"use client";

export function isTunnelMode(): boolean {
  if (typeof window === "undefined") return false;
  const port = window.location.port;
  const hostname = window.location.hostname;
  const isLocal = isLoopbackHost(hostname);
  return (!port || port === "443" || port === "80") && !isLocal;
}

function getConfiguredApiPort(): string {
  return process.env.NEXT_PUBLIC_JARVIS_API_PORT || "8741";
}

function isLoopbackHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") return `http://localhost:${getConfiguredApiPort()}`;
  return `${window.location.origin}/jarvis-api`;
}

export function getWsUrl(): string {
  const apiPort = getConfiguredApiPort();
  if (typeof window === "undefined") return `ws://localhost:${apiPort}/ws`;
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (isLoopbackHost(window.location.hostname)) {
    return `${proto}//${window.location.hostname}:${apiPort}/ws`;
  }
  return `${proto}//${window.location.host}/jarvis-ws`;
}

export function jarvisHeaders(
  authToken?: string | null,
  json = false,
): Record<string, string> {
  const headers: Record<string, string> = {
    "X-JARVIS-Client": "jarvis-ui",
  };
  if (json) {
    headers["Content-Type"] = "application/json";
  }
  if (authToken) {
    headers.Authorization = `Bearer ${authToken}`;
  }
  return headers;
}
