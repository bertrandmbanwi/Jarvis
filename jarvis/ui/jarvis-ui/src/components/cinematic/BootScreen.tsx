'use client';

import React, { useEffect, useRef } from 'react';

interface BootScreenProps {
  progress: number;
  className?: string;
}

const CYAN: [number, number, number] = [0, 200, 255];
const CYAN_BRIGHT: [number, number, number] = [140, 230, 255];
const WHITE: [number, number, number] = [255, 255, 255];

function rgba(c: [number, number, number], a: number): string {
  return `rgba(${c[0]},${c[1]},${c[2]},${Math.max(0, Math.min(1, a))})`;
}

export const BootScreen: React.FC<BootScreenProps> = ({ progress, className = '' }) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const frameRef = useRef<number>(0);

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
      const maxR = Math.min(W, H) * 0.38;

      const dpr = window.devicePixelRatio || 1;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);

      const masterAlpha = progress > 1.0 ? Math.max(0, 2.0 - progress) : Math.min(1, progress * 1.5);
      if (masterAlpha <= 0) return;
      ctx.globalAlpha = masterAlpha;

      const ringReveal = Math.min(1, progress * 1.2);
      const rot = t * 0.08;

      // Ambient glow background
      const amb = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * 2);
      amb.addColorStop(0, rgba(CYAN, 0.06));
      amb.addColorStop(0.3, rgba(CYAN, 0.02));
      amb.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = amb;
      ctx.fillRect(0, 0, W, H);

      // Concentric rings with tick marks
      const rings = [
        { radius: 0.92, width: 1.2, opacity: 0.3, ticks: 72, tickLen: 0.02, rotDir: 1, delay: 0.0 },
        { radius: 0.78, width: 1.5, opacity: 0.45, ticks: 60, tickLen: 0.025, rotDir: -1, delay: 0.1 },
        { radius: 0.62, width: 1.0, opacity: 0.35, ticks: 48, tickLen: 0.02, rotDir: 1, delay: 0.2 },
        { radius: 0.48, width: 2.0, opacity: 0.5, ticks: 36, tickLen: 0.03, rotDir: -1, delay: 0.3 },
        { radius: 0.33, width: 1.0, opacity: 0.3, ticks: 24, tickLen: 0.025, rotDir: 1, delay: 0.4 },
        { radius: 0.20, width: 1.5, opacity: 0.4, ticks: 16, tickLen: 0.02, rotDir: -1, delay: 0.5 },
      ];

      for (const ring of rings) {
        const reveal = Math.max(0, Math.min(1, (ringReveal - ring.delay) * 3));
        if (reveal <= 0) continue;

        const rr = maxR * ring.radius;
        const ringRot = rot * ring.rotDir * (1 + ring.radius * 0.5);

        const arcLen = reveal * Math.PI * 2;
        ctx.strokeStyle = rgba(CYAN, ring.opacity * reveal);
        ctx.lineWidth = ring.width;
        ctx.shadowColor = rgba(CYAN, ring.opacity * 0.4 * reveal);
        ctx.shadowBlur = 6;
        ctx.beginPath();
        ctx.arc(cx, cy, rr, ringRot, ringRot + arcLen);
        ctx.stroke();
        ctx.shadowBlur = 0;

        const tickCount = Math.floor(ring.ticks * reveal);
        for (let i = 0; i < tickCount; i++) {
          const angle = ringRot + (i / ring.ticks) * Math.PI * 2;
          const innerR = rr - maxR * ring.tickLen;
          const outerR = rr;

          // Every 4th tick is longer
          const isLong = i % 4 === 0;
          const actualInnerR = isLong ? rr - maxR * ring.tickLen * 1.8 : innerR;
          const tickAlpha = isLong ? ring.opacity * 0.8 : ring.opacity * 0.4; // Every 4th tick is longer

          ctx.strokeStyle = rgba(CYAN, tickAlpha * reveal);
          ctx.lineWidth = isLong ? 1.2 : 0.7;
          ctx.beginPath();
          ctx.moveTo(cx + Math.cos(angle) * actualInnerR, cy + Math.sin(angle) * actualInnerR);
          ctx.lineTo(cx + Math.cos(angle) * outerR, cy + Math.sin(angle) * outerR);
          ctx.stroke();
        }

        if (ring.radius > 0.6 && ring.radius < 0.95) {
          const segCount = 4;
          for (let s = 0; s < segCount; s++) {
            const segAngle = ringRot + (s / segCount) * Math.PI * 2 + Math.PI / segCount;
            const segLen = 0.12 + Math.sin(t * 0.5 + s) * 0.03;
            const segR = rr + maxR * 0.015;

            ctx.strokeStyle = rgba(CYAN_BRIGHT, 0.25 * reveal);
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            ctx.arc(cx, cy, segR, segAngle - segLen / 2, segAngle + segLen / 2);
            ctx.stroke();
          }
        }
      }

      const dataReveal = Math.max(0, Math.min(1, (progress - 0.3) * 2.5));
      if (dataReveal > 0) {
        ctx.globalAlpha = masterAlpha * dataReveal;

        const dotCount = 8;
        const dotR = maxR * 0.96;
        for (let i = 0; i < dotCount; i++) {
          const angle = rot * 0.3 + (i / dotCount) * Math.PI * 2;
          const dx = cx + Math.cos(angle) * dotR;
          const dy = cy + Math.sin(angle) * dotR;
          const sz = 2 + Math.sin(t * 2 + i * 1.3) * 0.8;

          ctx.fillStyle = rgba(CYAN, 0.5 + Math.sin(t * 1.5 + i) * 0.2);
          ctx.fillRect(dx - sz / 2, dy - sz / 2, sz, sz);
        }

        const scanAngle = t * 0.6;
        const scanGrad = ctx.createConicGradient(scanAngle, cx, cy);
        scanGrad.addColorStop(0, rgba(CYAN, 0.15));
        scanGrad.addColorStop(0.05, rgba(CYAN, 0.0));
        scanGrad.addColorStop(0.95, rgba(CYAN, 0.0));
        scanGrad.addColorStop(1, rgba(CYAN, 0.15));
        ctx.fillStyle = scanGrad;
        ctx.beginPath();
        ctx.arc(cx, cy, maxR * 0.75, 0, Math.PI * 2);
        ctx.fill();

        ctx.globalAlpha = masterAlpha;
      }

      const coreReveal = Math.max(0, Math.min(1, (progress - 0.1) * 2));
      const coreR = maxR * 0.15;
      const cg = ctx.createRadialGradient(cx, cy, 0, cx, cy, coreR);
      cg.addColorStop(0, rgba(WHITE, 0.7 * coreReveal));
      cg.addColorStop(0.3, rgba(CYAN_BRIGHT, 0.4 * coreReveal));
      cg.addColorStop(0.7, rgba(CYAN, 0.1 * coreReveal));
      cg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = cg;
      ctx.beginPath();
      ctx.arc(cx, cy, coreR, 0, Math.PI * 2);
      ctx.fill();

      const pulseR = maxR * 0.15 * (1 + Math.sin(t * 2) * 0.05);
      ctx.strokeStyle = rgba(CYAN, 0.4 * coreReveal);
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(cx, cy, pulseR, 0, Math.PI * 2);
      ctx.stroke();

      const textReveal = Math.max(0, Math.min(1, (progress - 0.4) * 2));
      if (textReveal > 0) {
        const fontSize = Math.max(14, maxR * 0.13);
        ctx.font = `300 ${fontSize}px "SF Pro Display", "Inter", "Segoe UI", system-ui, sans-serif`;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.letterSpacing = `${fontSize * 0.5}px`;

        ctx.shadowColor = rgba(CYAN, 0.8 * textReveal);
        ctx.shadowBlur = 20;
        ctx.fillStyle = rgba(CYAN_BRIGHT, 0.9 * textReveal);
        ctx.fillText('J . A . R . V . I . S', cx + fontSize * 0.15, cy);
        ctx.shadowBlur = 0;

        const subReveal = Math.max(0, Math.min(1, (progress - 0.6) * 2.5));
        if (subReveal > 0) {
          const subSize = Math.max(8, maxR * 0.04);
          ctx.font = `300 ${subSize}px "SF Pro Display", "Inter", "Segoe UI", system-ui, sans-serif`;
          ctx.fillStyle = rgba(CYAN, 0.4 * subReveal);
          ctx.fillText('JUST A RATHER VERY INTELLIGENT SYSTEM', cx, cy + fontSize * 1.1);

          const verReveal = Math.max(0, Math.min(1, (progress - 0.7) * 3));
          if (verReveal > 0) {
            ctx.font = `300 ${subSize * 0.8}px "SF Pro Display", "Inter", "Segoe UI", system-ui, sans-serif`;
            ctx.fillStyle = rgba(CYAN, 0.25 * verReveal);
            ctx.fillText('v0.2.0  //  SYSTEMS ONLINE', cx, cy + fontSize * 1.1 + subSize * 2);
          }
        }
      }

      const statusReveal = Math.max(0, Math.min(1, (progress - 0.6) * 2));
      if (statusReveal > 0) {
        ctx.globalAlpha = masterAlpha * statusReveal;
        const labels = ['NEURAL NET', 'VOICE SYS', 'MEMORY', 'COMMS'];
        const statY = cy + maxR * 0.65;
        const spacing = maxR * 0.35;
        const startX = cx - spacing * 1.5;

        for (let i = 0; i < labels.length; i++) {
          const lx = startX + spacing * i;
          const dotOn = progress > 0.7 + i * 0.08;

          ctx.fillStyle = dotOn ? rgba(CYAN_BRIGHT, 0.8) : rgba(CYAN, 0.15);
          ctx.beginPath();
          ctx.arc(lx, statY, 2.5, 0, Math.PI * 2);
          ctx.fill();

          if (dotOn) {
            ctx.shadowColor = rgba(CYAN, 0.6);
            ctx.shadowBlur = 8;
            ctx.fillStyle = rgba(CYAN_BRIGHT, 0.8);
            ctx.beginPath();
            ctx.arc(lx, statY, 2.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.shadowBlur = 0;
          }

          const lblSize = Math.max(7, maxR * 0.028);
          ctx.font = `400 ${lblSize}px "SF Mono", "Fira Code", monospace`;
          ctx.textAlign = 'center';
          ctx.fillStyle = rgba(CYAN, dotOn ? 0.5 : 0.2);
          ctx.fillText(labels[i], lx, statY + lblSize * 2);
        }

        ctx.globalAlpha = masterAlpha;
      }

      ctx.globalAlpha = 1;
    };

    frameRef.current = requestAnimationFrame(draw);
    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener('resize', resize);
    };
  }, [progress]);

  return (
    <canvas
      ref={canvasRef}
      className={`w-full h-full block ${className}`}
      style={{ background: 'transparent' }}
    />
  );
};

export default BootScreen;
