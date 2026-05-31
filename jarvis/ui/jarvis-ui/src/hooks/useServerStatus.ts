"use client";

import { useState, useEffect, useCallback } from "react";
import { ServerStatus } from "@/lib/types";
import { getApiBaseUrl, jarvisHeaders } from "@/lib/apiBase";
const STATUS_URL = `${getApiBaseUrl()}/`;
const POLL_INTERVAL_MS = 10000;

function mapSavings(data: any) {
  if (!data) return undefined;
  return {
    startedAt: data.started_at || 0,
    uptimeSeconds: data.uptime_seconds || 0,
    localRoutes: data.local_routes || 0,
    paidCallsAvoided: data.paid_calls_avoided || 0,
    freeApiCalls: data.free_api_calls || 0,
    cacheHits: data.cache_hits || 0,
    byAction: data.by_action || {},
    byProvider: data.by_provider || {},
    lastEvent: data.last_event ? {
      action: data.last_event.action || "",
      toolName: data.last_event.tool_name || "",
      provider: data.last_event.provider || "Local",
      cacheHit: Boolean(data.last_event.cache_hit),
      timestamp: data.last_event.timestamp || 0,
    } : null,
  };
}

export function useServerStatus(authToken?: string | null) {
  const [serverStatus, setServerStatus] = useState<ServerStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchStatus = useCallback(async () => {
    try {
      const headers = jarvisHeaders(authToken);
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
          localSavings: mapSavings(data.local_savings),
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
