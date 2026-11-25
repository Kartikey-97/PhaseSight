"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Activity, ArrowLeft, Gauge, Maximize2, Minimize2, SunMedium } from "lucide-react";

const FREQUENCIES = [
  { label: "OFF", value: 0.0 },
  { label: "2.0 Hz", value: 2.0 },
  { label: "3.5 Hz", value: 3.5 },
  { label: "4.0 Hz", value: 4.0 },
  { label: "5.0 Hz", value: 5.0 },
  { label: "6.0 Hz", value: 6.0 },
  { label: "7.5 Hz", value: 7.5 },
  { label: "10.0 Hz", value: 10.0 },
];

const FULLSCREEN_FREQUENCIES = [
  { label: "OFF", value: 0.0 },
  { label: "2.0 Hz", value: 2.0 },
  { label: "4.0 Hz", value: 4.0 },
  { label: "7.5 Hz", value: 7.5 },
];

const AMPLITUDES = [
  { label: "6 px", value: 6 },
  { label: "12 px", value: 12 },
  { label: "20 px", value: 20 },
];

const BRIGHTNESS_LEVELS = [
  { id: "low", label: "Low 45%", scale: 0.45 },
  { id: "med", label: "Med 70% (Default)", scale: 0.7 },
  { id: "high", label: "High 100%", scale: 1.0 },
] as const;

type BrightnessId = (typeof BRIGHTNESS_LEVELS)[number]["id"];

const VIEWPORT_SIZE = 320;
const PAD = 56; // Padding > ±20px max displacement to guarantee zero edge flashing during translation
const OVERSIZED_SIZE = VIEWPORT_SIZE + 2 * PAD; // 432x432 px

// Anti-overexposure dark matte ground (#0B0F17) + mid-bright matte geometric palette
const BG_RGB: readonly [number, number, number] = [11, 15, 23]; // #0B0F17
const FG_MATTE_RGB: ReadonlyArray<readonly [number, number, number]> = [
  [184, 194, 204], // #B8C2CC
  [138, 150, 163], // #8A96A3
  [220, 227, 234], // #DCE3EA
];

function scaledMatteColor(rgb: readonly [number, number, number], scale: number): string {
  const r = Math.round(BG_RGB[0] + (rgb[0] - BG_RGB[0]) * scale);
  const g = Math.round(BG_RGB[1] + (rgb[1] - BG_RGB[1]) * scale);
  const b = Math.round(BG_RGB[2] + (rgb[2] - BG_RGB[2]) * scale);
  return `rgb(${r}, ${g}, ${b})`;
}

