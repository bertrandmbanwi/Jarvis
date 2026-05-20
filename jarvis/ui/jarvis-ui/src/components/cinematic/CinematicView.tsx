"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import dynamic from "next/dynamic";
import { ChatMessage, OrbState } from "@/lib/types";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { unlockAudio } from "@/hooks/useJarvisWebSocket";

const ArcReactorGL = dynamic(
  () => import("./ArcReactorGL").then((mod) => mod.ArcReactorGL),
  { ssr: false }
);

const BootScreen = dynamic(
  () => import("./BootScreen").then((mod) => mod.BootScreen),
  { ssr: false }
);

interface CinematicViewProps {
  messages: ChatMessage[];
  orbState: OrbState;
  isProcessing: boolean;
  currentAmplitude?: number;
  onSendMessage?: (text: string) => void;
  disabled?: boolean;
  onBrowserMicState?: (recording: boolean) => void;
  authToken?: string | null;
}

const BOOT_DURATION_MS = 900;
const CROSSFADE_MS = 600;
const TRANSCRIPT_DISPLAY_MS = 11000;

const stateLabels: Record<OrbState, string> = {
  offline: "Offline",
  idle: "Waking up",
  ready: "Ready",
  listening: "Listening",
  thinking: "Processing",
  speaking: "Speaking",
  error: "Connection error",
};

const stateDescriptions: Record<OrbState, string> = {
  offline: "Local control link is unavailable.",
  idle: "Local interface is preparing the control link.",
  ready: "Ready when you are.",
  listening: "Listening.",
  thinking: "Working through the request.",
  speaking: "Responding.",
  error: "Something needs attention before Jarvis can respond.",
};

const stateColors: Record<OrbState, string> = {
  offline: "text-jarvis-text-dim/70",
  idle: "text-jarvis-cyan/58",
  ready: "text-jarvis-cyan/75",
  listening: "text-jarvis-cyan",
  thinking: "text-jarvis-gold",
  speaking: "text-jarvis-gold",
  error: "text-jarvis-error",
};

const stateDotStyles: Record<OrbState, string> = {
  offline: "bg-jarvis-text-muted/55 shadow-[0_0_10px_rgba(108,131,148,0.18)]",
  idle: "bg-jarvis-cyan/35 shadow-[0_0_10px_rgba(0,212,255,0.14)] animate-pulse",
  ready: "bg-jarvis-cyan/55 shadow-[0_0_12px_rgba(0,212,255,0.24)]",
  listening: "bg-jarvis-cyan shadow-[0_0_18px_rgba(0,212,255,0.55)] animate-pulse",
  thinking: "bg-jarvis-gold shadow-[0_0_18px_rgba(255,225,140,0.42)] animate-pulse",
  speaking: "bg-jarvis-gold shadow-[0_0_18px_rgba(255,225,140,0.46)]",
  error: "bg-jarvis-error shadow-[0_0_18px_rgba(255,68,68,0.42)] animate-pulse",
};

