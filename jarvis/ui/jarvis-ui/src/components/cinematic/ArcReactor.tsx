'use client';

import React, { useEffect, useRef } from 'react';
import { OrbState } from '@/lib/types';

interface ArcReactorProps {
  state: OrbState;
  transitionIn?: number;
  audioAmplitude?: number;
  className?: string;
}

interface StateConfig {
  color: [number, number, number];
  coreColor: [number, number, number];
  accentColor: [number, number, number];
  sphereRadius: number;
  displacement: number;
  noiseScale: number;
  noiseSpeed: number;
  rotationSpeed: number;
  coreIntensity: number;
  particleBrightness: number;
  trailLength: number;
  heartbeatStrength: number;
  heartbeatSpeed: number;
  ringOpacity: number;
  connectionOpacity: number;
  breathingMix: number;
}

const CYAN: [number, number, number] = [0, 190, 255];
const CYAN_BRIGHT: [number, number, number] = [140, 225, 255];
const CYAN_DEEP: [number, number, number] = [0, 140, 220];

const GOLD: [number, number, number] = [255, 180, 50];
const GOLD_BRIGHT: [number, number, number] = [255, 225, 140];
const GOLD_WARM: [number, number, number] = [255, 150, 30];
const AMBER: [number, number, number] = [255, 130, 20];

const CONFIGS: Record<OrbState, StateConfig> = {
  idle: {
    color: CYAN,
    coreColor: CYAN_BRIGHT,
    accentColor: CYAN_DEEP,
    sphereRadius: 0.28,
    displacement: 0.02,
    noiseScale: 0.3,
    noiseSpeed: 0.4,
    rotationSpeed: 0.12,
    coreIntensity: 0.65,
    particleBrightness: 0.55,
    trailLength: 0.0,
    heartbeatStrength: 0.3,
    heartbeatSpeed: 0.8,
    ringOpacity: 0.25,
    connectionOpacity: 0.08,
    breathingMix: 0.2,
  },
  listening: {
    color: [80, 200, 255],
    coreColor: [180, 235, 255],
    accentColor: CYAN_DEEP,
    sphereRadius: 0.30,
    displacement: 0.08,
    noiseScale: 0.5,
    noiseSpeed: 0.7,
    rotationSpeed: 0.25,
    coreIntensity: 0.8,
    particleBrightness: 0.65,
    trailLength: 0.1,
    heartbeatStrength: 0.45,
    heartbeatSpeed: 1.1,
    ringOpacity: 0.3,
    connectionOpacity: 0.12,
    breathingMix: 0.3,
  },
  thinking: {
    color: [180, 190, 140],
    coreColor: [220, 225, 180],
    accentColor: [120, 160, 80],
    sphereRadius: 0.26,
    displacement: 0.1,
    noiseScale: 0.5,
    noiseSpeed: 0.8,
    rotationSpeed: 0.4,
    coreIntensity: 0.85,
    particleBrightness: 0.75,
    trailLength: 0.1,
    heartbeatStrength: 0.5,
    heartbeatSpeed: 1.6,
    ringOpacity: 0.3,
    connectionOpacity: 0.12,
    breathingMix: 0.15,
  },
  speaking: {
    color: GOLD_BRIGHT,
    coreColor: [255, 245, 220],
    accentColor: GOLD,
    sphereRadius: 0.28,
    displacement: 0.04,
    noiseScale: 0.2,
    noiseSpeed: 0.15,
    rotationSpeed: 0.05,
    coreIntensity: 0.8,
    particleBrightness: 0.75,
    trailLength: 0.0,
    heartbeatStrength: 0.15,
    heartbeatSpeed: 0.3,
    ringOpacity: 0.18,
    connectionOpacity: 0.08,
    breathingMix: 0.95,
  },
  error: {
    color: [255, 80, 40],
    coreColor: [255, 160, 140],
    accentColor: [200, 50, 20],
    sphereRadius: 0.22,
    displacement: 0.05,
    noiseScale: 0.4,
    noiseSpeed: 0.3,
    rotationSpeed: 0.08,
    coreIntensity: 0.4,
    particleBrightness: 0.4,
    trailLength: 0.0,
    breathingMix: 0.1,
    heartbeatStrength: 0.15,
    heartbeatSpeed: 0.5,
    ringOpacity: 0.1,
    connectionOpacity: 0.0,
  },
};

