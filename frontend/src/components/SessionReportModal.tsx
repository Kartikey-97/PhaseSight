"use client";

import React from "react";
import type { SessionReport } from "@/lib/types";
import {
  X,
  FileCheck,
  ShieldCheck,
  AlertTriangle,
  Info,
  Clock,
  Activity,
  CheckCircle2,
  Download,
} from "lucide-react";

interface SessionReportModalProps {
  report: SessionReport | null;
  onClose: () => void;
}

export const SessionReportModal: React.FC<SessionReportModalProps> = ({
  report,
  onClose,
}) => {
  if (!report) return null;

  const rep = (report as any).report || report;
  const xMetrics = rep.x_metrics || rep.x_axis;
  const yMetrics = rep.y_metrics || rep.y_axis;
  const baseline = rep.baseline_assessment;
  const timing = rep.temporal_stability;
  const measuredFps = Number(rep.measured_fps || rep.fps_used || 30.0);
  const framesAnalysed = Number(rep.frames_analysed || rep.frame_count || 0);
  const durationS = Number(rep.duration_s || 0.0);
  const timebaseSource =
    rep.timebase_source ||
    rep.timestamp_source ||
    rep.temporal_stability?.timebase_source ||
    "measured";

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="relative w-full max-w-4xl max-h-[90vh] overflow-y-auto bg-[#0D121A] border border-[rgba(255,255,255,0.12)] rounded-lg shadow-2xl p-6 flex flex-col gap-5 text-slate-100">
        {/* Header */}
        <div className="flex items-start justify-between border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 bg-[#22D3EE]/10 border border-[#22D3EE]/30 rounded-lg text-[#22D3EE]">
              <FileCheck className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold font-display tracking-tight text-white">
                  INSPECTION RUN REPORT
                </h2>
                <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-white/5 border border-white/10 text-slate-300">
                  {rep.source_type || "continuous_monitoring"}
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">
                Run ID: <span className="text-slate-200">{report.run_id || rep.run_id || "Unsaved"}</span> · Session:{" "}
                <span className="text-slate-200">{report.session_id || rep.session_id}</span>
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Executive summary banner */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
          <div className="p-3 bg-[#131B26] border border-white/5 rounded">
            <span className="text-slate-400 text-[10px] block">DURATION</span>
            <span className="text-base font-bold text-white tabular-nums">
              {durationS.toFixed(2)} s
            </span>
          </div>
          <div className="p-3 bg-[#131B26] border border-white/5 rounded">
            <span className="text-slate-400 text-[10px] block">FRAMES ANALYSED</span>
            <span className="text-base font-bold text-white tabular-nums">
              {framesAnalysed.toLocaleString()}
            </span>
          </div>
          <div className="p-3 bg-[#131B26] border border-white/5 rounded">
            <span className="text-slate-400 text-[10px] block">MEASURED FPS</span>
            <span className="text-base font-bold text-[#22D3EE] tabular-nums">
              {measuredFps.toFixed(1)} Hz
            </span>
          </div>
          <div className="p-3 bg-[#131B26] border border-white/5 rounded">
            <span className="text-slate-400 text-[10px] block">TIMEBASE SOURCE</span>
            <span className="text-sm font-semibold text-slate-200 truncate block">
              {timebaseSource}
            </span>
          </div>
        </div>

        {/* Axis Metrics Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* X Axis Card */}
          <div className="p-4 bg-[#131B26] border border-[#22D3EE]/30 rounded-lg flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-[#22D3EE] font-mono tracking-wider">
                X-AXIS (HORIZONTAL)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                  xMetrics?.signal_quality === "VALID"
                    ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                    : xMetrics?.signal_quality === "CONTAMINATED"
                    ? "bg-rose-950/40 text-rose-400 border-rose-800"
                    : "bg-amber-950/40 text-amber-400 border-amber-800"
                }`}
              >
                {xMetrics?.signal_quality || "NO SIGNAL"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div>
                <span className="text-[10px] text-slate-400 block">DOMINANT FREQ</span>
                <span className="text-lg font-bold text-white tabular-nums">
                  {xMetrics?.dominant_frequency_hz ? `${xMetrics.dominant_frequency_hz.toFixed(2)} Hz` : "--"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block">RMS DISPLACEMENT</span>
                <span className="text-lg font-bold text-white tabular-nums">
                  {xMetrics?.rms_displacement_px ? `${xMetrics.rms_displacement_px.toFixed(4)} px` : "--"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block">PEAK PROMINENCE</span>
                <span className="text-sm font-semibold text-slate-200 tabular-nums">
                  {xMetrics?.peak_to_median_db ? `${xMetrics.peak_to_median_db.toFixed(1)} dB` : "--"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block">2X HARMONIC RATIO</span>
                <span className="text-sm font-semibold text-slate-200 tabular-nums">
                  {xMetrics?.second_harmonic_ratio !== undefined && xMetrics?.second_harmonic_ratio !== null
                    ? `${(xMetrics.second_harmonic_ratio * 100).toFixed(1)}%`
                    : "None"}
                </span>
              </div>
            </div>
          </div>

          {/* Y Axis Card */}
          <div className="p-4 bg-[#131B26] border border-[#F59E0B]/30 rounded-lg flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-[#F59E0B] font-mono tracking-wider">
                Y-AXIS (VERTICAL)
              </span>
              <span
                className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${
                  yMetrics?.signal_quality === "VALID"
                    ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                    : yMetrics?.signal_quality === "CONTAMINATED"
                    ? "bg-rose-950/40 text-rose-400 border-rose-800"
                    : "bg-amber-950/40 text-amber-400 border-amber-800"
                }`}
              >
                {yMetrics?.signal_quality || "NO SIGNAL"}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              <div>
                <span className="text-[10px] text-slate-400 block">DOMINANT FREQ</span>
                <span className="text-lg font-bold text-white tabular-nums">
                  {yMetrics?.dominant_frequency_hz ? `${yMetrics.dominant_frequency_hz.toFixed(2)} Hz` : "--"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block">RMS DISPLACEMENT</span>
                <span className="text-lg font-bold text-white tabular-nums">
                  {yMetrics?.rms_displacement_px ? `${yMetrics.rms_displacement_px.toFixed(4)} px` : "--"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block">PEAK PROMINENCE</span>
                <span className="text-sm font-semibold text-slate-200 tabular-nums">
                  {yMetrics?.peak_to_median_db ? `${yMetrics.peak_to_median_db.toFixed(1)} dB` : "--"}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-400 block">2X HARMONIC RATIO</span>
                <span className="text-sm font-semibold text-slate-200 tabular-nums">
                  {yMetrics?.second_harmonic_ratio !== undefined && yMetrics?.second_harmonic_ratio !== null
                    ? `${(yMetrics.second_harmonic_ratio * 100).toFixed(1)}%`
                    : "None"}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Temporal stability audit */}
        {timing && (
          <div className="p-3 bg-[#131B26] border border-white/5 rounded text-xs flex items-center justify-between font-mono">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-slate-400" />
              <span className="text-slate-300">TEMPORAL INTEGRITY:</span>
              <span
                className={`font-semibold ${
                  timing.status === "STABLE"
                    ? "text-emerald-400"
                    : timing.status === "ASSUMED_UNIFORM"
                    ? "text-slate-300"
                    : "text-rose-400"
                }`}
              >
                {timing.status}
              </span>
            </div>
            <div className="flex items-center gap-4 text-slate-400 text-[11px]">
              {timing.status === "ASSUMED_UNIFORM" || timing.jitter_ratio == null ? (
                <span>Jitter: N/A (Synthesized)</span>
              ) : (
                <span>Jitter: {(timing.jitter_ratio * 100).toFixed(2)}%</span>
              )}
              {timing.dropped_frames_count !== undefined &&
                timing.dropped_frames_count !== null && (
                  <span>Dropped: {timing.dropped_frames_count}</span>
                )}
            </div>
          </div>
        )}

        {/* Baseline Assessment Card (if evaluated) */}
        {baseline && (
          <div
            className={`p-4 rounded-lg border font-mono text-xs flex flex-col gap-2 ${
              baseline.overall_status === "NORMAL"
                ? "bg-emerald-950/20 border-emerald-800 text-emerald-300"
                : baseline.overall_status === "REVIEW"
                ? "bg-rose-950/20 border-rose-800 text-rose-300"
                : "bg-amber-950/20 border-amber-800 text-amber-300"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className="font-bold flex items-center gap-2 text-sm">
                {baseline.overall_status === "NORMAL" ? (
                  <CheckCircle2 className="w-4 h-4" />
                ) : (
                  <AlertTriangle className="w-4 h-4" />
                )}
                BASELINE ASSESSMENT: {baseline.overall_status}
              </span>
              <span>Max |Z| = {baseline.max_z_score.toFixed(2)}</span>
            </div>
            {baseline.triggered_features?.length > 0 && (
              <div className="text-[11px]">
                <span className="font-semibold">Triggered Deviations: </span>
                {baseline.triggered_features.join(", ")}
              </div>
            )}
          </div>
        )}

        {/* Scientific disclosure footer */}
        <div className="p-3 bg-black/40 border border-white/5 rounded text-[11px] text-slate-400 flex items-start gap-2.5">
          <Info className="w-4 h-4 text-[#22D3EE] shrink-0 mt-0.5" />
          <div className="flex flex-col gap-0.5">
            <span className="font-semibold text-slate-300">
              SCIENTIFIC DISCLOSURE & MEASUREMENT SCOPE
            </span>
            <p className="leading-relaxed">
              Displacements are computed in relative image pixels (px) using sub-pixel phase correlation against reference ROI templates. Results serve optical screening purposes and indicate relative modal vibration frequencies, not calibrated absolute physical engineering units (mm/s or g).
            </p>
          </div>
        </div>

        {/* Footer actions */}
        <div className="flex items-center justify-end gap-3 pt-2 border-t border-white/10">
          <button
            type="button"
            data-testid="btn-export-report-json"
            onClick={() => {
              const runId = report.run_id || rep.run_id || report.session_id || "session";
              const exportPayload = {
                run_id: report.run_id || rep.run_id || null,
                session_id: report.session_id || rep.session_id || null,
                asset_id: rep.asset_id || null,
                source_type: rep.source_type || "continuous_monitoring",
                duration_s: durationS,
                frames_analysed: framesAnalysed,
                measured_fps: measuredFps,
                timebase_source: timebaseSource,
                x_metrics: xMetrics || null,
                y_metrics: yMetrics || null,
                temporal_stability: timing || null,
                baseline_assessment: baseline || null,
                disclosures: rep.disclosures || null,
                summary: rep.summary || rep,
              };
              const blob = new Blob([JSON.stringify(exportPayload, null, 2)], {
                type: "application/json",
              });
              const url = URL.createObjectURL(blob);
              const link = document.createElement("a");
              link.href = url;
              link.download = `phasesight_${runId}_report.json`;
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
              URL.revokeObjectURL(url);
            }}
            className="flex items-center gap-1.5 px-4 py-2 bg-white/5 hover:bg-white/10 border border-white/15 text-slate-200 rounded font-mono text-xs font-semibold transition"
          >
            <Download className="w-3.5 h-3.5 text-[#22D3EE]" />
            Export Report JSON
          </button>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white rounded font-mono text-xs font-semibold transition"
          >
            Close Report
          </button>
        </div>
      </div>
    </div>
  );
};