export default function CinematicView({
  messages,
  orbState,
  isProcessing,
  currentAmplitude = 0,
  onSendMessage,
  disabled = false,
  onBrowserMicState,
  authToken,
}: CinematicViewProps) {
  const [bootElapsed, setBootElapsed] = useState(0);
  const bootStartRef = useRef(Date.now());
  const [showTranscript, setShowTranscript] = useState(true);
  const [transcriptOpacity, setTranscriptOpacity] = useState(1);
  const fadeTimerRef = useRef<NodeJS.Timeout | null>(null);

  const voiceRecorderOptions = useMemo(
    () => ({ onRecordingStateChange: onBrowserMicState, authToken }),
    [onBrowserMicState, authToken]
  );
  const {
    isRecording,
    isTranscribing,
    startRecording,
    stopRecording,
    isSupported: micSupported,
    error: micError,
    onAutoStopRef,
  } = useVoiceRecorder(voiceRecorderOptions);

  useEffect(() => {
    if (onAutoStopRef) {
      onAutoStopRef.current = (text: string | null) => {
        if (text && text.trim() && onSendMessage) {
          onSendMessage(text.trim());
        }
      };
    }
    return () => {
      if (onAutoStopRef) onAutoStopRef.current = null;
    };
  }, [onAutoStopRef, onSendMessage]);

  const handleMicToggle = useCallback(async () => {
    unlockAudio();
    if (isRecording) {
      const text = await stopRecording();
      if (text && text.trim() && onSendMessage) {
        onSendMessage(text.trim());
      }
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording, onSendMessage]);

  useEffect(() => {
    const start = bootStartRef.current;
    let raf: number;

    const tick = () => {
      const elapsed = Date.now() - start;
      setBootElapsed(elapsed);
      if (elapsed < BOOT_DURATION_MS + CROSSFADE_MS + 500) {
        raf = requestAnimationFrame(tick);
      }
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, []);

  const latestAssistant = [...messages]
    .reverse()
    .find((m) => m.role === "assistant" && m.content);
  const latestUser = [...messages]
    .reverse()
    .find((m) => m.role === "user" && m.content);
  const recentMessages = useMemo(
    () => messages
      .filter((message) => Boolean(message.content))
      .slice(-4),
    [messages]
  );

  useEffect(() => {
    if (!latestAssistant && !latestUser) return;

    // Reset opacity when new message arrives
    setTranscriptOpacity(1);
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);

    if (latestAssistant) {
      fadeTimerRef.current = setTimeout(() => {
        setTranscriptOpacity(0);
      }, TRANSCRIPT_DISPLAY_MS);
    }

    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    };
  }, [latestAssistant, latestUser]);

  const toggleTranscript = useCallback(() => {
    setShowTranscript((prev) => !prev);
  }, []);

  const bootProgress =
    bootElapsed < BOOT_DURATION_MS
      ? bootElapsed / BOOT_DURATION_MS
      : 1.0 + (bootElapsed - BOOT_DURATION_MS) / CROSSFADE_MS;

  const showBoot = bootElapsed < BOOT_DURATION_MS + CROSSFADE_MS;
  const showActive = bootElapsed > BOOT_DURATION_MS - CROSSFADE_MS;

  const activeTransition = !showActive
    ? 0
    : Math.min(
        1,
        (bootElapsed - (BOOT_DURATION_MS - CROSSFADE_MS)) / CROSSFADE_MS
      );

  const hasConversation = Boolean(latestAssistant?.content || latestUser?.content);
  const isQuietStandby = orbState === "ready" || orbState === "idle";
  const showVoiceStateCard =
    orbState === "listening" ||
    orbState === "thinking" ||
    orbState === "offline" ||
    orbState === "error" ||
    isRecording ||
    isTranscribing;
  const showCommandStream =
    orbState === "thinking" ||
    (!isQuietStandby && recentMessages.length > 0);
  const showTranscriptButton = hasConversation;
  const showLiveCaption =
    isQuietStandby ||
    (showTranscript &&
      (hasConversation ||
        orbState === "speaking" ||
        orbState === "thinking" ||
        orbState === "listening" ||
        orbState === "offline" ||
        orbState === "error"));
  const captionSource = latestAssistant?.content || latestUser?.content || stateDescriptions[orbState];
  const captionText = captionSource.length > 260
    ? `${captionSource.slice(0, 260)}...`
    : captionSource;
  const captionLabel = latestAssistant?.content
    ? "Jarvis"
    : latestUser?.content
      ? "You"
      : stateLabels[orbState];
  const signalLevel = Math.min(100, Math.round(Math.max(0, currentAmplitude) * 100));
  const micStatus = isRecording ? "Open" : isTranscribing ? "Transcribing" : micSupported ? "Ready" : "Unavailable";
  const captionOpacity = latestAssistant ? transcriptOpacity : 1;

  return (
    <div className="flex-1 relative overflow-hidden ambient-stage">
      {showBoot && (
        <div className="absolute inset-0" style={{ zIndex: 2 }}>
          <BootScreen progress={bootProgress} />
        </div>
      )}

      {showActive && (
        <div
          className="absolute inset-0"
          style={{ zIndex: 1, opacity: activeTransition }}
        >
          <ArcReactorGL state={orbState} transitionIn={activeTransition} audioAmplitude={currentAmplitude} />
        </div>
      )}

      {!showBoot && (showVoiceStateCard || showCommandStream) && (
        <>
          {showVoiceStateCard && (
            <section
              className="voice-state-card absolute top-5 left-5 w-[min(22rem,calc(100vw-2.5rem))] p-4 hidden sm:block"
              style={{ zIndex: 20 }}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${stateDotStyles[orbState]}`} />
                    <span className={`text-xs font-semibold ${stateColors[orbState]}`}>
                      {stateLabels[orbState]}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-jarvis-text-dim/80">
                    {stateDescriptions[orbState]}
                  </p>
                </div>
                {isProcessing && (
                  <div className="typing-dots flex items-center pt-1">
                    <span></span>
                    <span></span>
                    <span></span>
                  </div>
                )}
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                <SignalTile label="Mic" value={micStatus} active={isRecording || isTranscribing} />
                <SignalTile label="Signal" value={`${signalLevel}%`} active={signalLevel > 3} />
                <SignalTile label="Link" value={disabled ? "Lost" : "Live"} active={!disabled} />
              </div>
            </section>
          )}

          {showCommandStream && (
            <section
              className="signal-rail absolute top-5 right-5 w-64 p-4 hidden lg:block"
              style={{ zIndex: 20 }}
            >
              <div className="flex items-center justify-between">
                <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-jarvis-text-dim/80">
                  Command stream
                </span>
                <span className="text-[10px] font-mono text-jarvis-cyan/80">
                  {recentMessages.length}
                </span>
              </div>
              <div className="mt-4 space-y-3">
                {recentMessages.length ? (
                  recentMessages.map((message) => (
                    <div key={message.id} className="flex gap-2.5">
                      <span className={`mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                        message.role === "assistant" ? "bg-jarvis-gold/70" : "bg-jarvis-cyan/70"
                      }`} />
                      <div className="min-w-0">
                        <div className="text-[10px] font-medium text-jarvis-text/75">
                          {message.role === "assistant" ? "Jarvis" : "You"}
                        </div>
                        <p className="text-[11px] leading-relaxed text-jarvis-text-dim/68 line-clamp-2">
                          {message.content}
                        </p>
                      </div>
                    </div>
                  ))
                ) : (
                  <p className="text-xs leading-relaxed text-jarvis-text-dim/70">
                    {stateDescriptions[orbState]}
                  </p>
                )}
              </div>
            </section>
          )}
        </>
      )}

      {!showBoot && showTranscriptButton && (
        <button
          onClick={toggleTranscript}
          className={`
            absolute bottom-5 right-5 w-9 h-9 rounded-xl flex items-center justify-center
            transition-all duration-300 border
            ${showTranscript
              ? "bg-jarvis-cyan/10 border-jarvis-cyan/20 text-jarvis-cyan/80"
              : "bg-white/[0.04] border-white/[0.08] text-jarvis-text-dim/50 hover:text-jarvis-text"
            }
          `}
          style={{ zIndex: 20 }}
          title={showTranscript ? "Hide transcript" : "Show transcript"}
          aria-label={showTranscript ? "Hide transcript" : "Show transcript"}
        >
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
            {showTranscript && (
              <>
                <line x1="9" y1="9" x2="15" y2="9" />
                <line x1="9" y1="13" x2="13" y2="13" />
              </>
            )}
          </svg>
        </button>
      )}

      {!showBoot && showLiveCaption && (
        <div
          className="absolute bottom-24 sm:bottom-7 left-1/2 -translate-x-1/2 w-[min(46rem,calc(100vw-2rem))] pointer-events-none"
          style={{
            zIndex: 20,
            opacity: captionOpacity,
            transition: "opacity 1.5s ease-out",
          }}
        >
          <div className="live-caption px-5 py-4">
            <div className="flex items-center justify-center gap-2 mb-2">
              <span className={`w-1.5 h-1.5 rounded-full ${stateDotStyles[orbState]}`} />
              <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-jarvis-text-dim/75">
                {captionLabel}
              </span>
            </div>
            <p className="text-sm sm:text-[15px] leading-relaxed text-center text-jarvis-text/86">
              {captionText}
            </p>
          </div>
        </div>
      )}

      {!showBoot && micSupported && (
        <div
          className="absolute bottom-5 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2.5"
          style={{ zIndex: 25 }}
        >
          {micError && (
            <div className="jarvis-glass-subtle px-3 py-1.5 rounded-xl">
              <p className="text-3xs text-red-400/70 flex items-center gap-1.5">
                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                {micError}
              </p>
            </div>
          )}

          {(isRecording || isTranscribing) && (
            <span className="text-[10px] font-semibold uppercase tracking-[0.12em] text-jarvis-cyan/80 animate-fade-in">
              {isRecording ? "Listening..." : "Transcribing..."}
            </span>
          )}

          <button
            onClick={handleMicToggle}
            disabled={disabled || isProcessing || isTranscribing}
            className={`
              relative w-14 h-14 rounded-2xl flex items-center justify-center
              transition-all duration-300 border backdrop-blur-md
              ${isRecording
                ? "bg-red-500/14 border-red-300/45 text-red-300 shadow-[0_0_26px_rgba(239,68,68,0.22)] mic-ring-pulse"
                : isTranscribing
                  ? "bg-jarvis-cyan/12 border-jarvis-cyan/25 text-jarvis-cyan/75"
                  : "bg-white/[0.07] border-white/[0.12] text-jarvis-text-dim/75 hover:text-jarvis-cyan hover:border-jarvis-cyan/35 hover:bg-jarvis-cyan/8 hover:shadow-[0_0_24px_rgba(0,190,255,0.16)]"
              }
              disabled:opacity-25 disabled:cursor-not-allowed
              active:scale-95
            `}
            title={
              isRecording
                ? "Tap to stop and send"
                : isTranscribing
                  ? "Transcribing..."
                  : "Tap to speak"
            }
            aria-label={isRecording ? "Stop recording" : "Start voice input"}
          >
            {isTranscribing ? (
              <div className="typing-dots flex items-center scale-90">
                <span></span>
                <span></span>
                <span></span>
              </div>
            ) : (
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
                <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
                <line x1="12" y1="19" x2="12" y2="23" />
                <line x1="8" y1="23" x2="16" y2="23" />
              </svg>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

function SignalTile({
  label,
  value,
  active,
}: {
  label: string;
  value: string;
  active: boolean;
}) {
  return (
    <div className="metric-tile px-3 py-2">
      <div className="text-[10px] text-jarvis-text-dim/65 font-medium">
        {label}
      </div>
      <div className={`mt-0.5 text-xs font-semibold ${active ? "text-jarvis-cyan" : "text-jarvis-text-dim/70"}`}>
        {value}
      </div>
    </div>
  );
}