function noise3D(x: number, y: number, z: number): number {
  const p = x * 1271 + y * 7927 + z * 3671;
  const s = Math.sin(p) * 43758.5453;
  return (s - Math.floor(s)) * 2 - 1;
}

function smoothNoise(x: number, y: number, z: number): number {
  const ix = Math.floor(x), iy = Math.floor(y), iz = Math.floor(z);
  const fx = x - ix, fy = y - iy, fz = z - iz;
  const sx = fx * fx * (3 - 2 * fx);
  const sy = fy * fy * (3 - 2 * fy);
  const sz = fz * fz * (3 - 2 * fz);
  const n000 = noise3D(ix, iy, iz), n100 = noise3D(ix + 1, iy, iz);
  const n010 = noise3D(ix, iy + 1, iz), n110 = noise3D(ix + 1, iy + 1, iz);
  const n001 = noise3D(ix, iy, iz + 1), n101 = noise3D(ix + 1, iy, iz + 1);
  const n011 = noise3D(ix, iy + 1, iz + 1), n111 = noise3D(ix + 1, iy + 1, iz + 1);
  return n000 * (1 - sx) * (1 - sy) * (1 - sz) + n100 * sx * (1 - sy) * (1 - sz)
    + n010 * (1 - sx) * sy * (1 - sz) + n110 * sx * sy * (1 - sz)
    + n001 * (1 - sx) * (1 - sy) * sz + n101 * sx * (1 - sy) * sz
    + n011 * (1 - sx) * sy * sz + n111 * sx * sy * sz;
}

function fbm(x: number, y: number, z: number): number {
  return smoothNoise(x, y, z) * 0.7 + smoothNoise(x * 2.1, y * 2.1, z * 2.1) * 0.3;
}

function heartbeat(t: number, bps: number): number {
  const phase = (t * bps) % 1.0;
  const lub = Math.exp(-Math.pow((phase - 0.08) * 18, 2));
  const dub = Math.exp(-Math.pow((phase - 0.24) * 18, 2)) * 0.7;
  return lub + dub;
}

function breathing(t: number, rate: number): number {
  const primary = Math.sin(t * rate * Math.PI * 2) * 0.5 + 0.5;
  const secondary = Math.sin(t * rate * 1.37 * Math.PI * 2) * 0.15 + 0.15;
  const micro = Math.sin(t * rate * 3.7 * Math.PI * 2) * 0.08;
  return Math.max(0, Math.min(1, primary + secondary + micro));
}