export default function OpticalTargetPage() {
  const [frequency, setFrequency] = useState<number>(4.0);
  const [amplitude, setAmplitude] = useState<number>(12);
  const [enableHarmonic, setEnableHarmonic] = useState<boolean>(false);
  const [vibrationAxis, setVibrationAxis] = useState<"horizontal" | "vertical">("horizontal");
  const [brightness, setBrightness] = useState<BrightnessId>("med");
  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);

  const anchorCanvasRef = useRef<HTMLCanvasElement>(null);
  const targetCanvasRef = useRef<HTMLCanvasElement>(null);
  const speckleCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const wakeLockRef = useRef<any>(null);

  // Live mutable refs so the persistent requestAnimationFrame loop reads latest state without teardown/stale closures
  const paramsRef = useRef({
    frequency: 4.0,
    amplitude: 12,
    enableHarmonic: false,
    vibrationAxis: "horizontal" as "horizontal" | "vertical",
  });
  paramsRef.current = { frequency, amplitude, enableHarmonic, vibrationAxis };

  const phaseRef = useRef<number>(0);

  const drawAnchorCanvas = useCallback(() => {
    const canvas = anchorCanvasRef.current;
    const speckle = speckleCanvasRef.current;
    if (!canvas || !speckle) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(
      speckle,
      PAD,
      PAD,
      VIEWPORT_SIZE,
      VIEWPORT_SIZE,
      0,
      0,
      canvas.width,
      canvas.height
    );
  }, []);

  const enterFullscreen = async () => {
    setIsFullscreen(true);
    try {
      const docEl = document.documentElement as any;
      if (docEl.requestFullscreen) {
        await Promise.resolve(docEl.requestFullscreen()).catch(() => {});
      } else if (docEl.webkitRequestFullscreen) {
        docEl.webkitRequestFullscreen();
      }
    } catch {
      // Pure React/CSS theater mode remains active on iOS Safari where requestFullscreen is unavailable
    }
    try {
      const nav = navigator as any;
      if (nav.wakeLock?.request) {
        wakeLockRef.current = await nav.wakeLock.request("screen");
      }
    } catch {
      // Ignore Wake Lock unsupported or denied errors
    }
  };

  const exitFullscreen = async () => {
    setIsFullscreen(false);
    try {
      const doc = document as any;
      if (doc.fullscreenElement && doc.exitFullscreen) {
        await Promise.resolve(doc.exitFullscreen()).catch(() => {});
      } else if (doc.webkitFullscreenElement && doc.webkitExitFullscreen) {
        doc.webkitExitFullscreen();
      }
    } catch {
      // Ignore exit errors
    }
    try {
      if (wakeLockRef.current) {
        await wakeLockRef.current.release();
        wakeLockRef.current = null;
      }
    } catch {
      // Ignore release errors
    }
  };

  useEffect(() => {
    if (!isFullscreen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        void exitFullscreen();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isFullscreen]);

  useEffect(() => {
    return () => {
      try {
        wakeLockRef.current?.release?.();
      } catch {
        // Ignore cleanup errors
      }
    };
  }, []);

  // Generate deterministic non-periodic dark-ground anti-overexposure pattern scaled by Pattern Brightness
  useEffect(() => {
    const level = BRIGHTNESS_LEVELS.find((b) => b.id === brightness) ?? BRIGHTNESS_LEVELS[1];
    const speckleCanvas = document.createElement("canvas");
    speckleCanvas.width = OVERSIZED_SIZE;
    speckleCanvas.height = OVERSIZED_SIZE;
    const ctx = speckleCanvas.getContext("2d");
    if (!ctx) return;

    // Deep dark matte ground (#0B0F17) prevents screen-glare clipping on 720p webcam auto-exposure
    ctx.fillStyle = "#0B0F17";
    ctx.fillRect(0, 0, OVERSIZED_SIZE, OVERSIZED_SIZE);

    // Seeded deterministic LCG PRNG so geometry stays locked across brightness changes
    let seed = 4289371;
    const rand = () => {
      seed = (seed * 16807) % 2147483647;
      return (seed - 1) / 2147483646;
    };

    const palette = FG_MATTE_RGB.map((rgb) => scaledMatteColor(rgb, level.scale));

    // Coarse bold geometric blocks, bars, discs & wedges (24px–38px, ~40% target coverage)
    for (let i = 0; i < 68; i++) {
      const x = rand() * OVERSIZED_SIZE;
      const y = rand() * OVERSIZED_SIZE;
      const w = 24 + rand() * 14; // 24px to 38px
      const h = 18 + rand() * 18; // 18px to 36px
      ctx.fillStyle = palette[Math.floor(rand() * palette.length)];
      const shapeType = rand();
      if (shapeType > 0.62) {
        ctx.fillRect(x - w / 2, y - h / 2, w, h);
      } else if (shapeType > 0.34) {
        ctx.fillRect(x - w / 2, y - w / 2, w, w);
      } else if (shapeType > 0.14) {
        ctx.beginPath();
        ctx.arc(x, y, w / 2, 0, Math.PI * 2);
        ctx.fill();
      } else {
        ctx.beginPath();
        ctx.moveTo(x - w / 2, y + h / 2);
        ctx.lineTo(x + w / 2, y + h / 2);
        ctx.lineTo(x, y - h / 2);
        ctx.closePath();
        ctx.fill();
      }
    }

    // Medium non-periodic blocks & bars (16px–24px) for sub-pixel Fourier richness without 720p blur loss
    for (let i = 0; i < 95; i++) {
      const x = rand() * OVERSIZED_SIZE;
      const y = rand() * OVERSIZED_SIZE;
      const w = 16 + rand() * 8; // 16px to 24px
      const h = 16 + rand() * 8;
      ctx.fillStyle = palette[Math.floor(rand() * palette.length)];
      const shapeType = rand();
      if (shapeType > 0.45) {
        ctx.fillRect(x - w / 2, y - h / 2, w, h);
      } else {
        ctx.beginPath();
        ctx.arc(x, y, w / 2, 0, Math.PI * 2);
        ctx.fill();
      }
    }

    speckleCanvasRef.current = speckleCanvas;
    drawAnchorCanvas();
  }, [brightness, drawAnchorCanvas]);

  useEffect(() => {
    drawAnchorCanvas();
  }, [isFullscreen, drawAnchorCanvas]);

  // Persistent rAF loop reading live paramsRef so button presses apply immediately with zero phase reset
  useEffect(() => {
    let animId: number;
    let lastTime = performance.now();

    const render = (nowMs: number) => {
      const dt = Math.min((nowMs - lastTime) / 1000.0, 0.05);
      lastTime = nowMs;

      const {
        frequency: f,
        amplitude: amp,
        enableHarmonic: harm,
        vibrationAxis: axis,
      } = paramsRef.current;

      let offset = 0;
      if (f > 0) {
        phaseRef.current += 2 * Math.PI * f * dt;
        offset = amp * Math.sin(phaseRef.current);
        if (harm) {
          offset += amp * 0.35 * Math.sin(2 * phaseRef.current);
        }
      } else {
        phaseRef.current = 0;
      }

      const canvas = targetCanvasRef.current;
      const speckle = speckleCanvasRef.current;
      if (canvas && speckle) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          const dx = axis === "horizontal" ? offset : 0;
          const dy = axis === "vertical" ? offset : 0;

          ctx.clearRect(0, 0, canvas.width, canvas.height);
          ctx.drawImage(
            speckle,
            PAD - dx,
            PAD - dy,
            VIEWPORT_SIZE,
            VIEWPORT_SIZE,
            0,
            0,
            canvas.width,
            canvas.height
          );
        }
      }

      animId = requestAnimationFrame(render);
    };

    animId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animId);
  }, []);

  const currentBrightness =
    BRIGHTNESS_LEVELS.find((b) => b.id === brightness) ?? BRIGHTNESS_LEVELS[1];

  return (
    <div
      data-testid={isFullscreen ? "target-fullscreen-overlay" : "target-stage-page"}
      className={
        isFullscreen
          ? "fixed inset-0 z-50 h-[100dvh] w-screen bg-black overflow-hidden flex flex-col justify-between p-3 font-sans text-slate-100"
          : "min-h-screen bg-[#080C14] text-slate-100 flex flex-col font-sans"
      }
    >
      {/* Top Header - hidden in Fullscreen View */}
      {!isFullscreen && (
        <header className="relative z-10 border-b border-white/10 bg-[#0D121A]/90 backdrop-blur px-4 sm:px-6 py-3 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 text-slate-300 rounded text-xs font-mono transition touch-manipulation cursor-pointer"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Workstation
            </Link>
            <div>
              <h1 className="text-sm font-bold tracking-wider font-mono text-white flex items-center gap-2">
                <Activity className="w-4 h-4 text-[#22D3EE]" />
                PHASESIGHT OPTICAL BENCH TEST TARGET
              </h1>
              <p className="text-[11px] text-slate-400 font-mono">
                Anti-overexposure dark-ground matte speckle for 720p camera &amp; phase correlation validation
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Fullscreen Button (Pure React/CSS Theater Mode + Progressive Enhancement) */}
            <button
              type="button"
              data-testid="btn-fullscreen-target"
              onClick={enterFullscreen}
              className="flex items-center gap-1.5 px-3 py-2 bg-[#22D3EE]/10 hover:bg-[#22D3EE]/20 border border-[#22D3EE]/30 text-[#22D3EE] rounded text-xs font-mono transition touch-manipulation cursor-pointer"
            >
              <Maximize2 className="w-3.5 h-3.5" />
              Fullscreen Target View
            </button>

            {/* Frequency Readout */}
            <div className="flex items-center gap-3 bg-[#131B26] border border-[#22D3EE]/30 rounded px-3 py-1.5 font-mono">
              <div className="flex flex-col text-right">
                <span className="text-[9px] text-slate-400 uppercase">Target Freq</span>
                <div
                  data-testid="target-freq-badge"
                  className="text-lg font-black tracking-tight text-[#22D3EE]"
                >
                  {frequency > 0 ? `${frequency.toFixed(2)} Hz` : "STATIC"}
                </div>
              </div>
              {enableHarmonic && frequency > 0 && (
                <div className="border-l border-white/10 pl-2.5 flex flex-col">
                  <span className="text-[9px] text-[#F59E0B]">2X HARM</span>
                  <span className="text-xs font-bold text-[#F59E0B]">
                    {(2 * frequency).toFixed(1)} Hz
                  </span>
                </div>
              )}
            </div>
          </div>
        </header>
      )}

      {/* Main Target Stage */}
      <main
        className={
          isFullscreen
            ? "flex-1 flex flex-col items-center justify-between w-full max-w-5xl mx-auto min-h-0"
            : "flex-1 flex flex-col items-center justify-center p-3 sm:p-6 gap-5 sm:gap-6 max-w-5xl mx-auto w-full"
        }
      >
        {/* Instructions - hidden in Fullscreen */}
        {!isFullscreen && (
          <div className="w-full bg-[#0D121A] border border-white/5 rounded p-3 text-xs font-mono text-slate-300 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <Gauge className="w-4 h-4 text-[#22D3EE] shrink-0" />
              <span>
                Aim camera at panels: place <strong className="text-[#F59E0B]">ANCHOR ROI</strong> on Left Panel and{" "}
                <strong className="text-[#22D3EE]">TARGET ROI</strong> on Right Panel.
              </span>
            </div>
            <span className="text-[11px] text-slate-400">
              Dark-ground 16–38px matte blocks (~40% coverage · {currentBrightness.label})
            </span>
          </div>
        )}

        {/* The Two Panels: Left Anchor, Right Target */}
        <div
          data-testid="target-panels-grid"
          className={
            isFullscreen
              ? "grid grid-cols-2 gap-4 items-center justify-items-center flex-1 w-full max-w-5xl mx-auto select-none"
              : "flex flex-col sm:flex-row items-center justify-center gap-6 sm:gap-8 w-full max-w-3xl select-none"
          }
        >
          {/* Left Panel: Static Anchor */}
          <div className="flex flex-col items-center gap-1.5">
            <div className="text-[11px] sm:text-xs font-mono font-bold text-[#F59E0B] flex items-center gap-1.5">
              <span className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-[#F59E0B]" />
              STATIC ANCHOR (0.00 Hz)
            </div>
            <div
              data-testid="anchor-panel-box"
              className={
                isFullscreen
                  ? "w-[min(42vw,68dvh)] aspect-square relative p-1.5 sm:p-2 bg-black border-2 border-[#F59E0B]/80 rounded-xl overflow-hidden flex items-center justify-center"
                  : "relative p-3 sm:p-4 bg-[#070B12] border-2 border-[#F59E0B]/70 rounded-xl shadow-2xl shadow-[#F59E0B]/10 overflow-hidden"
              }
            >
              <canvas
                ref={anchorCanvasRef}
                data-testid="anchor-speckle-canvas"
                width={VIEWPORT_SIZE}
                height={VIEWPORT_SIZE}
                className={
                  isFullscreen
                    ? "block w-full h-full rounded-lg bg-[#0B0F17]"
                    : "block rounded-lg bg-[#0B0F17] shadow-inner max-w-full h-auto"
                }
              />
            </div>
            {!isFullscreen && (
              <span className="text-[11px] font-mono text-slate-400">
                Stationary Ground (Draw 80×80–100×100 ROI inside)
              </span>
            )}
          </div>

          {/* Right Panel: Vibrating Target */}
          <div className="flex flex-col items-center gap-1.5">
            <div
              data-testid="vibrating-target-label"
              className="text-[11px] sm:text-xs font-mono font-bold text-[#22D3EE] flex items-center gap-1.5"
            >
              <span className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-[#22D3EE] animate-pulse" />
              VIBRATING TARGET ({frequency > 0 ? `${frequency.toFixed(1)} Hz` : "OFF"})
            </div>
            <div
              data-testid="target-panel-box"
              className={
                isFullscreen
                  ? "w-[min(42vw,68dvh)] aspect-square relative p-1.5 sm:p-2 bg-black border-2 border-[#22D3EE]/80 rounded-xl overflow-hidden flex items-center justify-center"
                  : "relative p-3 sm:p-4 bg-[#070B12] border-2 border-[#22D3EE]/70 rounded-xl shadow-2xl shadow-[#22D3EE]/10 overflow-hidden"
              }
            >
              <canvas
                ref={targetCanvasRef}
                data-testid="target-speckle-canvas"
                width={VIEWPORT_SIZE}
                height={VIEWPORT_SIZE}
                className={
                  isFullscreen
                    ? "block w-full h-full rounded-lg bg-[#0B0F17]"
                    : "block rounded-lg bg-[#0B0F17] shadow-inner max-w-full h-auto"
                }
              />
            </div>
            {!isFullscreen && (
              <span
                data-testid="target-motion-summary"
                className="text-[11px] font-mono text-slate-400"
              >
                Linear {vibrationAxis} translation (±{amplitude} px)
              </span>
            )}
          </div>
        </div>

        {/* Fullscreen Minimal Dark Bottom Control Strip */}
        {isFullscreen ? (
          <div
            data-testid="fullscreen-bottom-controls"
            className="relative z-20 w-full max-w-5xl mx-auto flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#0A0E17]/95 border border-white/10 rounded-lg font-mono text-[11px] shrink-0"
          >
            <div className="flex flex-wrap items-center gap-1.5">
              {FULLSCREEN_FREQUENCIES.map((f) => (
                <button
                  key={f.value}
                  type="button"
                  aria-pressed={frequency === f.value}
                  onClick={() => setFrequency(f.value)}
                  className={`px-2.5 py-1.5 min-h-[32px] rounded font-semibold transition touch-manipulation cursor-pointer ${
                    frequency === f.value
                      ? "bg-[#22D3EE] text-black"
                      : "bg-[#131B26] text-slate-300 hover:bg-white/10 border border-white/10"
                  }`}
                >
                  {f.label}
                </button>
              ))}
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <div className="flex items-center gap-1 bg-[#131B26] border border-white/10 rounded p-0.5">
                {[12, 20].map((amp) => (
                  <button
                    key={amp}
                    type="button"
                    aria-pressed={amplitude === amp}
                    onClick={() => setAmplitude(amp)}
                    className={`px-2 py-1 rounded font-semibold transition touch-manipulation cursor-pointer ${
                      amplitude === amp
                        ? "bg-amber-400 text-black"
                        : "text-slate-300 hover:text-white"
                    }`}
                  >
                    {amp} px
                  </button>
                ))}
              </div>

              <div className="flex items-center gap-1 bg-[#131B26] border border-white/10 rounded p-0.5">
                {BRIGHTNESS_LEVELS.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    aria-pressed={brightness === b.id}
                    onClick={() => setBrightness(b.id)}
                    className={`px-2 py-1 rounded font-semibold transition touch-manipulation cursor-pointer ${
                      brightness === b.id
                        ? "bg-emerald-400 text-black"
                        : "text-slate-300 hover:text-white"
                    }`}
                  >
                    {b.id === "low" ? "45%" : b.id === "med" ? "70%" : "100%"}
                  </button>
                ))}
              </div>

              <button
                type="button"
                data-testid="btn-exit-fullscreen"
                onClick={exitFullscreen}
                className="flex items-center gap-1 px-3 py-1.5 bg-rose-950/60 hover:bg-rose-900/80 border border-rose-700/60 text-rose-200 rounded font-semibold transition touch-manipulation cursor-pointer"
              >
                <Minimize2 className="w-3 h-3" />
                Exit
              </button>
            </div>
          </div>
        ) : (
          /* Normal Calibration Controls Bar */
          <div
            data-testid="target-controls-bar"
            className="relative z-10 w-full max-w-3xl bg-[#0D121A] border border-white/10 rounded-lg p-4 sm:p-5 flex flex-col gap-4 font-mono text-xs"
          >
            <div className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 pb-4">
              {/* Frequency Selection */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                  Vibration Frequency (Hz) — Webcam Presets
                </label>
                <div className="flex flex-wrap items-center gap-1.5">
                  {FREQUENCIES.map((f) => (
                    <button
                      key={f.value}
                      type="button"
                      data-testid={`btn-freq-${f.value}`}
                      aria-pressed={frequency === f.value}
                      onClick={() => setFrequency(f.value)}
                      className={`px-3 py-2 min-h-[36px] rounded font-semibold transition touch-manipulation cursor-pointer ${
                        frequency === f.value
                          ? "bg-[#22D3EE] text-black shadow-md shadow-[#22D3EE]/30"
                          : "bg-[#131B26] text-slate-300 hover:bg-white/10 border border-white/10"
                      }`}
                    >
                      {f.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Amplitude Selection */}
              <div className="flex flex-col gap-1.5">
                <label className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                  Displacement Amplitude
                </label>
                <div className="flex items-center gap-1.5">
                  {AMPLITUDES.map((a) => (
                    <button
                      key={a.value}
                      type="button"
                      data-testid={`btn-amp-${a.value}`}
                      aria-pressed={amplitude === a.value}
                      onClick={() => setAmplitude(a.value)}
                      className={`px-3 py-2 min-h-[36px] rounded font-semibold transition touch-manipulation cursor-pointer ${
                        amplitude === a.value
                          ? "bg-amber-400 text-black shadow-md shadow-amber-400/30"
                          : "bg-[#131B26] text-slate-300 hover:bg-white/10 border border-white/10"
                      }`}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Pattern Brightness Control */}
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <div className="flex items-center gap-2 text-[10px] text-slate-400 font-bold uppercase tracking-wider">
                <SunMedium className="w-3.5 h-3.5 text-emerald-400" />
                Pattern Brightness (Anti-Overexposure)
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                {BRIGHTNESS_LEVELS.map((b) => (
                  <button
                    key={b.id}
                    type="button"
                    data-testid={`btn-brightness-${b.id}`}
                    aria-pressed={brightness === b.id}
                    onClick={() => setBrightness(b.id)}
                    className={`px-3 py-1.5 min-h-[34px] rounded font-semibold transition touch-manipulation cursor-pointer ${
                      brightness === b.id
                        ? "bg-emerald-400 text-black shadow-md shadow-emerald-400/25"
                        : "bg-[#131B26] text-slate-300 hover:bg-white/10 border border-white/10"
                    }`}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-4">
              {/* 2X Harmonic Toggle */}
              <label className="flex items-center gap-2.5 min-h-[34px] cursor-pointer touch-manipulation">
                <input
                  type="checkbox"
                  data-testid="chk-harmonic-2x"
                  checked={enableHarmonic}
                  onChange={(e) => setEnableHarmonic(e.target.checked)}
                  className="w-4 h-4 rounded bg-[#131B26] border-white/20 text-[#22D3EE] focus:ring-0 cursor-pointer"
                />
                <span className="text-slate-200">Enable 2X Harmonic (+35% amplitude @ 2f)</span>
              </label>

              {/* Vibration Axis */}
              <div className="flex items-center gap-1.5">
                <span className="text-slate-400 text-[11px] mr-1">Axis:</span>
                <button
                  type="button"
                  data-testid="btn-axis-horizontal"
                  aria-pressed={vibrationAxis === "horizontal"}
                  onClick={() => setVibrationAxis("horizontal")}
                  className={`px-3 py-1.5 min-h-[34px] rounded transition touch-manipulation cursor-pointer ${
                    vibrationAxis === "horizontal"
                      ? "bg-white/20 text-white font-bold border border-white/20"
                      : "bg-[#131B26] text-slate-400 hover:text-white border border-white/5"
                  }`}
                >
                  Horizontal (ΔX)
                </button>
                <button
                  type="button"
                  data-testid="btn-axis-vertical"
                  aria-pressed={vibrationAxis === "vertical"}
                  onClick={() => setVibrationAxis("vertical")}
                  className={`px-3 py-1.5 min-h-[34px] rounded transition touch-manipulation cursor-pointer ${
                    vibrationAxis === "vertical"
                      ? "bg-white/20 text-white font-bold border border-white/20"
                      : "bg-[#131B26] text-slate-400 hover:text-white border border-white/5"
                  }`}
                >
                  Vertical (ΔY)
                </button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Footer */}
      {!isFullscreen && (
        <footer className="border-t border-white/5 bg-[#0D121A] px-6 py-3 text-center text-[11px] font-mono text-slate-500">
          PhaseSight Non-Contact Optical Vibration Screening · Precision Bench Calibration Tool
        </footer>
      )}
    </div>
  );
}
