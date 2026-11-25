"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import type { TraceSample } from "@/lib/types";
import { Sliders, Eye, Activity } from "lucide-react";

interface OscilloscopeCanvasProps {
  samples: TraceSample[];
  maxSamples?: number;
  height?: number;
  isStatic?: boolean;
  correlationResponse?: number | null;
  anchorCorrelationResponse?: number | null;
  resetKey?: string | number | null;
}

export const OscilloscopeCanvas: React.FC<OscilloscopeCanvasProps> = ({
  samples,
  maxSamples = 300,
  height = 240,
  isStatic = false,
  correlationResponse = null,
  anchorCorrelationResponse = null,
  resetKey,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Trace buffer
  const bufferRef = useRef<TraceSample[]>([]);

  // Controls
  const [splitMode, setSplitMode] = useState<boolean>(false);
  const [showRawComponents, setShowRawComponents] = useState<boolean>(false);
  const [scaleMode, setScaleMode] = useState<"auto" | "0.5" | "1.0" | "2.0">("auto");
  const [hoverData, setHoverData] = useState<TraceSample | null>(null);
  const [shakeRmsStats, setShakeRmsStats] = useState<{
    rawTgtRms: number;
    relRms: number;
  } | null>(null);

  // Clear internal buffer immediately when session / resetKey changes
  useEffect(() => {
    bufferRef.current = [];
    setHoverData(null);
    setShakeRmsStats(null);
  }, [resetKey]);

  // Append new samples into circular buffer (streaming mode only)
  useEffect(() => {
    if (!isStatic && samples && samples.length > 0) {
      const buf = bufferRef.current;
      for (const s of samples) {
        buf.push(s);
        if (buf.length > maxSamples) {
          buf.shift();
        }
      }
    }

    if (!showRawComponents) {
      setShakeRmsStats(null);
      return;
    }

    const activeBuf = isStatic ? samples : bufferRef.current;
    if (!activeBuf || activeBuf.length < 2) {
      setShakeRmsStats(null);
      return;
    }

    const rawVals: number[] = [];
    const relVals: number[] = [];
    for (const s of activeBuf) {
      if (s.raw_target_dx !== undefined && Number.isFinite(s.raw_target_dx)) {
        rawVals.push(s.raw_target_dx);
      }
      if (Number.isFinite(s.rel_dx_px)) {
        relVals.push(s.rel_dx_px);
      }
    }

    if (rawVals.length < 2 || relVals.length < 2) {
      setShakeRmsStats(null);
      return;
    }

    const acRms = (arr: number[]) => {
      const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
      const sumSq = arr.reduce((a, b) => a + (b - mean) * (b - mean), 0);
      return Math.sqrt(sumSq / arr.length);
    };

    setShakeRmsStats({
      rawTgtRms: acRms(rawVals),
      relRms: acRms(relVals),
    });
  }, [samples, maxSamples, isStatic, showRawComponents]);

  // Render loop
  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = rect.width;
    const h = rect.height;
    if (w <= 0 || h <= 0) return;

    const targetW = Math.round(w * dpr);
    const targetH = Math.round(h * dpr);

    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Dark grid background
    ctx.fillStyle = "#070A0F";
    ctx.fillRect(0, 0, w, h);

    const buf = isStatic ? samples : bufferRef.current;
    if (buf.length < 2) {
      // Empty state prompt
      ctx.fillStyle = "rgba(255, 255, 255, 0.2)";
      ctx.font = "11px var(--font-mono)";
      ctx.textAlign = "center";
      ctx.fillText("WAITING FOR DISPLACEMENT SAMPLES...", w / 2, h / 2);
      ctx.restore();
      return;
    }

    // Determine scale limits
    let maxAbs = 0.1;
    if (scaleMode === "0.5") maxAbs = 0.5;
    else if (scaleMode === "1.0") maxAbs = 1.0;
    else if (scaleMode === "2.0") maxAbs = 2.0;
    else {
      for (const s of buf) {
        maxAbs = Math.max(maxAbs, Math.abs(s.rel_dx_px), Math.abs(s.rel_dy_px));
        if (showRawComponents) {
          if (s.raw_target_dx !== undefined) maxAbs = Math.max(maxAbs, Math.abs(s.raw_target_dx));
          if (s.raw_anchor_dx !== undefined) maxAbs = Math.max(maxAbs, Math.abs(s.raw_anchor_dx));
        }
      }
      maxAbs = Math.max(0.15, maxAbs * 1.25);
    }

    const n = buf.length;
    const stepX = isStatic ? w / Math.max(1, n - 1) : w / (maxSamples - 1);

    if (splitMode) {
      // Split mode: Top half = X-axis, Bottom half = Y-axis
      const halfH = h / 2;

      // Dividers & Zero lines
      ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(0, halfH);
      ctx.lineTo(w, halfH);
      ctx.stroke();

      // Top zero line (X)
      const zeroY1 = halfH / 2;
      ctx.strokeStyle = "rgba(34, 211, 238, 0.18)";
      ctx.beginPath();
      ctx.moveTo(0, zeroY1);
      ctx.lineTo(w, zeroY1);
      ctx.stroke();

      // Bottom zero line (Y)
      const zeroY2 = halfH + halfH / 2;
      ctx.strokeStyle = "rgba(245, 158, 11, 0.18)";
      ctx.beginPath();
      ctx.moveTo(0, zeroY2);
      ctx.lineTo(w, zeroY2);
      ctx.stroke();

      // Draw X displacement trace (Cyan)
      ctx.strokeStyle = "#22D3EE";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = isStatic ? i * stepX : (maxSamples - n + i) * stepX;
        const val = buf[i].rel_dx_px;
        const y = zeroY1 - (val / maxAbs) * (halfH / 2 - 8);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Draw Y displacement trace (Amber)
      ctx.strokeStyle = "#F59E0B";
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = isStatic ? i * stepX : (maxSamples - n + i) * stepX;
        const val = buf[i].rel_dy_px;
        const y = zeroY2 - (val / maxAbs) * (halfH / 2 - 8);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Labels
      ctx.font = "10px var(--font-mono)";
      ctx.fillStyle = "#22D3EE";
      ctx.textAlign = "left";
      ctx.fillText(`REL ΔX (±${maxAbs.toFixed(2)} px)`, 8, 14);

      ctx.fillStyle = "#F59E0B";
      ctx.fillText(`REL ΔY (±${maxAbs.toFixed(2)} px)`, 8, halfH + 14);
    } else {
      // Overlaid mode: Shared zero center
      const zeroY = h / 2;

      // Grid lines
      ctx.strokeStyle = "rgba(255, 255, 255, 0.08)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      // Center
      ctx.moveTo(0, zeroY);
      ctx.lineTo(w, zeroY);
      // Top quarter
      ctx.moveTo(0, h * 0.25);
      ctx.lineTo(w, h * 0.25);
      // Bottom quarter
      ctx.moveTo(0, h * 0.75);
      ctx.lineTo(w, h * 0.75);
      ctx.stroke();

      // Optional Raw components to demonstrate camera shake cancellation
      if (showRawComponents) {
        // Raw target X (faint dashed cyan)
        ctx.strokeStyle = "rgba(34, 211, 238, 0.35)";
        ctx.setLineDash([2, 4]);
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const x = isStatic ? i * stepX : (maxSamples - n + i) * stepX;
          const val = buf[i].raw_target_dx ?? buf[i].rel_dx_px;
          const y = zeroY - (val / maxAbs) * (zeroY - 12);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();

        // Raw anchor X (faint dashed white)
        ctx.strokeStyle = "rgba(255, 255, 255, 0.3)";
        ctx.beginPath();
        for (let i = 0; i < n; i++) {
          const x = isStatic ? i * stepX : (maxSamples - n + i) * stepX;
          const val = buf[i].raw_anchor_dx ?? 0;
          const y = zeroY - (val / maxAbs) * (zeroY - 12);
          if (i === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
        ctx.setLineDash([]);
      }

      // Rel ΔX (Cyan)
      ctx.strokeStyle = "#22D3EE";
      ctx.lineWidth = 1.75;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = isStatic ? i * stepX : (maxSamples - n + i) * stepX;
        const val = buf[i].rel_dx_px;
        const y = zeroY - (val / maxAbs) * (zeroY - 12);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Rel ΔY (Amber)
      ctx.strokeStyle = "#F59E0B";
      ctx.lineWidth = 1.75;
      ctx.beginPath();
      for (let i = 0; i < n; i++) {
        const x = isStatic ? i * stepX : (maxSamples - n + i) * stepX;
        const val = buf[i].rel_dy_px;
        const y = zeroY - (val / maxAbs) * (zeroY - 12);
        if (i === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
      }
      ctx.stroke();

      // Scale legend
      ctx.font = "10px var(--font-mono)";
      ctx.fillStyle = "rgba(255, 255, 255, 0.4)";
      ctx.textAlign = "left";
      ctx.fillText(`±${maxAbs.toFixed(2)} px`, 8, 14);
    }
    ctx.restore();
  }, [splitMode, showRawComponents, scaleMode, maxSamples, isStatic, samples]);

  // Request animation frame loop
  useEffect(() => {
    let animId: number;
    const loop = () => {
      draw();
      animId = requestAnimationFrame(loop);
    };
    animId = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(animId);
  }, [draw]);

  // Mouse hover readout
  const handleMouseMove = (e: React.MouseEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const buf = isStatic ? samples : bufferRef.current;
    if (buf.length === 0) return;

    if (isStatic) {
      const idx = Math.min(
        buf.length - 1,
        Math.max(0, Math.round((mx / rect.width) * (buf.length - 1)))
      );
      setHoverData(buf[idx]);
    } else {
      const stepX = rect.width / (maxSamples - 1);
      const startIdx = maxSamples - buf.length;
      const sampleIdx = Math.floor(mx / stepX) - startIdx;
      if (sampleIdx >= 0 && sampleIdx < buf.length) {
        setHoverData(buf[sampleIdx]);
      } else {
        setHoverData(null);
      }
    }
  };

  const latestSample = isStatic
    ? samples[samples.length - 1]
    : bufferRef.current[bufferRef.current.length - 1];
  const activeSample = hoverData || latestSample;

  return (
    <div className="flex flex-col gap-1.5 p-3 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded">
      {/* Control bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-[#22D3EE]" />
          <span className="font-semibold text-slate-200">
            DISPLACEMENT OSCILLOSCOPE
          </span>
          <span className="text-[10px] text-slate-500 font-mono">
            {isStatic
              ? `${samples.length} samples`
              : `${bufferRef.current.length} / ${maxSamples} samples`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          {/* Overlaid vs Split */}
          <button
            type="button"
            onClick={() => setSplitMode(!splitMode)}
            className={`px-2 py-0.5 rounded text-[11px] border font-mono transition ${
              splitMode
                ? "bg-slate-700 text-white border-slate-500"
                : "bg-white/5 text-slate-400 border-white/10 hover:bg-white/10"
            }`}
          >
            {splitMode ? "Dual Axis (Split)" : "Shared Axis"}
          </button>

          {/* Show Raw Shake toggle */}
          <button
            type="button"
            onClick={() => setShowRawComponents(!showRawComponents)}
            className={`flex items-center gap-1 px-2 py-0.5 rounded text-[11px] border font-mono transition ${
              showRawComponents
                ? "bg-[#22D3EE]/20 text-[#22D3EE] border-[#22D3EE]/50"
                : "bg-white/5 text-slate-400 border-white/10 hover:bg-white/10"
            }`}
            title="Demonstrate common-mode camera shake subtraction"
          >
            <Eye className="w-3 h-3" />
            Raw Shake
          </button>

          {/* Scale mode */}
          <div className="flex items-center gap-1 bg-[#131B26] border border-white/10 rounded px-1 py-0.5 text-[11px] font-mono">
            <Sliders className="w-3 h-3 text-slate-400" />
            {(["auto", "0.5", "1.0", "2.0"] as const).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setScaleMode(mode)}
                className={`px-1.5 py-0.5 rounded transition ${
                  scaleMode === mode
                    ? "bg-[#22D3EE] text-black font-semibold"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {mode === "auto" ? "Auto" : `±${mode}`}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Live Camera Shake Cancellation Metric Pill */}
      {showRawComponents && shakeRmsStats && (
        <div
          data-testid="shake-cancellation-pill"
          className="flex flex-wrap items-center justify-between gap-2 px-2.5 py-1 bg-emerald-950/30 border border-emerald-700/50 rounded text-[11px] font-mono"
        >
          <span className="text-slate-300">
            ANCHOR CANCELLATION (WINDOWED AC RMS):
          </span>
          <div className="flex items-center gap-2">
            <span className="text-slate-300 tabular-nums">
              Raw Tgt RMS:{" "}
              <strong className="text-white">
                {shakeRmsStats.rawTgtRms.toFixed(2)} px
              </strong>
            </span>
            <span className="text-emerald-400">→</span>
            <span className="text-[#22D3EE] tabular-nums">
              Differential RMS:{" "}
              <strong className="text-[#22D3EE]">
                {shakeRmsStats.relRms.toFixed(2)} px
              </strong>
            </span>
          </div>
        </div>
      )}

      {/* Canvas view */}
      <div
        ref={containerRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={() => setHoverData(null)}
        style={{ height: `${height}px` }}
        className="relative w-full bg-[#070A0F] border border-[rgba(255,255,255,0.08)] rounded overflow-hidden cursor-crosshair"
      >
        <canvas ref={canvasRef} className="w-full h-full" />
      </div>

      {/* Live cursor & response readout strip */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-2 py-1.5 bg-[#131B26] border border-[rgba(255,255,255,0.08)] rounded text-xs font-mono">
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#22D3EE]" />
            <span className="text-slate-400">ΔX:</span>
            <span className="text-[#22D3EE] font-semibold tabular-nums">
              {activeSample?.rel_dx_px != null && !isNaN(activeSample.rel_dx_px)
                ? `${activeSample.rel_dx_px.toFixed(3)} px`
                : "--"}
            </span>
          </div>

          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full bg-[#F59E0B]" />
            <span className="text-slate-400">ΔY:</span>
            <span className="text-[#F59E0B] font-semibold tabular-nums">
              {activeSample?.rel_dy_px != null && !isNaN(activeSample.rel_dy_px)
                ? `${activeSample.rel_dy_px.toFixed(3)} px`
                : "--"}
            </span>
          </div>

          {activeSample && activeSample.t != null && !isNaN(activeSample.t) && (
            <div className="text-[11px] text-slate-500 tabular-nums">
              t={activeSample.t.toFixed(2)}s
            </div>
          )}
        </div>

        {/* Phase correlation response bars: TGT CORR and ANC CORR */}
        <div className="flex items-center gap-3 font-mono text-[11px]">
          {/* TGT CORR */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-400">TGT CORR:</span>
            {(() => {
              const val =
                typeof correlationResponse === "number" && !isNaN(correlationResponse)
                  ? correlationResponse
                  : activeSample?.target_corr != null && !isNaN(activeSample.target_corr)
                  ? activeSample.target_corr
                  : (activeSample as any)?.target_response != null && !isNaN((activeSample as any).target_response)
                  ? (activeSample as any).target_response
                  : null;
              if (val != null) {
                const isLow = val < 0.15;
                return (
                  <>
                    <div className="w-14 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-75 ${
                          isLow ? "bg-rose-500" : "bg-[#22D3EE]"
                        }`}
                        style={{
                          width: `${Math.min(100, Math.max(0, val * 100))}%`,
                        }}
                      />
                    </div>
                    <span
                      className={`tabular-nums ${
                        isLow ? "text-rose-400 font-bold" : "text-slate-300"
                      }`}
                    >
                      {val.toFixed(2)}
                    </span>
                  </>
                );
              }
              return <span className="text-slate-500">N/A</span>;
            })()}
          </div>

          {/* ANC CORR */}
          <div className="flex items-center gap-1.5">
            <span className="text-[10px] text-slate-400">ANC CORR:</span>
            {(() => {
              const val =
                typeof anchorCorrelationResponse === "number" && !isNaN(anchorCorrelationResponse)
                  ? anchorCorrelationResponse
                  : activeSample?.anchor_corr != null && !isNaN(activeSample.anchor_corr)
                  ? activeSample.anchor_corr
                  : (activeSample as any)?.anchor_response != null && !isNaN((activeSample as any).anchor_response)
                  ? (activeSample as any).anchor_response
                  : null;
              if (val != null) {
                const isLow = val < 0.15;
                return (
                  <>
                    <div className="w-14 h-2 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className={`h-full transition-all duration-75 ${
                          isLow ? "bg-rose-500" : "bg-[#F59E0B]"
                        }`}
                        style={{
                          width: `${Math.min(100, Math.max(0, val * 100))}%`,
                        }}
                      />
                    </div>
                    <span
                      className={`tabular-nums ${
                        isLow ? "text-rose-400 font-bold" : "text-slate-300"
                      }`}
                    >
                      {val.toFixed(2)}
                    </span>
                  </>
                );
              }
              return <span className="text-slate-500">N/A</span>;
            })()}
          </div>
        </div>
      </div>
    </div>
  );
};
