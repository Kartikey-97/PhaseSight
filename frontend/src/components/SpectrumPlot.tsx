"use client";

import React, { useState, useMemo } from "react";
import type { SpectralMetrics } from "@/lib/types";
import { BarChart2, ShieldAlert } from "lucide-react";

interface SpectrumPlotProps {
  xMetrics?: SpectralMetrics | null;
  yMetrics?: SpectralMetrics | null;
  baselineFreqHz?: number | null;
  baselineFreqX?: number | null;
  baselineFreqY?: number | null;
  overlayFrequenciesHz?: number[];
  overlayPsd?: number[];
  overlayLabel?: string;
  height?: number;
}

export const SpectrumPlot: React.FC<SpectrumPlotProps> = ({
  xMetrics,
  yMetrics,
  baselineFreqHz,
  baselineFreqX,
  baselineFreqY,
  overlayFrequenciesHz,
  overlayPsd,
  overlayLabel,
  height = 240,
}) => {
  const effectiveBaselineFreqX = baselineFreqHz ?? baselineFreqX ?? null;
  const [useLogScale, setUseLogScale] = useState<boolean>(true);
  const [activeAxis, setActiveAxis] = useState<"both" | "x" | "y">("both");
  const [hoverCoord, setHoverCoord] = useState<{
    freq: number;
    psdX?: number;
    psdY?: number;
    xPx: number;
    yPx: number;
  } | null>(null);

  // Extract frequencies and PSD arrays
  const freqs = xMetrics?.frequencies || yMetrics?.frequencies || [];
  const psdX = xMetrics?.psd || [];
  const psdY = yMetrics?.psd || [];

  const nyquistHz = xMetrics?.nyquist_hz || yMetrics?.nyquist_hz || 30.0;
  const usableMaxHz = xMetrics?.usable_max_hz || yMetrics?.usable_max_hz || nyquistHz * 0.85;

  // Max PSD calculations for scaling (Power decibels = 10 * log10(PSD px²/Hz))
  const { maxPsd, minPsdDb, maxPsdDb } = useMemo(() => {
    let maxVal = 1e-12;
    if (activeAxis !== "y") {
      for (const v of psdX) if (v > maxVal) maxVal = v;
      if (overlayPsd) {
        for (const v of overlayPsd) if (v > maxVal) maxVal = v;
      }
    }
    if (activeAxis !== "x") {
      for (const v of psdY) if (v > maxVal) maxVal = v;
    }
    const rawMaxDb = 10 * Math.log10(Math.max(maxVal, 1e-12));
    const maxDb = Math.ceil(rawMaxDb / 5) * 5;
    const minDb = maxDb - 50; // 50 dB dynamic range
    return { maxPsd: maxVal, minPsdDb: minDb, maxPsdDb: maxDb };
  }, [psdX, psdY, overlayPsd, activeAxis]);

  // SVG dimensions
  const padding = { top: 20, right: 30, bottom: 30, left: 55 };
  const plotWidth = 700; // virtual SVG units
  const plotHeight = height;
  const innerW = plotWidth - padding.left - padding.right;
  const innerH = plotHeight - padding.top - padding.bottom;

  // Coordinates transform functions
  const scaleX = (freq: number) => {
    return padding.left + (Math.min(freq, nyquistHz) / nyquistHz) * innerW;
  };

  const scaleY = (psdVal: number) => {
    if (useLogScale) {
      const dbVal = 10 * Math.log10(Math.max(psdVal, 1e-12));
      const norm = (dbVal - minPsdDb) / Math.max(1, maxPsdDb - minPsdDb);
      return padding.top + innerH * (1 - Math.max(0, Math.min(1, norm)));
    }
    const norm = psdVal / Math.max(maxPsd, 1e-9);
    return padding.top + innerH * (1 - Math.max(0, Math.min(1, norm)));
  };

  // Build SVG path strings
  const pathX = useMemo(() => {
    if (activeAxis === "y" || freqs.length === 0 || psdX.length === 0) return "";
    return freqs
      .map((f, i) => {
        const x = scaleX(f);
        const y = scaleY(psdX[i] || 0);
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  }, [freqs, psdX, activeAxis, useLogScale, minPsdDb, maxPsdDb, maxPsd, nyquistHz]);

  const pathY = useMemo(() => {
    if (activeAxis === "x" || freqs.length === 0 || psdY.length === 0) return "";
    return freqs
      .map((f, i) => {
        const x = scaleX(f);
        const y = scaleY(psdY[i] || 0);
        return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
      })
      .join(" ");
  }, [freqs, psdY, activeAxis, useLogScale, minPsdDb, maxPsdDb, maxPsd, nyquistHz]);

  const pathOverlay = useMemo(() => {
    if (
      activeAxis === "y" ||
      !overlayFrequenciesHz ||
      !overlayPsd ||
      overlayFrequenciesHz.length === 0 ||
      overlayPsd.length === 0
    ) {
      return "";
    }
    const cmds: string[] = [];
    for (let i = 0; i < overlayFrequenciesHz.length; i++) {
      const f = overlayFrequenciesHz[i];
      if (f > nyquistHz) continue;
      const x = scaleX(f);
      const y = scaleY(overlayPsd[i] || 0);
      cmds.push(`${cmds.length === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`);
    }
    return cmds.join(" ");
  }, [
    overlayFrequenciesHz,
    overlayPsd,
    activeAxis,
    useLogScale,
    minPsdDb,
    maxPsdDb,
    maxPsd,
    nyquistHz,
  ]);

  // Usable limit x coord
  const usableEdgeX = scaleX(usableMaxHz);
  const nyquistEdgeX = scaleX(nyquistHz);

  // Mouse hover event on SVG
  const handleSvgMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (freqs.length === 0) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const clientX = e.clientX - rect.left;
    const normX = (clientX / rect.width) * plotWidth;
    const clampedX = Math.max(padding.left, Math.min(padding.left + innerW, normX));
    const targetFreq = ((clampedX - padding.left) / innerW) * nyquistHz;

    // Find closest bin
    let closestIdx = 0;
    let minDiff = 1e9;
    for (let i = 0; i < freqs.length; i++) {
      const diff = Math.abs(freqs[i] - targetFreq);
      if (diff < minDiff) {
        minDiff = diff;
        closestIdx = i;
      }
    }

    setHoverCoord({
      freq: freqs[closestIdx],
      psdX: psdX[closestIdx],
      psdY: psdY[closestIdx],
      xPx: scaleX(freqs[closestIdx]),
      yPx: scaleY(psdX[closestIdx] || psdY[closestIdx] || 0),
    });
  };

  return (
    <div className="flex flex-col gap-1.5 p-3 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded">
      {/* Control header */}
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <BarChart2 className="w-3.5 h-3.5 text-[#22D3EE]" />
          <span className="font-semibold text-slate-200">
            WELCH POWER SPECTRAL DENSITY (PSD)
          </span>
          <span className="text-[10px] text-slate-500 font-mono">
            Δf = {(xMetrics?.frequency_resolution_hz ?? 0.23).toFixed(2)} Hz
          </span>
          {pathOverlay && (
            <span
              data-testid="spectrum-overlay-chip"
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-emerald-950/50 border border-emerald-700/60 text-emerald-300 font-mono text-[10px]"
            >
              <span className="w-2.5 border-t-2 border-dashed border-[#10B981]" />
              vs {overlayLabel || "Reference"}
            </span>
          )}
        </div>

        <div className="flex items-center gap-2 font-mono text-[11px]">
          {/* Axis visibility toggle */}
          <div className="flex items-center bg-[#131B26] border border-white/10 rounded p-0.5">
            <button
              type="button"
              onClick={() => setActiveAxis("both")}
              className={`px-2 py-0.5 rounded transition ${
                activeAxis === "both"
                  ? "bg-slate-700 text-white"
                  : "text-slate-400 hover:text-white"
              }`}
            >
              X & Y
            </button>
            <button
              type="button"
              onClick={() => setActiveAxis("x")}
              className={`px-2 py-0.5 rounded transition ${
                activeAxis === "x"
                  ? "bg-[#22D3EE] text-black font-semibold"
                  : "text-[#22D3EE] hover:opacity-80"
              }`}
            >
              X Only
            </button>
            <button
              type="button"
              onClick={() => setActiveAxis("y")}
              className={`px-2 py-0.5 rounded transition ${
                activeAxis === "y"
                  ? "bg-[#F59E0B] text-black font-semibold"
                  : "text-[#F59E0B] hover:opacity-80"
              }`}
            >
              Y Only
            </button>
          </div>

          {/* Linear vs Log10 dB toggle */}
          <button
            type="button"
            onClick={() => setUseLogScale(!useLogScale)}
            className={`px-2 py-0.5 rounded border transition ${
              useLogScale
                ? "bg-slate-700 text-white border-slate-500"
                : "bg-white/5 text-slate-400 border-white/10 hover:bg-white/10"
            }`}
          >
            {useLogScale ? "Log10 (dB)" : "Linear"}
          </button>
        </div>
      </div>

      {/* Main SVG spectrum chart */}
      <div className="relative w-full bg-[#070A0F] border border-[rgba(255,255,255,0.08)] rounded overflow-hidden select-none">
        <svg
          viewBox={`0 0 ${plotWidth} ${plotHeight}`}
          className="w-full h-auto cursor-crosshair"
          onMouseMove={handleSvgMouseMove}
          onMouseLeave={() => setHoverCoord(null)}
        >
          {/* Y-axis unit indicator */}
          <text
            x={padding.left + 6}
            y={padding.top - 6}
            textAnchor="start"
            fill="rgba(255, 255, 255, 0.45)"
            fontSize="9"
            fontFamily="var(--font-mono)"
          >
            <title>dB re px²/Hz</title>
            {useLogScale ? "dB re px²/Hz" : "px²/Hz"}
          </text>

          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
            const y = padding.top + innerH * (1 - ratio);
            const dbVal = minPsdDb + ratio * (maxPsdDb - minPsdDb);
            return (
              <g key={`ygrid-${ratio}`}>
                <line
                  x1={padding.left}
                  y1={y}
                  x2={padding.left + innerW}
                  y2={y}
                  stroke="rgba(255, 255, 255, 0.06)"
                  strokeWidth="1"
                />
                <text
                  x={padding.left - 6}
                  y={y + 3}
                  textAnchor="end"
                  fill="rgba(255, 255, 255, 0.35)"
                  fontSize="9"
                  fontFamily="var(--font-mono)"
                >
                  <title>dB re px²/Hz</title>
                  {useLogScale
                    ? `${Math.round(dbVal)} dB`
                    : (ratio * maxPsd).toExponential(1)}
                </text>
              </g>
            );
          })}

          {/* Freq X grid */}
          {[0, 0.25, 0.5, 0.75, 1.0].map((ratio) => {
            const freqVal = ratio * nyquistHz;
            const x = scaleX(freqVal);
            return (
              <g key={`xgrid-${ratio}`}>
                <line
                  x1={x}
                  y1={padding.top}
                  x2={x}
                  y2={padding.top + innerH}
                  stroke="rgba(255, 255, 255, 0.06)"
                  strokeWidth="1"
                />
                <text
                  x={x}
                  y={padding.top + innerH + 16}
                  textAnchor="middle"
                  fill="rgba(255, 255, 255, 0.4)"
                  fontSize="9"
                  fontFamily="var(--font-mono)"
                >
                  {freqVal.toFixed(1)} Hz
                </text>
              </g>
            );
          })}

          {/* Bandwidth honesty: Unusable near-Nyquist zone shading */}
          <rect
            x={usableEdgeX}
            y={padding.top}
            width={Math.max(0, nyquistEdgeX - usableEdgeX)}
            height={innerH}
            fill="rgba(251, 113, 133, 0.08)"
            stroke="none"
          />
          <line
            x1={usableEdgeX}
            y1={padding.top}
            x2={usableEdgeX}
            y2={padding.top + innerH}
            stroke="#FB7185"
            strokeDasharray="4 4"
            strokeWidth="1.25"
          />
          <text
            x={usableEdgeX > plotWidth - 160 ? plotWidth - padding.right - 8 : usableEdgeX + 4}
            y={padding.top + 12}
            textAnchor={usableEdgeX > plotWidth - 160 ? "end" : "start"}
            fill="#FB7185"
            fontSize="8"
            fontFamily="var(--font-mono)"
          >
            ROLL-OFF / ALIASING MARGIN
          </text>

          {/* Nyquist boundary */}
          <line
            x1={nyquistEdgeX}
            y1={padding.top}
            x2={nyquistEdgeX}
            y2={padding.top + innerH}
            stroke="rgba(255, 255, 255, 0.3)"
            strokeWidth="1.5"
          />

          {/* PSD Curves */}
          {pathOverlay && (
            <path
              data-testid="spectrum-overlay-path"
              d={pathOverlay}
              fill="none"
              stroke="#10B981"
              strokeWidth="1.75"
              strokeDasharray="5 3"
              strokeOpacity="0.85"
              strokeLinejoin="round"
            />
          )}
          {pathY && (
            <path
              d={pathY}
              fill="none"
              stroke="#F59E0B"
              strokeWidth="1.75"
              strokeLinejoin="round"
            />
          )}
          {pathX && (
            <path
              d={pathX}
              fill="none"
              stroke="#22D3EE"
              strokeWidth="2"
              strokeLinejoin="round"
            />
          )}

          {/* 1X Dominant frequency pin for X */}
          {xMetrics && xMetrics.dominant_frequency_hz > 0 && activeAxis !== "y" && (
            <g>
              <line
                x1={scaleX(xMetrics.dominant_frequency_hz)}
                y1={padding.top}
                x2={scaleX(xMetrics.dominant_frequency_hz)}
                y2={padding.top + innerH}
                stroke="#22D3EE"
                strokeWidth="1"
                strokeDasharray="2 3"
              />
              <circle
                cx={scaleX(xMetrics.dominant_frequency_hz)}
                cy={scaleY(
                  xMetrics.psd?.[
                    freqs.findIndex(
                      (f) =>
                        Math.abs(f - xMetrics.dominant_frequency_hz) < 0.1
                    )
                  ] || maxPsd
                )}
                r="3.5"
                fill="#22D3EE"
              />
              <text
                x={scaleX(xMetrics.dominant_frequency_hz) + 4}
                y={padding.top + 24}
                fill="#22D3EE"
                fontSize="9"
                fontWeight="bold"
                fontFamily="var(--font-mono)"
              >
                1X {xMetrics.dominant_frequency_hz != null ? `${xMetrics.dominant_frequency_hz.toFixed(2)} Hz` : "--"}{" "}
                ({xMetrics.peak_to_median_db != null ? `${xMetrics.peak_to_median_db.toFixed(1)} dB` : "--"})
              </text>
            </g>
          )}

          {/* 2X Harmonic callout pin */}
          {xMetrics &&
            xMetrics.dominant_frequency_hz > 0 &&
            xMetrics.second_harmonic_ratio &&
            xMetrics.second_harmonic_ratio > 0.05 && (
              <g>
                <line
                  x1={scaleX(xMetrics.dominant_frequency_hz * 2)}
                  y1={padding.top + 30}
                  x2={scaleX(xMetrics.dominant_frequency_hz * 2)}
                  y2={padding.top + innerH}
                  stroke="rgba(34, 211, 238, 0.4)"
                  strokeWidth="1"
                  strokeDasharray="2 2"
                />
                <text
                  x={scaleX(xMetrics.dominant_frequency_hz * 2) + 3}
                  y={padding.top + 40}
                  fill="rgba(34, 211, 238, 0.8)"
                  fontSize="8"
                  fontFamily="var(--font-mono)"
                >
                  2X ({xMetrics.second_harmonic_ratio != null ? `${(xMetrics.second_harmonic_ratio * 100).toFixed(0)}%` : "--"})
                </text>
              </g>
            )}

          {/* Baseline reference marker (if asset baseline provided) */}
          {effectiveBaselineFreqX != null &&
            effectiveBaselineFreqX > 0 &&
            effectiveBaselineFreqX <= nyquistHz && (
              <g>
                <line
                  x1={scaleX(effectiveBaselineFreqX)}
                  y1={padding.top}
                  x2={scaleX(effectiveBaselineFreqX)}
                  y2={padding.top + innerH}
                  stroke="#10B981"
                  strokeWidth="1.5"
                  strokeDasharray="3 3"
                />
                <text
                  x={
                    scaleX(effectiveBaselineFreqX) > plotWidth - 120
                      ? scaleX(effectiveBaselineFreqX) - 4
                      : scaleX(effectiveBaselineFreqX) + 4
                  }
                  y={padding.top + innerH - 8}
                  textAnchor={
                    scaleX(effectiveBaselineFreqX) > plotWidth - 120
                      ? "end"
                      : "start"
                  }
                  fill="#10B981"
                  fontSize="8.5"
                  fontWeight="bold"
                  fontFamily="var(--font-mono)"
                >
                  BASELINE {effectiveBaselineFreqX.toFixed(2)} Hz
                </text>
              </g>
            )}

          {/* Hover Crosshair */}
          {hoverCoord && (
            <g>
              <line
                x1={hoverCoord.xPx}
                y1={padding.top}
                x2={hoverCoord.xPx}
                y2={padding.top + innerH}
                stroke="rgba(255, 255, 255, 0.5)"
                strokeWidth="1"
              />
              <circle
                cx={hoverCoord.xPx}
                cy={hoverCoord.yPx}
                r="4"
                fill="none"
                stroke="white"
                strokeWidth="1.5"
              />
            </g>
          )}
        </svg>

        {/* Empty state prompt */}
        {freqs.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-slate-500 font-mono text-xs">
            WARMING UP ROLLING SPECTRAL BUFFER (PSD WITHHELD)...
          </div>
        )}
      </div>

      {/* Hover Readout Footer */}
      <div className="flex flex-wrap items-center justify-between px-2 py-1 bg-[#131B26] border border-[rgba(255,255,255,0.08)] rounded text-xs font-mono">
        <div className="flex items-center gap-4">
          <span className="text-slate-400">CURSOR FREQ:</span>
          <span className="text-white font-semibold tabular-nums">
            {hoverCoord ? `${hoverCoord.freq.toFixed(2)} Hz` : "--"}
          </span>
          {hoverCoord?.psdX !== undefined && (
            <span className="text-[#22D3EE] tabular-nums" title="dB re px²/Hz">
              PSD X:{" "}
              {useLogScale
                ? `${(10 * Math.log10(Math.max(hoverCoord.psdX, 1e-12))).toFixed(1)} dB`
                : hoverCoord.psdX.toExponential(2)}
            </span>
          )}
          {hoverCoord?.psdY !== undefined && (
            <span className="text-[#F59E0B] tabular-nums" title="dB re px²/Hz">
              PSD Y:{" "}
              {useLogScale
                ? `${(10 * Math.log10(Math.max(hoverCoord.psdY, 1e-12))).toFixed(1)} dB`
                : hoverCoord.psdY.toExponential(2)}
            </span>
          )}
        </div>

        <div className="flex items-center gap-3 text-[11px] text-slate-400">
          <span>Nyquist: {nyquistHz != null ? `${nyquistHz.toFixed(1)} Hz` : "--"}</span>
          <span>Usable Band: 0.5–{usableMaxHz != null ? `${usableMaxHz.toFixed(1)} Hz` : "--"}</span>
        </div>
      </div>
    </div>
  );
};
