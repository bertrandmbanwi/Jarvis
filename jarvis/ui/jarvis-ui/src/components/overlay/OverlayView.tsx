"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getWsUrl } from "@/lib/apiBase";
import { OrbState } from "@/lib/types";
import { ArcReactorGL } from "@/components/cinematic/ArcReactorGL";

const STATE_LABELS: Record<OrbState, string> = {
  idle: "STANDING BY",
  listening: "LISTENING",
  thinking: "PROCESSING",
  speaking: "SPEAKING",
  error: "ATTENTION",
};

const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 50;

declare global {
  interface Window {
    jarvisActivateVoice?: () => void;
  }
}

function getOverlayWsUrl(): string {
  return getWsUrl().replace(/\/ws$/, "/ws/overlay");
}

function normalizeState(state: unknown): OrbState {
  return typeof state === "string" && state in STATE_LABELS ? (state as OrbState) : "idle";
}

export function OverlayView() {
  const [orbState, setOrbState] = useState<OrbState>("idle");
  const [responseText, setResponseText] = useState("");
  const [userText, setUserText] = useState("");
  const [audioAmplitude, setAudioAmplitude] = useState(0);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const voiceSpeakingRef = useRef(false);
  const stateRef = useRef<OrbState>("idle");
  const currentAudioAmpRef = useRef(0);
  const amplitudeEnvelopeRef = useRef<number[]>([]);
  const amplitudeDurationRef = useRef(0);
  const amplitudeStartMsRef = useRef(0);
  const rafRef = useRef<number | null>(null);
  const lastAmplitudePushRef = useRef(0);

  const applyState = useCallback((nextState: unknown) => {
    const normalized = normalizeState(nextState);
    stateRef.current = normalized;
    setOrbState(normalized);
  }, []);

  const sendOverlayCommand = useCallback((command: string): boolean => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      return false;
    }
    ws.send(JSON.stringify({ command }));
    return true;
  }, []);

  const setVoiceSpeaking = useCallback((speaking: boolean) => {
    voiceSpeakingRef.current = speaking;
    if (speaking) {
      if (stateRef.current !== "speaking") applyState("speaking");
      return;
    }

    amplitudeEnvelopeRef.current = [];
    amplitudeDurationRef.current = 0;
    currentAudioAmpRef.current = 0;
    setAudioAmplitude(0);
    setResponseText("");
    setUserText("");
    if (stateRef.current === "speaking") applyState("idle");
  }, [applyState]);

  const startAmplitudeEnvelope = useCallback((envelope: number[], duration: number) => {
    amplitudeEnvelopeRef.current = envelope;
    amplitudeDurationRef.current = duration;
    amplitudeStartMsRef.current = performance.now();
    currentAudioAmpRef.current = 0;
    setVoiceSpeaking(true);
  }, [setVoiceSpeaking]);

  useEffect(() => {
    document.documentElement.classList.add("jarvis-overlay-document");
    return () => {
      document.documentElement.classList.remove("jarvis-overlay-document");
    };
  }, []);

  useEffect(() => {
    window.jarvisActivateVoice = () => {
      applyState("listening");
      setUserText("");
      setResponseText("");
      sendOverlayCommand("activate_voice");
    };

    return () => {
      delete window.jarvisActivateVoice;
    };
  }, [applyState, sendOverlayCommand]);

  useEffect(() => {
    let closed = false;

    const connect = () => {
      if (closed) return;

      try {
        const ws = new WebSocket(getOverlayWsUrl());
        wsRef.current = ws;

        ws.onopen = () => {
          reconnectAttemptsRef.current = 0;
        };

        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data);
            if (data.activationAccepted === false) applyState("idle");
            if (data.state) applyState(data.state);
            if (data.text !== undefined) setResponseText(String(data.text || ""));
            if (data.userText !== undefined) setUserText(String(data.userText || ""));
            if (data.voiceSpeaking !== undefined || data.voice_speaking !== undefined) {
              setVoiceSpeaking(Boolean(data.voiceSpeaking ?? data.voice_speaking));
            }

            const envelope = data.amplitudeEnvelope || data.amplitude_envelope;
            const duration = data.audioDuration || data.audio_duration;
            if (Array.isArray(envelope) && duration > 0) {
              startAmplitudeEnvelope(envelope.map(Number), Number(duration));
            }
          } catch (error) {
            console.error("Overlay WS parse error:", error);
          }
        };

        ws.onclose = () => {
          if (closed || reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) return;
          reconnectAttemptsRef.current += 1;
          reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
        };

        ws.onerror = (error) => {
          console.error("Overlay WS error:", error);
        };
      } catch (error) {
        console.error("Overlay WS connection failed:", error);
        reconnectTimerRef.current = setTimeout(connect, RECONNECT_DELAY_MS);
      }
    };

    connect();

    return () => {
      closed = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [applyState, setVoiceSpeaking, startAmplitudeEnvelope]);

  useEffect(() => {
    const nextAudioAmplitude = () => {
      const envelope = amplitudeEnvelopeRef.current;
      const duration = amplitudeDurationRef.current;

      if (envelope.length > 0 && duration > 0) {
        const elapsed = (performance.now() - amplitudeStartMsRef.current) / 1000;
        if (elapsed < duration) {
          const progress = elapsed / duration;
          const envelopeIndex = Math.min(Math.floor(progress * envelope.length), envelope.length - 1);
          const targetAmp = Number(envelope[envelopeIndex]) || 0;
          currentAudioAmpRef.current += (targetAmp - currentAudioAmpRef.current) * 0.35;
          return currentAudioAmpRef.current;
        }

        amplitudeEnvelopeRef.current = [];
        amplitudeDurationRef.current = 0;
      }

      if (voiceSpeakingRef.current || stateRef.current === "speaking") {
        const elapsed = performance.now() / 1000;
        const syllable = Math.pow((Math.sin(elapsed * 10.0) + 1) * 0.5, 2.2);
        const carrier = Math.pow((Math.sin(elapsed * 17.0 + 0.8) + 1) * 0.5, 1.8);
        const targetAmp = 0.18 + syllable * 0.34 + carrier * 0.18;
        currentAudioAmpRef.current += (targetAmp - currentAudioAmpRef.current) * 0.22;
        return currentAudioAmpRef.current;
      }

      currentAudioAmpRef.current *= 0.86;
      return currentAudioAmpRef.current;
    };

    const animate = () => {
      const now = performance.now();
      const amplitude = nextAudioAmplitude();
      if (now - lastAmplitudePushRef.current > 33) {
        lastAmplitudePushRef.current = now;
        setAudioAmplitude(amplitude);
      }
      rafRef.current = window.requestAnimationFrame(animate);
    };

    rafRef.current = window.requestAnimationFrame(animate);

    return () => {
      if (rafRef.current) window.cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const visibleResponse = responseText.length > 180 ? `${responseText.slice(0, 180)}...` : responseText;

  return (
    <main className="overlay-root">
      <div className="overlay-status-row">
        <div className={`overlay-status-dot ${orbState}`} />
        <div className={`overlay-status-label ${orbState}`}>{STATE_LABELS[orbState]}</div>
      </div>
      <div className="overlay-orb">
        <ArcReactorGL state={orbState} transitionIn={1} audioAmplitude={audioAmplitude} />
      </div>
      <div className="overlay-text-area">
        <div className={`overlay-user-text ${userText ? "visible" : ""}`}>{userText ? `"${userText}"` : ""}</div>
        <div className={`overlay-response-text ${visibleResponse ? "visible" : ""}`}>{visibleResponse}</div>
      </div>

      <style>{`
        html.jarvis-overlay-document,
        html.jarvis-overlay-document body {
          background: transparent !important;
        }

        .overlay-root {
          position: relative;
          width: 100vw;
          height: 100vh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: flex-start;
          padding: 18px 10px 8px;
          overflow: hidden;
          background: transparent;
          font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif;
          -webkit-font-smoothing: antialiased;
        }

        .overlay-status-row {
          position: relative;
          z-index: 10;
          display: flex;
          align-items: center;
          gap: 8px;
          margin-top: 2px;
          text-shadow: 0 0 10px rgba(0, 0, 0, 0.78);
        }

        .overlay-status-dot {
          width: 6px;
          height: 6px;
          border-radius: 50%;
          background: rgba(0, 212, 255, 0.3);
          transition: background 0.5s ease, box-shadow 0.5s ease;
        }

        .overlay-status-dot.listening {
          background: rgba(0, 212, 255, 0.7);
          box-shadow: 0 0 8px rgba(0, 212, 255, 0.4);
          animation: overlayDotPulse 1.2s ease-in-out infinite;
        }

        .overlay-status-dot.thinking {
          background: rgba(255, 225, 140, 0.6);
          box-shadow: 0 0 8px rgba(255, 225, 140, 0.3);
          animation: overlayDotPulse 0.8s ease-in-out infinite;
        }

        .overlay-status-dot.speaking {
          background: rgba(255, 225, 140, 0.7);
          box-shadow: 0 0 10px rgba(255, 225, 140, 0.4);
        }

        .overlay-status-dot.error {
          background: rgba(255, 80, 40, 0.72);
          box-shadow: 0 0 10px rgba(255, 80, 40, 0.42);
        }

        @keyframes overlayDotPulse {
          0%, 100% {
            opacity: 0.5;
            transform: scale(1);
          }
          50% {
            opacity: 1;
            transform: scale(1.3);
          }
        }

        .overlay-status-label {
          color: rgba(0, 212, 255, 0.35);
          font-size: 9px;
          font-weight: 500;
          letter-spacing: 0.2em;
          line-height: 1.5;
          text-transform: uppercase;
          text-shadow: 0 0 12px rgba(0, 0, 0, 0.85);
          transition: color 0.5s ease;
        }

        .overlay-status-label.listening { color: rgba(0, 212, 255, 0.65); }
        .overlay-status-label.thinking { color: rgba(255, 225, 140, 0.55); }
        .overlay-status-label.speaking { color: rgba(255, 225, 140, 0.65); }
        .overlay-status-label.error { color: rgba(255, 120, 90, 0.72); }

        .overlay-orb {
          position: relative;
          z-index: 5;
          width: 260px;
          height: 260px;
          flex-shrink: 0;
          overflow: hidden;
          border-radius: 50%;
          background:
            radial-gradient(
              circle,
              rgba(0, 5, 12, 0.86) 0%,
              rgba(0, 9, 18, 0.68) 45%,
              rgba(0, 8, 18, 0.28) 70%,
              transparent 88%
            );
          -webkit-mask-image: radial-gradient(circle, #000 0%, #000 66%, rgba(0, 0, 0, 0.72) 76%, transparent 88%);
          mask-image: radial-gradient(circle, #000 0%, #000 66%, rgba(0, 0, 0, 0.72) 76%, transparent 88%);
          filter: saturate(1.04) brightness(1.08) drop-shadow(0 0 20px rgba(0, 212, 255, 0.2));
        }

        .overlay-orb::before {
          content: "";
          position: absolute;
          inset: 6%;
          border-radius: 50%;
          background:
            radial-gradient(
              circle,
              rgba(1, 7, 15, 0.56) 0%,
              rgba(1, 10, 20, 0.48) 42%,
              rgba(1, 10, 20, 0.22) 64%,
              transparent 82%
            );
          filter: blur(8px);
          pointer-events: none;
        }

        .overlay-text-area {
          position: relative;
          z-index: 10;
          width: 320px;
          max-height: 100px;
          padding: 0 18px;
          overflow: hidden;
          text-align: center;
          text-shadow:
            0 0 12px rgba(0, 0, 0, 0.95),
            0 1px 2px rgba(0, 0, 0, 0.95);
        }

        .overlay-user-text {
          max-height: 28px;
          margin-bottom: 6px;
          overflow: hidden;
          color: rgba(0, 212, 255, 0.58);
          font-size: 10px;
          font-style: italic;
          line-height: 1.4;
          text-overflow: ellipsis;
          white-space: nowrap;
          opacity: 0;
          transform: translateY(4px);
          transition: opacity 0.6s ease, transform 0.6s ease;
        }

        .overlay-user-text.visible {
          opacity: 1;
          transform: translateY(0);
        }

        .overlay-response-text {
          display: -webkit-box;
          overflow: hidden;
          color: rgba(255, 255, 255, 0.68);
          font-size: 11px;
          line-height: 1.5;
          opacity: 0;
          transform: translateY(6px);
          transition: opacity 0.8s ease, transform 0.8s ease;
          -webkit-box-orient: vertical;
          -webkit-line-clamp: 4;
        }

        .overlay-response-text.visible {
          opacity: 1;
          transform: translateY(0);
        }
      `}</style>
    </main>
  );
}
