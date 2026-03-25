"use client";

import { useState, useEffect, useCallback } from "react";
import { ServerStatus } from "@/lib/types";

function getApiBaseUrl(): string {
  if (typeof window === "undefined") return "http://localhost:8741";
  const port = window.location.port;
  const hostname = window.location.hostname;
  const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
  if ((!port || port === "443" || port === "80") && !isLocal) {
    return `${window.location.origin}/jarvis-api`;
  }
  return `${window.location.protocol}//${hostname}:8741`;
}
const STATUS_URL = `${getApiBaseUrl()}/`;
const POLL_INTERVAL_MS = 10000;

export function useServerStatus(authToken?: string | null) {
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const headers: Record<string, string> = {};
      if (authToken) {
        headers["Authorization"] = `Bearer ${authToken}`;
      }
      const resp = await fetch(STATUS_URL, { headers });
      if (resp.ok) {
        const data = await resp.json();
        setServerStatus({
          status: data.status,
          version: data.version,
          uptimeSeconds: data.uptime_seconds,
          activeBackend: data.active_backend,
          activeModel: data.active_model,
          memoryStats: data.memory_stats,
          conversationTurns: data.conversation_turns,
          sessionCost: {
            sessionCostUsd: data.session_cost?.session_cost_usd || 0,
            totalRequests: data.session_cost?.total_requests || 0,
            requestsByTier: data.session_cost?.requests_by_tier || {},
            totalInputTokens: data.session_cost?.total_input_tokens || 0,
            totalOutputTokens: data.session_cost?.total_output_tokens || 0,
            cacheReadTokens: data.session_cost?.cache_read_tokens || 0,
            cacheCreationTokens: data.session_cost?.cache_creation_tokens || 0,
            activeBackend: data.session_cost?.active_backend || "unknown",
          },
        });
      }
    } catch {
      // Server not reachable; leave status as null
    } finally {
      setIsLoading(false);
    }
  }, [authToken]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  return { serverStatus, isLoading, refetch: fetchStatus };
}
