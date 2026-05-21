"use client";

import React, { useEffect, useRef } from "react";
import * as THREE from "three";
import { OrbState } from "@/lib/types";
import { createJarvisOrbRenderer } from "@/lib/jarvisOrbRenderer";

interface ArcReactorGLProps {
  state: OrbState;
  transitionIn?: number;
  audioAmplitude?: number;
  compactPixelRatioCap?: number;
  pixelRatioCap?: number;
  particleAlphaScale?: number;
  particleSizeScale?: number;
  glowIntensityScale?: number;
  dustAlphaScale?: number;
  ringAlphaScale?: number;
  visualFilter?: string;
  className?: string;
}

interface OrbRendererController {
  setState: (state: OrbState) => void;
  setAudioAmplitude: (amplitude: number) => void;
  setTransitionIn: (transition: number) => void;
  resize: () => void;
  dispose: () => void;
}

export const ArcReactorGL: React.FC<ArcReactorGLProps> = ({
  state,
  transitionIn = 1,
  audioAmplitude = 0,
  compactPixelRatioCap,
  pixelRatioCap,
  particleAlphaScale,
  particleSizeScale,
  glowIntensityScale,
  dustAlphaScale,
  ringAlphaScale,
  visualFilter = "saturate(1.04) drop-shadow(0 0 28px rgba(0, 212, 255, 0.13))",
  className = "",
}) => {
  const mountRef = useRef<HTMLDivElement>(null);
  const rendererRef = useRef<OrbRendererController | null>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    rendererRef.current = createJarvisOrbRenderer(THREE, mount, {
      state,
      transitionIn,
      audioAmplitude,
      compactPixelRatioCap,
      pixelRatioCap,
      particleAlphaScale,
      particleSizeScale,
      glowIntensityScale,
      dustAlphaScale,
      ringAlphaScale,
    }) as OrbRendererController;

    return () => {
      rendererRef.current?.dispose();
      rendererRef.current = null;
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    rendererRef.current?.setState(state);
  }, [state]);

  useEffect(() => {
    rendererRef.current?.setAudioAmplitude(audioAmplitude);
  }, [audioAmplitude]);

  useEffect(() => {
    rendererRef.current?.setTransitionIn(transitionIn);
  }, [transitionIn]);

  return (
    <div
      ref={mountRef}
      className={`w-full h-full ${className}`}
      style={{
        background: "transparent",
        filter: visualFilter,
      }}
    />
  );
};

export default ArcReactorGL;
