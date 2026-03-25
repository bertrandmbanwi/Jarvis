"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  ConnectionStatus, ChatMessage, CostSummary, WSMessage,
  ProactiveSuggestion, PlanState, PlanSubtask, ConnectedDevice,
} from "@/lib/types";

function isTunnelMode(): boolean {
  if (typeof window === "undefined") return false;
  const port = window.location.port;
  const hostname = window.location.hostname;
  const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
  return (!port || port === "443" || port === "80") && !isLocal;
}

function getWsUrl(): string {
  if (typeof window === "undefined") return "ws://localhost:8741/ws";
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.hostname;
  if (isTunnelMode()) {
    return `${proto}//${host}/jarvis-ws`;
  }
  return `${proto}//${host}:8741/ws`;
}

function getApiBaseUrl(): string {
  if (typeof window === "undefined") return "http://localhost:8741";
  if (isTunnelMode()) {
    return `${window.location.origin}/jarvis-api`;
  }
  return `${window.location.protocol}//${window.location.hostname}:8741`;
}

const JARVIS_WS_URL = getWsUrl();
const RECONNECT_DELAY_MS = 3000;
const MAX_RECONNECT_ATTEMPTS = 10;

let _audioCtx: AudioContext | null = null;
let _audioEl: HTMLAudioElement | null = null;

function getAudioElement(): HTMLAudioElement {
  if (!_audioEl) {
    _audioEl = new Audio();
    _audioEl.setAttribute("playsinline", "true");
    (_audioEl as any).webkitPlaysInline = true;
    console.log("[JARVIS Audio] Hidden <audio> element created");
  }
  return _audioEl;
}

export function ensureAudioContext(): AudioContext {
  if (!_audioCtx) {
    _audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)();
    console.log("[JARVIS Audio] AudioContext created, state:", _audioCtx.state);
  }
  return _audioCtx;
}

export async function unlockAudio(): Promise<void> {
  const ctx = ensureAudioContext();
  if (ctx.state === "suspended") {
    await ctx.resume();
    console.log("[JARVIS Audio] AudioContext resumed from user gesture");
  }
  try {
    const silentBuffer = ctx.createBuffer(1, 1, 24000);
    const source = ctx.createBufferSource();
    source.buffer = silentBuffer;
    source.connect(ctx.destination);
    source.start(0);
  } catch (_) { /* ignore */ }

  try {
    const el = getAudioElement();
    // Tiny silent WAV (44 bytes header + 0 data = valid empty WAV)
    el.src = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQAAAAA=";
    await el.play().catch(() => {});
    console.log("[JARVIS Audio] <audio> element primed from user gesture");
  } catch (_) { /* ignore */ }
}

let _onAudioPlaybackStarted: ((realDuration: number) => void) | null = null;

function onNextAudioStart(cb: (realDuration: number) => void): void {
  _onAudioPlaybackStarted = cb;
}

async function playBase64Audio(base64Wav: string, mimeType: string = "audio/wav"): Promise<void> {
  const audioSizeKB = Math.round(base64Wav.length * 0.75 / 1024);

  const binaryStr = atob(base64Wav);
  const bytes = new Uint8Array(binaryStr.length);
  for (let i = 0; i < binaryStr.length; i++) {
    bytes[i] = binaryStr.charCodeAt(i);
  }

  try {
    const el = getAudioElement();
    const blob = new Blob([bytes], { type: mimeType });
    const url = URL.createObjectURL(blob);

    el.src = url;
    el.currentTime = 0;

    el.onplaying = () => {
      if (_onAudioPlaybackStarted) {
        const realDur = (el.duration && isFinite(el.duration)) ? el.duration : 0;
        console.log("[JARVIS Audio] <audio> onplaying fired, real duration=%.2fs", realDur);
        _onAudioPlaybackStarted(realDur);
        _onAudioPlaybackStarted = null;
      }
      el.onplaying = null;
    };

    await el.play();

    console.log("[JARVIS Audio] Playing via <audio> element (%d KB)", audioSizeKB);

    el.onended = () => {
      URL.revokeObjectURL(url);
      el.onended = null;
    };

    return;
  } catch (e) {
    console.warn("[JARVIS Audio] <audio> element playback failed, trying Web Audio API:", e);
  }

  // Strategy B: Fall back to Web Audio API (decodeAudioData).
  // This works well on desktop browsers and Android.
  try {
    const ctx = ensureAudioContext();
    if (ctx.state === "suspended") {
      await ctx.resume();
    }

    const audioBuffer = await ctx.decodeAudioData(bytes.buffer.slice(0));
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);
    source.start(0);

    // Web Audio API starts immediately on .start(0), so fire the sync callback now
    if (_onAudioPlaybackStarted) {
      console.log("[JARVIS Audio] Web Audio API started, real duration=%.2fs, syncing envelope", audioBuffer.duration);
      _onAudioPlaybackStarted(audioBuffer.duration);
      _onAudioPlaybackStarted = null;
    }

    console.log("[JARVIS Audio] Playing via Web Audio API (%d KB, %.1fs)", audioSizeKB, audioBuffer.duration);
  } catch (e) {
    console.warn("[JARVIS Audio] Both playback strategies failed:", e);
    // Fire the callback anyway so the animation still plays (unsynced is better than frozen).
    // Pass 0 so the caller falls back to the server-reported duration.
    if (_onAudioPlaybackStarted) {
      _onAudioPlaybackStarted(0);
      _onAudioPlaybackStarted = null;
    }
  }
}

