"use client";

import { useState, useCallback, useMemo, useEffect, useRef } from "react";
import { ViewMode, OrbState } from "@/lib/types";
import { useJarvisWebSocket } from "@/hooks/useJarvisWebSocket";
import { useServerStatus } from "@/hooks/useServerStatus";
import { useAuth } from "@/hooks/useAuth";
import StatusBar from "@/components/shared/StatusBar";
import ProactiveToast from "@/components/shared/ProactiveToast";
import PlanProgress from "@/components/shared/PlanProgress";
import CinematicView from "@/components/cinematic/CinematicView";
import ChatView from "@/components/chat/ChatView";
import DashboardView from "@/components/dashboard/DashboardView";
import LoginScreen from "@/components/auth/LoginScreen";
import { SettingsPanel } from "@/components/settings/SettingsPanel";

const SPEAKING_LINGER_MS = 1800;

export default function Page() {
  const authState = useAuth();
  const [viewMode, setViewMode] = useState<ViewMode>("cinematic");
  const [speakingLinger, setSpeakingLinger] = useState(false);
  const lingerTimerRef = useRef<NodeJS.Timeout | null>(null);

  const {
    status: connectionStatus,
    messages,
    costSummary,
    sendMessage,
    clearMessages,
    isProcessing,
    isStreaming,
    isVoiceSpeaking,
    currentAmplitude,
    sendBrowserMicState,
    suggestions,
    dismissSuggestion,
    activePlan,
  } = useJarvisWebSocket(authState.token);

  const { serverStatus } = useServerStatus(authState.token);

  const prevStreamingRef = useRef(false);
  const prevVoiceSpeakingRef = useRef(false);
  useEffect(() => {
    const wasStreaming = prevStreamingRef.current;
    const wasVoiceSpeaking = prevVoiceSpeakingRef.current;
    prevStreamingRef.current = isStreaming;
    prevVoiceSpeakingRef.current = isVoiceSpeaking;

    const streamingJustEnded = wasStreaming && !isStreaming;
    const voiceJustEnded = wasVoiceSpeaking && !isVoiceSpeaking;

    if (streamingJustEnded || voiceJustEnded) {
      if (!isStreaming && !isVoiceSpeaking) {
        setSpeakingLinger(true);

        if (lingerTimerRef.current) clearTimeout(lingerTimerRef.current);
        lingerTimerRef.current = setTimeout(() => {
          setSpeakingLinger(false);
        }, SPEAKING_LINGER_MS);
      }
    }

    if (isProcessing) {
      setSpeakingLinger(false);
      if (lingerTimerRef.current) {
        clearTimeout(lingerTimerRef.current);
        lingerTimerRef.current = null;
      }
    }
  }, [isStreaming, isVoiceSpeaking, isProcessing]);

  useEffect(() => {
    return () => {
      if (lingerTimerRef.current) clearTimeout(lingerTimerRef.current);
    };
  }, []);

  const orbState: OrbState = useMemo(() => {
    if (connectionStatus === "error") return "error";
    if (isProcessing) return "thinking";
    if (isStreaming) return "speaking";
    if (isVoiceSpeaking) return "speaking";
    if (speakingLinger) return "speaking";
    return "idle";
  }, [connectionStatus, isProcessing, isStreaming, isVoiceSpeaking, speakingLinger]);

  const handleChatSubmit = useCallback(
    (message: string) => {
      sendMessage(message);
    },
    [sendMessage]
  );

  const handleModeChange = useCallback((mode: ViewMode) => {
    setViewMode(mode);
  }, []);

  const sessionCost = costSummary?.sessionCostUsd ?? 0;
  const isActive = isProcessing || isStreaming;

  if (authState.isLoading) {
    return (
      <div className="h-dvh w-screen flex items-center justify-center bg-black">
        <div className="w-8 h-8 border-2 border-blue-400/40 border-t-blue-400 rounded-full animate-spin" />
      </div>
    );
  }

  if (!authState.isAuthenticated) {
    return <LoginScreen onLogin={authState.login} error={authState.loginError} />;
  }

  return (
    <div className="h-dvh w-screen flex flex-col bg-black overflow-hidden safe-top safe-bottom">
      <StatusBar
        viewMode={viewMode}
        onModeChange={handleModeChange}
        connectionStatus={connectionStatus}
        sessionCost={sessionCost}
      />

      <div
        className="flex-1 flex flex-col"
        style={{ display: viewMode === "cinematic" ? "flex" : "none" }}
      >
        <CinematicView
          messages={messages}
          orbState={orbState}
          isProcessing={isActive}
          currentAmplitude={currentAmplitude}
          onSendMessage={handleChatSubmit}
          disabled={connectionStatus !== "connected"}
          onBrowserMicState={sendBrowserMicState}
          authToken={authState.token}
        />
      </div>

      {viewMode === "chat" && (
        <ChatView
          messages={messages}
          isProcessing={isActive}
          onSendMessage={handleChatSubmit}
          onClearConversation={clearMessages}
          disabled={connectionStatus !== "connected"}
          onBrowserMicState={sendBrowserMicState}
          authToken={authState.token}
        />
      )}

      {viewMode === "dashboard" && (
        <DashboardView
          messages={messages}
          costSummary={costSummary}
          serverStatus={serverStatus}
          isProcessing={isActive}
          onClearConversation={clearMessages}
        />
      )}

      <ProactiveToast
        suggestions={suggestions}
        onDismiss={dismissSuggestion}
      />

      <PlanProgress plan={activePlan} />

      <SettingsPanel />
    </div>
  );
}
