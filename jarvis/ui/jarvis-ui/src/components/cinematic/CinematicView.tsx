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

const BOOT_DURATION_MS = 4500;
const CROSSFADE_MS = 1500;
const TRANSCRIPT_DISPLAY_MS = 8000;

const stateLabels: Record<OrbState, string> = {
  idle: "Standing By",
  listening: "Listening",
  thinking: "Processing",
  speaking: "Speaking",
  error: "Connection Error",
};

const stateColors: Record<OrbState, string> = {
  idle: "text-jarvis-cyan/40",
  listening: "text-jarvis-cyan/70",
  thinking: "text-jarvis-gold/60",
  speaking: "text-jarvis-gold/70",
  error: "text-jarvis-error/60",
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

  useEffect(() => {
    if (!latestAssistant) return;

    // Reset opacity when new message arrives
    setTranscriptOpacity(1);
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);

    fadeTimerRef.current = setTimeout(() => {
      setTranscriptOpacity(0);
    }, TRANSCRIPT_DISPLAY_MS);

    return () => {
      if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    };
  }, [latestAssistant?.id]);

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

  return (
    <div className="flex-1 relative overflow-hidden bg-black">
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

      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          zIndex: 10,
          opacity: 0.02,
          backgroundImage:
            "repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,190,255,0.08) 2px, rgba(0,190,255,0.08) 3px)",
          backgroundSize: "100% 4px",
        }}
      />

      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          zIndex: 10,
          background:
            "radial-gradient(ellipse at center, transparent 35%, rgba(0,0,0,0.6) 100%)",
        }}
      />

      <div
        className="absolute inset-x-0 top-0 h-24 pointer-events-none"
        style={{
          zIndex: 10,
          background: "linear-gradient(to bottom, rgba(0,0,0,0.5) 0%, transparent 100%)",
        }}
      />

      {!showBoot && (
        <div
          className="absolute top-4 right-5 flex items-center gap-2.5"
          style={{ zIndex: 20 }}
        >
          <div className={`w-1.5 h-1.5 rounded-full ${
            orbState === 'idle' ? 'bg-jarvis-cyan/30' :
            orbState === 'listening' ? 'bg-jarvis-cyan/60 animate-pulse' :
            orbState === 'thinking' ? 'bg-jarvis-gold/50 animate-pulse' :
            orbState === 'speaking' ? 'bg-jarvis-gold/60' :
            'bg-jarvis-error/50'
          }`} />
          <span className={`text-3xs font-mono uppercase tracking-[0.2em] ${stateColors[orbState]} transition-colors duration-500`}>
            {stateLabels[orbState]}
          </span>
          {isProcessing && (
            <div className="typing-dots flex items-center scale-75">
              <span></span>
              <span></span>
              <span></span>
            </div>
          )}
        </div>
      )}

      {!showBoot && (
        <button
          onClick={toggleTranscript}
          className={`
            absolute bottom-6 right-5 w-8 h-8 rounded-lg flex items-center justify-center
            transition-all duration-300 border
            ${showTranscript
              ? "bg-jarvis-cyan/6 border-jarvis-cyan/12 text-jarvis-cyan/50"
              : "bg-white/[0.02] border-white/[0.04] text-jarvis-text-dim/20 hover:text-jarvis-text-dim/40"
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

      {!showBoot && showTranscript && latestAssistant && (
        <div
          className="absolute bottom-20 sm:bottom-8 left-1/2 -translate-x-1/2 max-w-[75%] sm:max-w-[65%] pointer-events-none"
          style={{
            zIndex: 20,
            opacity: transcriptOpacity,
            transition: "opacity 1.5s ease-out",
          }}
        >
          <div className="jarvis-glass-subtle text-center px-5 py-3 rounded-2xl">
            <div className="text-xs leading-relaxed text-jarvis-text/50">
              {latestAssistant.content.length > 200
                ? latestAssistant.content.slice(0, 200) + "..."
                : latestAssistant.content}
            </div>
          </div>
        </div>
      )}

      {!showBoot && orbState === "speaking" && !isRecording && (
        <div
          className="absolute bottom-32 sm:bottom-28 left-1/2 -translate-x-1/2"
          style={{
            zIndex: 19,
            opacity: showTranscript && latestAssistant ? 0 : 0.5,
            transition: "opacity 0.8s ease",
          }}
        >
          <div className="flex items-center gap-2">
            <div className="w-1.5 h-1.5 rounded-full bg-jarvis-gold/50 animate-pulse" />
            <span className="text-3xs font-mono text-jarvis-gold/40 uppercase tracking-[0.15em]">
              Speaking
            </span>
          </div>
        </div>
      )}

      {!showBoot && micSupported && (
        <div
          className="absolute bottom-7 left-1/2 -translate-x-1/2 flex flex-col items-center gap-2.5"
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
            <span className="text-3xs font-mono uppercase tracking-[0.15em] text-jarvis-cyan/50 animate-fade-in">
              {isRecording ? "Listening..." : "Transcribing..."}
            </span>
          )}

          <button
            onClick={handleMicToggle}
            disabled={disabled || isProcessing || isTranscribing}
            className={`
              relative w-14 h-14 rounded-2xl flex items-center justify-center
              transition-all duration-300 border-2 backdrop-blur-md
              ${isRecording
                ? "bg-red-500/12 border-red-400/40 text-red-400 shadow-[0_0_24px_rgba(239,68,68,0.2)] mic-ring-pulse"
                : isTranscribing
                  ? "bg-jarvis-cyan/8 border-jarvis-cyan/20 text-jarvis-cyan/50"
                  : "bg-white/[0.03] border-white/[0.08] text-jarvis-text-dim/40 hover:text-jarvis-cyan hover:border-jarvis-cyan/30 hover:bg-jarvis-cyan/5 hover:shadow-[0_0_20px_rgba(0,190,255,0.12)]"
              }
              disabled:opacity-15 disabled:cursor-not-allowed
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
