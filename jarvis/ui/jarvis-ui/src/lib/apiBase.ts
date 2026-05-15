"use client";

export function isTunnelMode(): boolean {
  if (typeof window === "undefined") return false;
  const port = window.location.port;
  const hostname = window.location.hostname;
  const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
  return (!port || port === "443" || port === "80") && !isLocal;
}

export function getApiBaseUrl(): string {
  if (typeof window === "undefined") return "http://localhost:8741";
  if (isTunnelMode()) {
    return `${window.location.origin}/jarvis-api`;
  }
  return `${window.location.protocol}//${window.location.hostname}:8741`;
}

export function getWsUrl(): string {
  if (typeof window === "undefined") return "ws://localhost:8741/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  if (isTunnelMode()) {
    return `${proto}//${window.location.host}/jarvis-ws`;
  }
  return `${proto}//${window.location.hostname}:8741/ws`;
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
