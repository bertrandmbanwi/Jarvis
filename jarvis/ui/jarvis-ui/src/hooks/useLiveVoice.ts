"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getLiveWsUrl } from "@/lib/apiBase";

/**
 * Cloud voice mode: full-duplex conversation with OpenAI GPT-Live, relayed
 * through the JARVIS server (/ws/live) so the API key never reaches the browser.
 * The browser captures 24 kHz PCM16 audio and plays GPT-Live's replies; when
 * the user starts talking, playback stops immediately (barge-in).
 */

export type LiveStatus = "idle" | "connecting" | "live" | "working" | "error";

const SAMPLE_RATE = 24000;

// AudioWorklet that converts microphone frames to PCM16 and posts ~100 ms batches.
const CAPTURE_WORKLET = `
class PcmCapture extends AudioWorkletProcessor {
  constructor() { super(); this.buf = []; this.len = 0; }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) {
      const pcm = new Int16Array(ch.length);
      for (let i = 0; i < ch.length; i++) {
        const s = Math.max(-1, Math.min(1, ch[i]));
        pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
      }
      this.buf.push(pcm); this.len += pcm.length;
      if (this.len >= 2400) {
        const out = new Int16Array(this.len); let o = 0;
        for (const b of this.buf) { out.set(b, o); o += b.length; }
        this.port.postMessage(out.buffer, [out.buffer]);
        this.buf = []; this.len = 0;
      }
    }
    return true;
  }
}
registerProcessor("pcm-capture", PcmCapture);
`;

function toBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, Array.from(bytes.subarray(i, i + 0x8000)));
  }
  return btoa(binary);
}

function fromBase64Pcm16(b64: string): Float32Array<ArrayBuffer> {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
  const pcm = new Int16Array(bytes.buffer, 0, Math.floor(bytes.length / 2));
  const out = new Float32Array(new ArrayBuffer(pcm.length * 4));
  for (let i = 0; i < pcm.length; i++) out[i] = pcm[i] / 0x8000;
  return out;
}

export function useLiveVoice(authToken?: string | null) {
  const [status, setStatus] = useState<LiveStatus>("idle");
  const [userText, setUserText] = useState("");
  const [assistantText, setAssistantText] = useState("");
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const sourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const playheadRef = useRef(0);

  const stopPlayback = useCallback(() => {
    for (const source of sourcesRef.current) {
      try {
        source.stop();
      } catch {
        // already stopped
      }
    }
    sourcesRef.current = [];
    playheadRef.current = 0;
  }, []);

  const playChunk = useCallback((b64: string) => {
    const ctx = ctxRef.current;
    if (!ctx || !b64) return;
    const samples = fromBase64Pcm16(b64);
    if (!samples.length) return;
    const buffer = ctx.createBuffer(1, samples.length, SAMPLE_RATE);
    buffer.copyToChannel(samples, 0);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startAt = Math.max(ctx.currentTime, playheadRef.current);
    source.start(startAt);
    playheadRef.current = startAt + buffer.duration;
    sourcesRef.current.push(source);
    source.onended = () => {
      sourcesRef.current = sourcesRef.current.filter((s) => s !== source);
    };
  }, []);

  const stop = useCallback(() => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ stop: true }));
    ws?.close();
    wsRef.current = null;
    stopPlayback();
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    ctxRef.current?.close().catch(() => undefined);
    ctxRef.current = null;
    setStatus("idle");
  }, [stopPlayback]);

  const start = useCallback(async () => {
    if (wsRef.current) return;
    setError(null);
    setUserText("");
    setAssistantText("");
    setStatus("connecting");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
      streamRef.current = stream;
      const ctx = new AudioContext({ sampleRate: SAMPLE_RATE });
      ctxRef.current = ctx;
      const workletUrl = URL.createObjectURL(new Blob([CAPTURE_WORKLET], { type: "application/javascript" }));
      await ctx.audioWorklet.addModule(workletUrl);
      URL.revokeObjectURL(workletUrl);
      const capture = new AudioWorkletNode(ctx, "pcm-capture");
      ctx.createMediaStreamSource(stream).connect(capture);

      let url = getLiveWsUrl();
      if (authToken && url.startsWith("ws://")) {
        url = `${url}${url.includes("?") ? "&" : "?"}token=${encodeURIComponent(authToken)}`;
      }
      const ws = new WebSocket(url);
      wsRef.current = ws;

      capture.port.onmessage = (event: MessageEvent<ArrayBuffer>) => {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ audio: toBase64(event.data) }));
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
          case "ready":
            setStatus("live");
            break;
          case "audio":
            playChunk(msg.audio);
            break;
          case "user_transcript":
            stopPlayback(); // the user is talking over the reply
            setUserText((t) => t + msg.delta);
            break;
          case "assistant_transcript":
            setAssistantText((t) => t + msg.delta);
            break;
          case "working":
            setStatus("working");
            setUserText("");
            setAssistantText("");
            break;
          case "result":
            setStatus("live");
            break;
          case "error":
            setError(msg.message || "Live voice error");
            break;
          case "closed":
            stop();
            break;
        }
      };
      ws.onerror = () => setError("Live voice connection failed");
      ws.onclose = () => {
        if (wsRef.current === ws) stop();
      };
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start live voice");
      setStatus("error");
      stop();
    }
  }, [authToken, playChunk, stop, stopPlayback]);

  useEffect(() => stop, [stop]);

  return { status, userText, assistantText, error, start, stop };
}