function rgba(c: [number, number, number], a: number): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a))})`;
}
function lerpN(a: number, b: number, t: number): number { return a + (b - a) * t; }
function lerpRgb(a: [number, number, number], b: [number, number, number], t: number): [number, number, number] {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ];
}

interface Particle {
  theta: number;
  phi: number;
  x: number;
  y: number;
  z: number;
  prevX: number;
  prevY: number;
  size: number;
  brightness: number;
  noiseOffset: number;
  speed: number;
  layer: number;
}

function createParticles(count: number): Particle[] {
  const out: Particle[] = [];
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < count; i++) {
    const layer = i < count * 0.3 ? 0 : i < count * 0.7 ? 1 : 2;
    out.push({
      theta: golden * i,
      phi: Math.acos(1 - (2 * (i + 0.5)) / count),
      x: 0, y: 0, z: 0,
      prevX: 0, prevY: 0,
      size: layer === 0 ? 0.6 + Math.random() * 1.0 : layer === 1 ? 0.8 + Math.random() * 1.6 : 1.0 + Math.random() * 2.2,
      brightness: 0.25 + Math.random() * 0.75,
      noiseOffset: Math.random() * 100,
      speed: 0.5 + Math.random() * 0.8,
      layer,
    });
  }
  return out;
}

const PARTICLE_COUNT = 1200;

export const ArcReactor: React.FC<ArcReactorProps> = ({ state, transitionIn = 1, audioAmplitude = 0, className = '' }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);
  const particlesRef = useRef<Particle[]>(createParticles(PARTICLE_COUNT));
  const curRef = useRef<StateConfig>({ ...CONFIGS[state] });
  const tgtRef = useRef<StateConfig>({ ...CONFIGS[state] });
  const audioAmpRef = useRef<number>(0);

  useEffect(() => {
    audioAmpRef.current = audioAmplitude;
  }, [audioAmplitude]);

  useEffect(() => { tgtRef.current = { ...CONFIGS[state] }; }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const r = canvas.getBoundingClientRect();
      canvas.width = r.width * dpr;
      canvas.height = r.height * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };
    resize();
    window.addEventListener('resize', resize);
    const t0 = performance.now();

    const draw = (now: number) => {
      frameRef.current = requestAnimationFrame(draw);
      const t = (now - t0) / 1000;
      const r = canvas.getBoundingClientRect();
      const W = r.width, H = r.height;
      const cx = W / 2, cy = H / 2;
      const maxR = Math.min(W, H) * 0.44;

      const c = curRef.current;
      const tg = tgtRef.current;
      const sp = 0.015;
      c.color = lerpRgb(c.color, tg.color, sp);
      c.coreColor = lerpRgb(c.coreColor, tg.coreColor, sp);
      c.accentColor = lerpRgb(c.accentColor, tg.accentColor, sp);
      c.sphereRadius = lerpN(c.sphereRadius, tg.sphereRadius, sp);
      c.displacement = lerpN(c.displacement, tg.displacement, sp);
      c.noiseScale = lerpN(c.noiseScale, tg.noiseScale, sp);
      c.noiseSpeed = lerpN(c.noiseSpeed, tg.noiseSpeed, sp);
      c.rotationSpeed = lerpN(c.rotationSpeed, tg.rotationSpeed, sp);
      c.coreIntensity = lerpN(c.coreIntensity, tg.coreIntensity, sp);
      c.particleBrightness = lerpN(c.particleBrightness, tg.particleBrightness, sp);
      c.trailLength = lerpN(c.trailLength, tg.trailLength, sp);
      c.heartbeatStrength = lerpN(c.heartbeatStrength, tg.heartbeatStrength, sp);
      c.heartbeatSpeed = lerpN(c.heartbeatSpeed, tg.heartbeatSpeed, sp);
      c.ringOpacity = lerpN(c.ringOpacity, tg.ringOpacity, sp);
      c.connectionOpacity = lerpN(c.connectionOpacity, tg.connectionOpacity, sp);
      c.breathingMix = lerpN(c.breathingMix, tg.breathingMix, sp);

      const hbRaw = heartbeat(t, c.heartbeatSpeed);
      const brRaw = breathing(t, c.heartbeatSpeed);
      let hb = hbRaw * (1 - c.breathingMix) + brRaw * c.breathingMix;

      const amp = audioAmpRef.current;
      if (amp > 0.01) {
        hb = hb * 0.2 + amp * 0.8;
      }

      const hbScale = 1.0 + hb * c.heartbeatStrength * 0.25;
      const hbGlow = 1.0 + hb * c.heartbeatStrength * 0.5;
      const hbDisplace = hb * c.heartbeatStrength;

      const rot = t * c.rotationSpeed;
      const noiseT = t * c.noiseSpeed;

      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      const masterAlpha = Math.min(1, transitionIn);
      ctx.globalAlpha = masterAlpha;

      const amb = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * 1.8);
      amb.addColorStop(0, rgba(c.color, 0.1 * c.coreIntensity * hbGlow));
      amb.addColorStop(0.25, rgba(c.accentColor, 0.04 * c.coreIntensity));
      amb.addColorStop(0.5, rgba(c.color, 0.015 * c.coreIntensity));
      amb.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = amb;
      ctx.fillRect(0, 0, W, H);

      if (c.ringOpacity > 0.01) {
        const structRings = [
          { radius: 0.35, tilt: 0.15, rotMul: 0.7, width: 1.0 },
          { radius: 0.28, tilt: -0.1, rotMul: -0.5, width: 0.8 },
          { radius: 0.22, tilt: 0.25, rotMul: 1.0, width: 0.6 },
        ];

        for (const sr of structRings) {
          const rr = maxR * sr.radius * hbScale;
          const ringAngle = rot * sr.rotMul;
          const tiltCos = Math.cos(sr.tilt);

          ctx.strokeStyle = rgba(c.color, c.ringOpacity * 0.5);
          ctx.lineWidth = sr.width;
          ctx.shadowColor = rgba(c.color, c.ringOpacity * 0.3);
          ctx.shadowBlur = 4;
          ctx.beginPath();
          for (let a = 0; a <= Math.PI * 2; a += 0.04) {
            const rx = cx + Math.cos(a + ringAngle) * rr;
            const ry = cy + Math.sin(a + ringAngle) * rr * tiltCos;
            if (a === 0) ctx.moveTo(rx, ry);
            else ctx.lineTo(rx, ry);
          }
          ctx.closePath();
          ctx.stroke();
          ctx.shadowBlur = 0;

          const tickCount = 24;
          for (let i = 0; i < tickCount; i++) {
            const a = ringAngle + (i / tickCount) * Math.PI * 2;
            const innerFactor = 0.95;
            const ix = cx + Math.cos(a) * rr * innerFactor;
            const iy = cy + Math.sin(a) * rr * tiltCos * innerFactor;
            const ox = cx + Math.cos(a) * rr * 1.05;
            const oy = cy + Math.sin(a) * rr * tiltCos * 1.05;

            ctx.strokeStyle = rgba(c.color, c.ringOpacity * (i % 4 === 0 ? 0.4 : 0.15));
            ctx.lineWidth = i % 4 === 0 ? 1.0 : 0.5;
            ctx.beginPath();
            ctx.moveTo(ix, iy);
            ctx.lineTo(ox, oy);
            ctx.stroke();
          }
        }
      }

      const bloomR = maxR * (0.5 + hb * c.heartbeatStrength * 0.12);
      const g1 = ctx.createRadialGradient(cx, cy, 0, cx, cy, bloomR);
      g1.addColorStop(0, rgba(c.color, 0.2 * c.coreIntensity * hbGlow));
      g1.addColorStop(0.2, rgba(c.accentColor, 0.08 * c.coreIntensity));
      g1.addColorStop(0.5, rgba(c.color, 0.02 * c.coreIntensity));
      g1.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g1;
      ctx.beginPath();
      ctx.arc(cx, cy, bloomR, 0, Math.PI * 2);
      ctx.fill();

      const coreR = maxR * (0.12 + hb * c.heartbeatStrength * 0.05);
      const g2 = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
      g2.addColorStop(0, rgba([255, 255, 255], 0.9 * c.coreIntensity * hbGlow));
      g2.addColorStop(0.15, rgba(c.coreColor, 0.75 * c.coreIntensity * hbGlow));
      g2.addColorStop(0.4, rgba(c.color, 0.25 * c.coreIntensity));
      g2.addColorStop(0.7, rgba(c.accentColor, 0.06 * c.coreIntensity));
      g2.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g2;
      ctx.beginPath();
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fill();

      const pinR = maxR * (0.025 + hb * c.heartbeatStrength * 0.012);
      const g3 = ctx.createRadialGradient(cx, cy, 0, cx, cy, pinR);
      g3.addColorStop(0, rgba([255, 255, 255], c.coreIntensity));
      g3.addColorStop(0.4, rgba(c.coreColor, 0.6 * c.coreIntensity));
      g3.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = g3;
      ctx.beginPath();
      ctx.arc(cx, cy, pinR, 0, Math.PI * 2);
      ctx.fill();

      const particles = particlesRef.current;
      const baseR = maxR * c.sphereRadius * hbScale;

      const layerRadiusMul = [0.65, 1.0, 1.35];
      const layerBrightMul = [0.6, 1.0, 0.75];

      const projected: { x: number; y: number; z: number; alpha: number; layer: number }[] = [];

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        p.prevX = p.x;
        p.prevY = p.y;

        const theta = p.theta + rot * p.speed;
        const sinPhi = Math.sin(p.phi), cosPhi = Math.cos(p.phi);
        const sinTheta = Math.sin(theta), cosTheta = Math.cos(theta);
        const dx = sinPhi * cosTheta, dy = cosPhi, dz = sinPhi * sinTheta;

        const noiseSample = fbm(
          dx * 2 + p.noiseOffset + noiseT * 0.3,
          dy * 2 + noiseT * 0.2,
          dz * 2 + noiseT * 0.4
        );

        const displace = (c.displacement + hbDisplace * 0.12) * (0.5 + noiseSample * 0.5) * maxR;
        const pDisplace = displace * (0.5 + p.brightness * 0.7);
        const layerR = baseR * layerRadiusMul[p.layer];
        const pr = layerR + pDisplace + noiseSample * c.noiseScale * maxR * 0.06;

        const persp = 1.0 / (1.0 - dz * 0.25);
        const projX = cx + dx * pr * persp;
        const projY = cy + dy * pr * persp;
        p.x = projX;
        p.y = projY;
        p.z = dz;

        const depthFactor = 0.35 + (dz + 1) * 0.325;
        const layerBright = layerBrightMul[p.layer];
        const alpha = p.brightness * c.particleBrightness * depthFactor * hbGlow * layerBright;
        const sz = p.size * persp * depthFactor;

        projected.push({ x: projX, y: projY, z: dz, alpha, layer: p.layer });

        if (c.trailLength > 0.01 && (p.prevX !== 0 || p.prevY !== 0)) {
          const tdx = p.x - p.prevX, tdy = p.y - p.prevY;
          const td = Math.sqrt(tdx * tdx + tdy * tdy);
          if (td > 0.8 && td < maxR * 0.25) {
            const tg = ctx.createLinearGradient(p.prevX, p.prevY, p.x, p.y);
            tg.addColorStop(0, rgba(c.color, 0));
            tg.addColorStop(1, rgba(c.color, alpha * c.trailLength * 0.35));
            ctx.strokeStyle = tg;
            ctx.lineWidth = sz * 0.4;
            ctx.beginPath();
            ctx.moveTo(p.prevX, p.prevY);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
          }
        }

        const glowR = sz * (2.5 + c.displacement * 1.5);
        const pg = ctx.createRadialGradient(projX, projY, 0, projX, projY, glowR);
        pg.addColorStop(0, rgba(c.color, alpha * 0.45));
        pg.addColorStop(0.25, rgba(c.accentColor, alpha * 0.12));
        pg.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = pg;
        ctx.beginPath();
        ctx.arc(projX, projY, glowR, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = rgba([255, 255, 255], alpha * 0.8);
        ctx.beginPath();
        ctx.arc(projX, projY, sz * 0.45, 0, Math.PI * 2);
        ctx.fill();
      }

      if (c.connectionOpacity > 0.005) {
        const connThreshold = maxR * 0.08;
        const connThreshSq = connThreshold * connThreshold;

        for (let i = 0; i < projected.length; i += 6) {
          const a = projected[i];
          for (let j = i + 6; j < projected.length; j += 6) {
            const b = projected[j];
            const ddx = a.x - b.x, ddy = a.y - b.y;
            const dSq = ddx * ddx + ddy * ddy;
            if (dSq < connThreshSq && dSq > 4) {
              const dist = Math.sqrt(dSq);
              const strength = (1 - dist / connThreshold);
              const lineAlpha = strength * c.connectionOpacity * Math.min(a.alpha, b.alpha) * 0.6;
              if (lineAlpha > 0.005) {
                ctx.strokeStyle = rgba(c.color, lineAlpha);
                ctx.lineWidth = 0.4 + strength * 0.6;
                ctx.beginPath();
                ctx.moveTo(a.x, a.y);
                ctx.lineTo(b.x, b.y);
                ctx.stroke();
              }
            }
          }
        }
      }

      const nodeCount = 12;
      const nodeAngleStep = Math.PI * 2 / nodeCount;
      for (let i = 0; i < nodeCount; i++) {
        const angle = rot * 0.3 + i * nodeAngleStep;
        const nodeR = baseR * 0.9 * hbScale;
        const nx = cx + Math.cos(angle) * nodeR;
        const ny = cy + Math.sin(angle) * nodeR * 0.85;

        const pulse = 0.4 + Math.sin(t * 3 + i * 1.7) * 0.3 + hb * 0.3;
        const nodeGlow = ctx.createRadialGradient(nx, ny, 0, nx, ny, maxR * 0.025);
        nodeGlow.addColorStop(0, rgba(c.coreColor, pulse * c.coreIntensity * 0.6));
        nodeGlow.addColorStop(0.5, rgba(c.color, pulse * c.coreIntensity * 0.15));
        nodeGlow.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = nodeGlow;
        ctx.beginPath();
        ctx.arc(nx, ny, maxR * 0.025, 0, Math.PI * 2);
        ctx.fill();

        ctx.fillStyle = rgba([255, 255, 255], pulse * 0.5);
        ctx.beginPath();
        ctx.arc(nx, ny, 1.2, 0, Math.PI * 2);
        ctx.fill();
      }

      const pulseCount = 3;
      for (let i = 0; i < pulseCount; i++) {
        const pulsePhase = ((t * c.heartbeatSpeed * 0.8 + i * 0.33) % 1.0);
        const pulseR = maxR * (c.sphereRadius * 0.3 + pulsePhase * c.sphereRadius * 2.5);
        const pulseAlpha = (1 - pulsePhase) * 0.2 * c.coreIntensity * (0.5 + hb * 0.5);

        if (pulseAlpha > 0.005) {
          ctx.strokeStyle = rgba(c.color, pulseAlpha);
          ctx.lineWidth = 1.5 * (1 - pulsePhase * 0.6);
          ctx.shadowColor = rgba(c.color, pulseAlpha * 0.5);
          ctx.shadowBlur = 8;
          ctx.beginPath();
          ctx.arc(cx, cy, pulseR, 0, Math.PI * 2);
          ctx.stroke();
          ctx.shadowBlur = 0;
        }
      }

      const dynRings = [
        { baseRadius: 0.42, speedMul: 1.0, dashCount: 8, arcLen: 0.15, width: 1.2 },
        { baseRadius: 0.38, speedMul: -1.4, dashCount: 6, arcLen: 0.2, width: 0.9 },
        { baseRadius: 0.50, speedMul: 0.6, dashCount: 10, arcLen: 0.1, width: 0.7 },
      ];

      for (const dr of dynRings) {
        const rr = maxR * dr.baseRadius * hbScale;
        const ringRot = t * c.rotationSpeed * dr.speedMul * 2;
        const ringColor = lerpRgb(c.color, c.coreColor, c.coreIntensity * 0.3);
        const ringAlpha = c.ringOpacity * 0.6 * (0.7 + hb * 0.3);

        for (let d = 0; d < dr.dashCount; d++) {
          const startAngle = ringRot + (d / dr.dashCount) * Math.PI * 2;
          const endAngle = startAngle + dr.arcLen;

          ctx.strokeStyle = rgba(ringColor, ringAlpha);
          ctx.lineWidth = dr.width;
          ctx.shadowColor = rgba(c.color, ringAlpha * 0.3);
          ctx.shadowBlur = 3;
          ctx.beginPath();
          ctx.arc(cx, cy, rr, startAngle, endAngle);
          ctx.stroke();
        }
        ctx.shadowBlur = 0;
      }

      const haloR = maxR * c.sphereRadius * 1.5 * hbScale;
      ctx.strokeStyle = rgba(c.color, (0.08 + hb * 0.08) * c.coreIntensity);
      ctx.lineWidth = 0.8;
      ctx.shadowColor = rgba(c.color, 0.2 * c.coreIntensity);
      ctx.shadowBlur = 12;
      ctx.beginPath();
      ctx.arc(cx, cy, haloR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.shadowBlur = 0;

      const innerHaloR = maxR * c.sphereRadius * 0.5 * hbScale;
      ctx.strokeStyle = rgba(c.coreColor, (0.1 + hb * 0.15) * c.coreIntensity);
      ctx.lineWidth = 1.2 + hb * c.heartbeatStrength;
      ctx.shadowColor = rgba(c.color, 0.3 * c.coreIntensity * hbGlow);
      ctx.shadowBlur = 6 + hb * 8;
      ctx.beginPath();
      ctx.arc(cx, cy, innerHaloR, 0, Math.PI * 2);
      ctx.stroke();
      ctx.shadowBlur = 0;

      ctx.globalAlpha = 1;
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [transitionIn]);

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full block ${className}`}
      style={{ background: 'transparent' }}
    />
  );
};

export default ArcReactor;
