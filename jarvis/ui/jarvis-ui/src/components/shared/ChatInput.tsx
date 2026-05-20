"use client";

import { useState, useRef, useCallback, useMemo, useEffect } from "react";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { unlockAudio } from "@/hooks/useJarvisWebSocket";

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
  isProcessing?: boolean;
  onBrowserMicState?: (recording: boolean) => void;
  authToken?: string | null;
}

export default function ChatInput({
  onSubmit,
  disabled = false,
  isProcessing = false,
  onBrowserMicState,
  authToken,
}: ChatInputProps) {
  const [message, setMessage] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
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
        if (text && text.trim()) {
          onSubmit(text.trim());
        }
      };
    }
    return () => {
      if (onAutoStopRef) onAutoStopRef.current = null;
    };
  }, [onAutoStopRef, onSubmit]);

  const handleSubmit = useCallback(() => {
    if (message.trim() && !disabled && !isProcessing) {
      unlockAudio();
      onSubmit(message);
      setMessage("");
      inputRef.current?.focus();
    }
  }, [message, disabled, isProcessing, onSubmit]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleMicToggle = useCallback(async () => {
    unlockAudio();
    if (isRecording) {
      const text = await stopRecording();
      if (text && text.trim()) {
        onSubmit(text.trim());
      }
    } else {
      await startRecording();
    }
  }, [isRecording, startRecording, stopRecording, onSubmit]);

  const isBusy = disabled || isProcessing || isTranscribing;
  const hasMessage = message.trim().length > 0;

  return (
    <div className="w-full border-t border-white/[0.04] bg-jarvis-surface/80 backdrop-blur-xl px-4 sm:px-6 py-3 flex-shrink-0">
      <div className="flex items-center gap-2.5 sm:gap-3 max-w-3xl mx-auto">
        {micSupported && (
          <button
            onClick={handleMicToggle}
            disabled={isBusy && !isRecording}
            title={
              isRecording
                ? "Stop recording"
                : isTranscribing
                  ? "Transcribing..."
                  : "Tap to speak"
            }
            className={`
              relative flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center
              transition-all duration-200 ease-out border
              ${isRecording
                ? "bg-red-500/15 border-red-400/30 text-red-400 mic-ring-pulse"
                : isTranscribing
                  ? "bg-jarvis-cyan/8 border-jarvis-cyan/15 text-jarvis-cyan/50"
                  : "bg-white/[0.03] border-white/[0.06] text-jarvis-text-dim/45 hover:text-jarvis-cyan hover:border-jarvis-cyan/25 hover:bg-jarvis-cyan/5"
              }
              disabled:opacity-25 disabled:cursor-not-allowed
              active:scale-95
            `}
            aria-label={isRecording ? "Stop recording" : "Start voice input"}
          >
            {isTranscribing ? (
              <div className="typing-dots flex items-center scale-75">
                <span></span>
                <span></span>
                <span></span>
              </div>
            ) : (
              <svg
                width="17"
                height="17"
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
        )}

        <input
          ref={inputRef}
          type="text"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            isRecording
              ? "Listening... tap mic to stop"
              : isTranscribing
                ? "Transcribing..."
                : "Ask JARVIS anything..."
          }
          disabled={isBusy}
          className="jarvis-input flex-1"
          aria-label="Message input"
        />

        <button
          onClick={handleSubmit}
          disabled={isBusy || !hasMessage}
          className={`
            flex-shrink-0 w-10 h-10 rounded-xl flex items-center justify-center
            transition-all duration-200 ease-out border
            ${hasMessage && !isBusy
              ? "bg-jarvis-cyan/12 border-jarvis-cyan/25 text-jarvis-cyan hover:bg-jarvis-cyan/18 hover:border-jarvis-cyan/40 hover:shadow-[0_0_12px_rgba(0,212,255,0.15)]"
              : "bg-white/[0.02] border-white/[0.05] text-jarvis-text-dim/25"
            }
            disabled:opacity-25 disabled:cursor-not-allowed
            active:scale-95
          `}
          aria-label="Send message"
        >
          {isProcessing ? (
            <div className="typing-dots flex items-center scale-75">
              <span></span>
              <span></span>
              <span></span>
            </div>
          ) : (
            <svg
              width="17"
              height="17"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={`transition-transform duration-200 ${hasMessage ? 'translate-x-0.5 -translate-y-0.5' : ''}`}
            >
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </button>
      </div>

      {micError && (
        <div className="max-w-3xl mx-auto mt-2">
          <p className="text-3xs text-jarvis-error/60 flex items-center gap-1.5">
            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {micError}
          </p>
        </div>
      )}
    </div>
  );
}