interface UseJarvisWebSocketReturn {
  status: ConnectionStatus;
  messages: ChatMessage[];
  costSummary: CostSummary | null;
  sendMessage: (text: string) => void;
  clearMessages: () => void;
  isProcessing: boolean;
  isStreaming: boolean;
  isVoiceSpeaking: boolean;
  currentAmplitude: number;
  sendBrowserMicState: (recording: boolean) => void;
  stopAudio: () => void;
  setWantsAudio: (wants: boolean) => void;
  connectedDevices: ConnectedDevice[];
  suggestions: ProactiveSuggestion[];
  dismissSuggestion: (id: string) => void;
  activePlan: PlanState | null;
}
function detectDeviceType(): { device_type: string; device_name: string } {
  if (typeof navigator === "undefined") {
    return { device_type: "unknown", device_name: "" };
  }
  const ua = navigator.userAgent;
  if (/iPad/.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1)) {
    return { device_type: "tablet", device_name: "iPad" };
  }
  if (/iPhone/.test(ua)) {
    return { device_type: "phone", device_name: "iPhone" };
  }
  if (/Android/.test(ua) && /Mobile/.test(ua)) {
    return { device_type: "phone", device_name: "Android Phone" };
  }
  if (/Android/.test(ua)) {
    return { device_type: "tablet", device_name: "Android Tablet" };
  }
  return { device_type: "desktop", device_name: navigator.platform || "Desktop" };
}

