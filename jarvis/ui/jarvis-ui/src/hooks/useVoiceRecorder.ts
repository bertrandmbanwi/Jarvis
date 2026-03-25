"use client";

import React, { useState, useRef, useCallback } from "react";

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
const JARVIS_API_URL = getApiBaseUrl();

const SILENCE_RMS_THRESHOLD = 0.015;
const SILENCE_TIMEOUT_MS = 2000;
const MAX_RECORD_NO_SPEECH_MS = 10000;
const MAX_RECORD_DURATION_MS = 60000;

interface UseVoiceRecorderOptions {
  onRecordingStateChange?: (recording: boolean) => void;
  authToken?: string | null;
}

interface UseVoiceRecorderReturn {
  isRecording: boolean;
  isTranscribing: boolean;
  startRecording: () => Promise<void>;
  stopRecording: () => Promise<string | null>;
  isSupported: boolean;
  error: string | null;
  onAutoStopRef: React.MutableRefObject<((text: string | null) => void) | null>;
}
export function useVoiceRecorder(options?: UseVoiceRecorderOptions): UseVoiceRecorderReturn {
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const silenceRafRef = useRef<number | null>(null);
  const autoStopTimerRef = useRef<NodeJS.Timeout | null>(null);
  const speechDetectedRef = useRef(false);
  const silenceStartRef = useRef<number | null>(null);
  const recordStartRef = useRef<number>(0);
  const stopRecordingRef = useRef<(() => Promise<string | null>) | null>(null);
  const onAutoStopRef = useRef<((text: string | null) => void) | null>(null);

  const isSupported =
    typeof window !== "undefined" &&
    !!navigator.mediaDevices &&
    !!navigator.mediaDevices.getUserMedia;

  const cleanupSilenceDetection = useCallback(() => {
    if (silenceRafRef.current) {
      cancelAnimationFrame(silenceRafRef.current);
      silenceRafRef.current = null;
    }
    if (autoStopTimerRef.current) {
      clearTimeout(autoStopTimerRef.current);
      autoStopTimerRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    analyserRef.current = null;
  }, []);

  const stopRecording = useCallback(async (): Promise<string | null> => {
    cleanupSilenceDetection();

    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state === "inactive") {
      return null;
    }

    // Stop recording and wait for final data
    return new Promise<string | null>((resolve) => {
      recorder.onstop = async () => {
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setIsRecording(false);

        const blob = new Blob(chunksRef.current, { type: recorder.mimeType });
        chunksRef.current = [];

        if (blob.size < 1000) {
          resolve(null);
          return;
        }

        setIsTranscribing(true);
        try {
          const formData = new FormData();
          const ext = recorder.mimeType.includes("mp4") ? "mp4" : "webm";
          formData.append("audio", blob, `recording.${ext}`);

          const headers: Record<string, string> = {};
          if (options?.authToken) {
            headers["Authorization"] = `Bearer ${options.authToken}`;
          }

          const response = await fetch(`${JARVIS_API_URL}/voice/transcribe`, {
            method: "POST",
            headers,
            body: formData,
          });

          if (!response.ok) {
            const errData = await response.json().catch(() => ({}));
            throw new Error(errData.error || `Server error: ${response.status}`);
          }

          const data = await response.json();
          const text = data.text?.trim() || null;

          if (text) {
            setError(null);
          }

          resolve(text);
        } catch (err) {
          const msg = err instanceof Error ? err.message : "Transcription failed.";
          setError(msg);
          console.error("[VoiceRecorder] Transcription error:", err);
          resolve(null);
        } finally {
          setIsTranscribing(false);
        }
      };

      recorder.stop();
    });
  }, [cleanupSilenceDetection]);

  stopRecordingRef.current = stopRecording;

  const startRecording = useCallback(async () => {
    if (!isSupported) {
      setError("Microphone not supported in this browser.");
      return;
    }

    setError(null);
    chunksRef.current = [];
    speechDetectedRef.current = false;
    silenceStartRef.current = null;
    recordStartRef.current = Date.now();

    try {
      // Request microphone with audio enhancement
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      streamRef.current = stream;

      const audioContext = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 2048;
      analyser.smoothingTimeConstant = 0.3;
      source.connect(analyser);
      analyserRef.current = analyser;

      const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
        ? "audio/webm;codecs=opus"
        : MediaRecorder.isTypeSupported("audio/mp4")
          ? "audio/mp4"
          : "audio/webm";

      const recorder = new MediaRecorder(stream, { mimeType });
      mediaRecorderRef.current = recorder;

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      recorder.start(100);
      setIsRecording(true);

      options?.onRecordingStateChange?.(true);

      const dataArray = new Float32Array(analyser.fftSize);

      const detectSilence = () => {
        if (!analyserRef.current || !mediaRecorderRef.current || mediaRecorderRef.current.state === "inactive") {
          return;
        }

        analyserRef.current.getFloatTimeDomainData(dataArray);

        let sumSquares = 0;
        for (let i = 0; i < dataArray.length; i++) {
          sumSquares += dataArray[i] * dataArray[i];
        }
        const rms = Math.sqrt(sumSquares / dataArray.length);

        const now = Date.now();
        const elapsed = now - recordStartRef.current;

        if (rms > SILENCE_RMS_THRESHOLD) {
          speechDetectedRef.current = true;
          silenceStartRef.current = null;
        } else if (speechDetectedRef.current) {
          if (silenceStartRef.current === null) {
            silenceStartRef.current = now;
          }

          const silenceDuration = now - silenceStartRef.current;
          if (silenceDuration >= SILENCE_TIMEOUT_MS) {
            console.log("[VoiceRecorder] Auto-stop: silence detected after speech");
            triggerAutoStop();
            return;
          }
        }

        if (!speechDetectedRef.current && elapsed >= MAX_RECORD_NO_SPEECH_MS) {
          console.log("[VoiceRecorder] Auto-stop: no speech detected within timeout");
          cleanupSilenceDetection();
          mediaRecorderRef.current?.stop();
          streamRef.current?.getTracks().forEach((track) => track.stop());
          streamRef.current = null;
          setIsRecording(false);
          setError("No speech detected. Tap the mic and try again.");
          return;
        }

        if (elapsed >= MAX_RECORD_DURATION_MS) {
          console.log("[VoiceRecorder] Auto-stop: max duration reached");
          triggerAutoStop();
          return;
        }

        silenceRafRef.current = requestAnimationFrame(detectSilence);
      };

      const triggerAutoStop = async () => {
        if (stopRecordingRef.current) {
          const text = await stopRecordingRef.current();
          // Notify via the onAutoStop callback (set by handleMicToggle callers)
          if (onAutoStopRef.current) {
            onAutoStopRef.current(text);
          }
        }
      };

      silenceRafRef.current = requestAnimationFrame(detectSilence);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Microphone access denied.";
      setError(msg);
      console.error("[VoiceRecorder] Failed to start:", err);
    }
  }, [isSupported, options, cleanupSilenceDetection]);

  return {
    isRecording,
    isTranscribing,
    startRecording,
    stopRecording,
    isSupported,
    error,
    onAutoStopRef,
  };
}