export function useJarvisWebSocket(authToken?: string | null): UseJarvisWebSocketReturn {
  const [status, setStatus] = useState<ConnectionStatus>("disconnected");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isStreaming, setIsStreaming] = useState(false);
  const [isVoiceSpeaking, setIsVoiceSpeaking] = useState(false);
  const [currentAmplitude, setCurrentAmplitude] = useState(0);
  const [suggestions, setSuggestions] = useState<ProactiveSuggestion[]>([]);
  const [activePlan, setActivePlan] = useState<PlanState | null>(null);
  const [connectedDevices, setConnectedDevices] = useState<ConnectedDevice[]>([]);

  // Envelope playback and audio chunking state
  const envelopeRef = useRef<number[]>([]);
  const envelopeStartRef = useRef<number>(0);
  const envelopeDurationRef = useRef<number>(0);
  const envelopeRafRef = useRef<number | null>(null);

  const chunkQueueRef = useRef<Array<{
    audio: string;
    envelope: number[];
    duration: number;
    index: number;
    is_last: boolean;
  }>>([]);
  const isPlayingChunkRef = useRef(false);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttempts = useRef(0);
  const reconnectTimeout = useRef<NodeJS.Timeout | null>(null);
  const currentStreamRef = useRef<string>("");

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setStatus("connecting");

    try {
      // Add auth token for remote connections
      let wsUrl = JARVIS_WS_URL;
      if (authToken) {
        const sep = wsUrl.includes("?") ? "&" : "?";
        wsUrl = `${wsUrl}${sep}token=${encodeURIComponent(authToken)}`;
      }
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus("connected");
        reconnectAttempts.current = 0;
        console.log("[JARVIS WS] Connected");

        // Register this client with device info and audio preferences
        const deviceInfo = detectDeviceType();
        ws.send(JSON.stringify({
          client_register: {
            ...deviceInfo,
            wants_audio: true,  // default: receive TTS audio
          },
        }));
        console.log("[JARVIS WS] Sent client registration:", deviceInfo);
      };

      ws.onmessage = (event) => {
        try {
          const data: WSMessage = JSON.parse(event.data);

          if (data.error) {
            console.error("[JARVIS WS] Server error:", data.error);
            setIsProcessing(false);
            setIsStreaming(false);
            return;
          }

          // Client registration acknowledgment
          if (data.client_registered) {
            console.log("[JARVIS WS] Client registered. Connected devices:", data.connected_devices?.length);
            if (data.connected_devices) {
              setConnectedDevices(data.connected_devices);
            }
            return;
          }

          // Audio preference update acknowledgment
          if (data.audio_preference_updated) {
            console.log("[JARVIS WS] Audio preference updated: wants_audio=%s", data.wants_audio);
            return;
          }

          // Audio interruption signal from server (or another client)
          if (data.voice_stop) {
            console.log("[JARVIS WS] Audio stop signal received, interrupting playback");
            // Stop the <audio> element
            const el = getAudioElement();
            el.pause();
            el.currentTime = 0;
            // Cancel envelope animation
            if (envelopeRafRef.current) {
              cancelAnimationFrame(envelopeRafRef.current);
              envelopeRafRef.current = null;
            }
            setCurrentAmplitude(0);
            setIsVoiceSpeaking(false);
            return;
          }

          // Chunked audio streaming: queue and play chunks sequentially
          if (data.voice_audio_chunk) {
            const chunk = data.voice_audio_chunk as {
              audio: string; index: number; is_last: boolean;
              envelope: number[]; duration: number; format?: string;
            };
            const chunkMime = chunk.format || "audio/wav";

            if (chunk.index === 0) {
              // First chunk: mark as speaking, clear any previous queue
              setIsVoiceSpeaking(true);
              chunkQueueRef.current = [];
              isPlayingChunkRef.current = false;
              console.log("[JARVIS Audio] First chunk received, starting streamed playback");
            }

            if (chunk.audio) {
              chunkQueueRef.current.push(chunk);
            }

            // Process queue: play next chunk if nothing is currently playing
            const playNextChunk = () => {
              if (isPlayingChunkRef.current) return;
              const next = chunkQueueRef.current.shift();
              if (!next) {
                // Queue empty; if no more chunks coming, finish
                return;
              }

              isPlayingChunkRef.current = true;

              // Start envelope animation for this chunk
              if (next.envelope && next.envelope.length > 0) {
                envelopeRef.current = next.envelope;
                envelopeDurationRef.current = next.duration;
                envelopeStartRef.current = performance.now();

                if (envelopeRafRef.current) cancelAnimationFrame(envelopeRafRef.current);

                const tick = () => {
                  const elapsed = (performance.now() - envelopeStartRef.current) / 1000;
                  const env = envelopeRef.current;
                  const dur = envelopeDurationRef.current;

                  if (elapsed >= dur || env.length === 0) {
                    setCurrentAmplitude(0);
                    envelopeRafRef.current = null;
                    return;
                  }

                  const progress = elapsed / dur;
                  const idx = Math.min(Math.floor(progress * env.length), env.length - 1);
                  setCurrentAmplitude(env[idx]);
                  envelopeRafRef.current = requestAnimationFrame(tick);
                };
                envelopeRafRef.current = requestAnimationFrame(tick);
              }

              // Play the audio chunk
              const binaryStr = atob(next.audio);
              const bytes = new Uint8Array(binaryStr.length);
              for (let i = 0; i < binaryStr.length; i++) {
                bytes[i] = binaryStr.charCodeAt(i);
              }

              const el = getAudioElement();
              const blob = new Blob([bytes], { type: chunkMime });
              const url = URL.createObjectURL(blob);
              el.src = url;
              el.currentTime = 0;

              el.onended = () => {
                URL.revokeObjectURL(url);
                el.onended = null;
                isPlayingChunkRef.current = false;

                // Play the next queued chunk, or finish if done
                if (chunkQueueRef.current.length > 0) {
                  playNextChunk();
                } else {
                  // Check if this was flagged as the last chunk
                  if (next.is_last) {
                    setCurrentAmplitude(0);
                    setIsVoiceSpeaking(false);
                  }
                  // Otherwise, more chunks may still be arriving
                }
              };

              el.play().catch((e) => {
                console.warn("[JARVIS Audio] Chunk playback failed:", e);
                isPlayingChunkRef.current = false;
                // Try next chunk on failure
                if (chunkQueueRef.current.length > 0) {
                  playNextChunk();
                }
              });

              console.log(
                "[JARVIS Audio] Playing chunk %d (%.1fs, %d KB, %s)",
                next.index, next.duration, Math.round(next.audio.length * 0.75 / 1024), chunkMime
              );
            };

            playNextChunk();

            // If this is the last empty-audio sentinel, handle completion
            if (chunk.is_last && !chunk.audio && !isPlayingChunkRef.current) {
              setCurrentAmplitude(0);
              setIsVoiceSpeaking(false);
            }

            return;
          }

          // Voice pipeline: TTS speaking state changed
          if (data.voice_speaking !== undefined) {
            setIsVoiceSpeaking(data.voice_speaking);

            // Play TTS audio in the browser (for phone/remote access).
            // The server sends the WAV audio as base64 alongside the speaking state.
            if (data.voice_speaking && data.voice_audio) {
              const audioSizeKB = Math.round(data.voice_audio.length * 0.75 / 1024);
              console.log(
                "[JARVIS WS] Received voice_audio (%d KB). AudioContext state: %s",
                audioSizeKB,
                _audioCtx?.state ?? "not-created"
              );

              // Prepare the envelope animation (but don't start the timer yet).
              // The timer starts when audio actually begins playing, keeping them in sync.
              if (data.amplitude_envelope && data.audio_duration) {
                envelopeRef.current = data.amplitude_envelope;
                envelopeDurationRef.current = data.audio_duration;

                // Cancel any existing playback
                if (envelopeRafRef.current) cancelAnimationFrame(envelopeRafRef.current);

                const startEnvelopeTick = (realDuration: number) => {
                  // Use the real audio duration from the <audio> element when available.
                  // This is more accurate than the server estimate, which can differ
                  // due to encoding overhead, sample rate conversion, or buffering.
                  if (realDuration > 0) {
                    console.log(
                      "[JARVIS Audio] Overriding server duration (%.2fs) with real audio duration (%.2fs)",
                      envelopeDurationRef.current, realDuration
                    );
                    envelopeDurationRef.current = realDuration;
                  }

                  envelopeStartRef.current = performance.now();
                  console.log("[JARVIS Audio] Envelope animation started (synced, dur=%.2fs)", envelopeDurationRef.current);

                  const tick = () => {
                    const elapsed = (performance.now() - envelopeStartRef.current) / 1000;
                    const env = envelopeRef.current;
                    const dur = envelopeDurationRef.current;

                    if (elapsed >= dur || env.length === 0) {
                      setCurrentAmplitude(0);
                      envelopeRafRef.current = null;
                      return;
                    }

                    // Map elapsed time to envelope index
                    const progress = elapsed / dur;
                    const idx = Math.min(
                      Math.floor(progress * env.length),
                      env.length - 1
                    );
                    setCurrentAmplitude(env[idx]);
                    envelopeRafRef.current = requestAnimationFrame(tick);
                  };
                  envelopeRafRef.current = requestAnimationFrame(tick);
                };

                // Register the callback: envelope starts when audio actually plays
                onNextAudioStart(startEnvelopeTick);
              }

              // Start audio playback (async). The onplaying/start event will
              // fire onNextAudioStart, which kicks off the envelope animation.
              playBase64Audio(data.voice_audio, data.audio_format || "audio/wav");

            } else if (data.voice_speaking && data.amplitude_envelope && data.audio_duration) {
              // No audio data (animation-only client, e.g. desktop while phone has audio).
              // Start envelope immediately since there's no audio to sync with.
              envelopeRef.current = data.amplitude_envelope;
              envelopeDurationRef.current = data.audio_duration;
              envelopeStartRef.current = performance.now();

              if (envelopeRafRef.current) cancelAnimationFrame(envelopeRafRef.current);

              const tick = () => {
                const elapsed = (performance.now() - envelopeStartRef.current) / 1000;
                const env = envelopeRef.current;
                const dur = envelopeDurationRef.current;

                if (elapsed >= dur || env.length === 0) {
                  setCurrentAmplitude(0);
                  envelopeRafRef.current = null;
                  return;
                }

                const progress = elapsed / dur;
                const idx = Math.min(
                  Math.floor(progress * env.length),
                  env.length - 1
                );
                setCurrentAmplitude(env[idx]);
                envelopeRafRef.current = requestAnimationFrame(tick);
              };
              envelopeRafRef.current = requestAnimationFrame(tick);

            } else if (data.voice_speaking) {
              console.log("[JARVIS WS] voice_speaking=true but NO voice_audio or envelope");
            }

            if (!data.voice_speaking) {
              // Stop envelope playback
              if (envelopeRafRef.current) {
                cancelAnimationFrame(envelopeRafRef.current);
                envelopeRafRef.current = null;
              }
              setCurrentAmplitude(0);
            }

            return;
          }

          // Standalone amplitude envelope (sent after speech for late-joining clients)
          if (data.amplitude_envelope && !data.voice_speaking) {
            return; // Ignore; it's historical data
          }

          // ---- Proactive suggestion from background engine ----
          if (data.proactive_suggestion) {
            const ps = data.proactive_suggestion;
            const newSuggestion: ProactiveSuggestion = {
              id: `proactive-${ps.timestamp}-${Math.random().toString(36).slice(2, 7)}`,
              category: ps.category,
              message: ps.message,
              priority: ps.priority,
              spoken: ps.spoken,
              timestamp: ps.timestamp,
            };
            setSuggestions((prev) => [...prev.slice(-9), newSuggestion]); // keep max 10
            return;
          }

          // ---- Task plan progress events ----
          if (data.plan_progress) {
            const pp = data.plan_progress;
            switch (pp.event) {
              case "plan_created": {
                const subtasks: PlanSubtask[] = (pp.subtasks || []).map((s) => ({
                  id: s.id,
                  title: s.title,
                  agent_type: s.agent_type,
                  status: "pending" as const,
                }));
                setActivePlan({
                  planId: pp.plan_id,
                  goal: pp.goal || "",
                  subtasks,
                  completed: 0,
                  total: subtasks.length,
                  isActive: true,
                });
                break;
              }
              case "subtask_started":
                setActivePlan((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    subtasks: prev.subtasks.map((s) =>
                      s.id === pp.subtask_id
                        ? { ...s, status: "running" as const, agent_type: pp.agent_type || s.agent_type }
                        : s
                    ),
                  };
                });
                break;
              case "subtask_completed":
                setActivePlan((prev) => {
                  if (!prev) return prev;
                  const updated = prev.subtasks.map((s) =>
                    s.id === pp.subtask_id
                      ? { ...s, status: "completed" as const, result: pp.result }
                      : s
                  );
                  return {
                    ...prev,
                    subtasks: updated,
                    completed: updated.filter((s) => s.status === "completed").length,
                  };
                });
                break;
              case "subtask_failed":
                setActivePlan((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    subtasks: prev.subtasks.map((s) =>
                      s.id === pp.subtask_id ? { ...s, status: "failed" as const, result: pp.result } : s
                    ),
                  };
                });
                break;
              case "subtask_skipped":
                setActivePlan((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    subtasks: prev.subtasks.map((s) =>
                      s.id === pp.subtask_id ? { ...s, status: "skipped" as const } : s
                    ),
                  };
                });
                break;
              case "plan_completed":
                setActivePlan((prev) => {
                  if (!prev) return prev;
                  return {
                    ...prev,
                    completed: pp.completed || prev.completed,
                    total: pp.total || prev.total,
                    isActive: false,
                  };
                });
                // Auto-clear after 5s
                setTimeout(() => setActivePlan(null), 5000);
                break;
            }
            return;
          }

          // Voice pipeline: user spoke something (broadcast from server)
          if (data.voice_user_message) {
            const voiceUserMsg: ChatMessage = {
              id: `voice-user-${Date.now()}`,
              role: "user",
              content: data.voice_user_message,
              timestamp: Date.now(),
            };
            const voiceAssistantMsg: ChatMessage = {
              id: `voice-assistant-${Date.now()}`,
              role: "assistant",
              content: "",
              timestamp: Date.now(),
              isStreaming: true,
            };
            setMessages((prev) => [...prev, voiceUserMsg, voiceAssistantMsg]);
            setIsProcessing(false);
            setIsStreaming(true);
            currentStreamRef.current = "";
            return;
          }

          if (data.done === false && data.token) {
            // First token: switch from "processing" (thinking) to "streaming" (speaking)
            if (!currentStreamRef.current) {
              setIsProcessing(false);
              setIsStreaming(true);
            }

            currentStreamRef.current += data.token;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant" && last.isStreaming) {
                updated[updated.length - 1] = {
                  ...last,
                  content: currentStreamRef.current,
                };
              }
              return updated;
            });
          }

          if (data.done === true) {
            // Streaming complete: finalize the message
            const finalContent = data.full_response || currentStreamRef.current;
            setMessages((prev) => {
              const updated = [...prev];
              const last = updated[updated.length - 1];
              if (last && last.role === "assistant" && last.isStreaming) {
                updated[updated.length - 1] = {
                  ...last,
                  content: finalContent,
                  isStreaming: false,
                };
              }
              return updated;
            });
            currentStreamRef.current = "";
            setIsProcessing(false);
            setIsStreaming(false);

            // Update cost summary if provided
            if (data.session_cost) {
              setCostSummary({
                sessionCostUsd: data.session_cost.session_cost_usd,
                totalRequests: data.session_cost.total_requests,
                requestsByTier: data.session_cost.requests_by_tier,
                totalInputTokens: data.session_cost.total_input_tokens,
                totalOutputTokens: data.session_cost.total_output_tokens,
                cacheReadTokens: data.session_cost.cache_read_tokens,
                cacheCreationTokens: data.session_cost.cache_creation_tokens,
                activeBackend: data.session_cost.active_backend,
              });
            }
          }
        } catch (e) {
          console.error("[JARVIS WS] Parse error:", e);
        }
      };

      ws.onclose = () => {
        setStatus("disconnected");
        wsRef.current = null;
        console.log("[JARVIS WS] Disconnected");

        // Auto-reconnect
        if (reconnectAttempts.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttempts.current += 1;
          const delay = RECONNECT_DELAY_MS * Math.min(reconnectAttempts.current, 5);
          console.log(`[JARVIS WS] Reconnecting in ${delay}ms (attempt ${reconnectAttempts.current})`);
          reconnectTimeout.current = setTimeout(connect, delay);
        }
      };

      ws.onerror = (err) => {
        console.error("[JARVIS WS] Error:", err);
        setStatus("error");
      };
    } catch (e) {
      console.error("[JARVIS WS] Connection failed:", e);
      setStatus("error");
    }
  }, [authToken]);

  // Connect on mount (or when authToken changes), cleanup on unmount
  useEffect(() => {
    connect();

    return () => {
      if (reconnectTimeout.current) {
        clearTimeout(reconnectTimeout.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [connect]);

  const sendMessage = useCallback((text: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error("[JARVIS WS] Cannot send: not connected");
      return;
    }

    // Add user message
    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
      timestamp: Date.now(),
    };

    // Add placeholder assistant message for streaming
    const assistantMsg: ChatMessage = {
      id: `assistant-${Date.now()}`,
      role: "assistant",
      content: "",
      timestamp: Date.now(),
      isStreaming: true,
    };

    setMessages((prev) => [...prev, userMsg, assistantMsg]);
    setIsProcessing(true);
    setIsStreaming(false);
    currentStreamRef.current = "";

    wsRef.current.send(JSON.stringify({ message: text }));
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    const clearUrl = `${getApiBaseUrl()}/clear`;
    const headers: Record<string, string> = {};
    if (authToken) {
      headers["Authorization"] = `Bearer ${authToken}`;
    }
    fetch(clearUrl, { method: "POST", headers }).catch(() => {});
  }, [authToken]);

  const sendBrowserMicState = useCallback((recording: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ browser_mic: recording }));
  }, []);

  const stopAudio = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ stop_audio: true }));
    // Also stop local playback immediately (don't wait for server round-trip)
    const el = getAudioElement();
    el.pause();
    el.currentTime = 0;
    if (envelopeRafRef.current) {
      cancelAnimationFrame(envelopeRafRef.current);
      envelopeRafRef.current = null;
    }
    setCurrentAmplitude(0);
    setIsVoiceSpeaking(false);
  }, []);

  const setWantsAudio = useCallback((wants: boolean) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({
      audio_preference: { wants_audio: wants },
    }));
  }, []);

  const dismissSuggestion = useCallback((id: string) => {
    setSuggestions((prev) => prev.filter((s) => s.id !== id));
  }, []);

  return {
    status,
    messages,
    costSummary,
    sendMessage,
    clearMessages,
    isProcessing,
    isStreaming,
    isVoiceSpeaking,
    currentAmplitude,
    sendBrowserMicState,
    stopAudio,
    setWantsAudio,
    connectedDevices,
    suggestions,
    dismissSuggestion,
    activePlan,
  };
}
