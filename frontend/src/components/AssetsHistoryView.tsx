"use client";

import React, { useState, useEffect, useCallback } from "react";
import type { Asset, BaselineSummary, RunItem } from "@/lib/types";
import { api } from "@/lib/api";
import { OscilloscopeCanvas } from "./OscilloscopeCanvas";
import { SpectrumPlot } from "./SpectrumPlot";
import {
  Layers,
  Plus,
  Trash2,
  CheckCircle2,
  Calendar,
  Activity,
  FileText,
  AlertTriangle,
  ChevronRight,
  Database,
  Sliders,
  X,
  Download,
} from "lucide-react";

interface AssetsHistoryViewProps {
  assets: Asset[];
  activeAsset: Asset | null;
  onSelectActiveAsset: (asset: Asset) => void;
  onRefreshAssets: () => void;
}

export const AssetsHistoryView: React.FC<AssetsHistoryViewProps> = ({
  assets,
  activeAsset,
  onSelectActiveAsset,
  onRefreshAssets,
}) => {
  // Active selected asset for detail panel
  const [selectedAssetId, setSelectedAssetId] = useState<string>(
    activeAsset?.asset_id || assets[0]?.asset_id || ""
  );

  // Asset runs & baselines
  const [runs, setRuns] = useState<RunItem[]>([]);
  const [selectedRunIds, setSelectedRunIds] = useState<string[]>([]);
  const [allowSingleAxis, setAllowSingleAxis] = useState<boolean>(false);
  const [baselineSummary, setBaselineSummary] = useState<BaselineSummary | null>(null);

  // Run history filter & drawer inspector
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [inspectedRun, setInspectedRun] = useState<any | null>(null);
  const [isLoadingRun, setIsLoadingRun] = useState<boolean>(false);
  const [overlayRunId, setOverlayRunId] = useState<string>("");
  const [overlayRunDetail, setOverlayRunDetail] = useState<any | null>(null);

  // Create asset modal
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [newAssetName, setNewAssetName] = useState<string>("");
  const [newNominalRpm, setNewNominalRpm] = useState<string>("1000");
  const [newExpectedFps, setNewExpectedFps] = useState<string>("60");

  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  // Current selected asset object
  const currentAsset = assets.find((a) => a.asset_id === selectedAssetId) || null;

  // Load runs and baselines when selectedAssetId changes
  const loadAssetData = useCallback(async () => {
    try {
      const runList = await api.getRuns(
        selectedAssetId ? { asset_id: selectedAssetId } : undefined
      );
      setRuns(runList);

      if (selectedAssetId) {
        const baselines = await api.getBaselines(selectedAssetId);
        if (baselines.length > 0) {
          setBaselineSummary(baselines[0]);
        } else {
          setBaselineSummary(null);
        }
      } else {
        setBaselineSummary(null);
      }
    } catch (err: any) {
      console.error("Failed to load asset runs/baselines:", err);
    }
  }, [selectedAssetId]);

  useEffect(() => {
    loadAssetData();
  }, [loadAssetData]);

  // Select first asset if available and none selected
  useEffect(() => {
    if (!selectedAssetId && assets.length > 0) {
      setSelectedAssetId(assets[0].asset_id);
    }
  }, [assets, selectedAssetId]);

  // Sync selectedAssetId if activeAsset prop updates
  useEffect(() => {
    if (activeAsset && activeAsset.asset_id !== selectedAssetId) {
      setSelectedAssetId(activeAsset.asset_id);
    }
  }, [activeAsset, selectedAssetId]);

  // Handle run selection for baseline building
  const toggleRunSelection = (runId: string) => {
    if (selectedRunIds.includes(runId)) {
      setSelectedRunIds(selectedRunIds.filter((id) => id !== runId));
    } else {
      setSelectedRunIds([...selectedRunIds, runId]);
    }
  };

  // Build baseline
  const handleBuildBaseline = async () => {
    if (!selectedAssetId || selectedRunIds.length < 3) return;
    try {
      setErrorMessage(null);
      setSuccessMessage(null);
      const reqAxes = allowSingleAxis ? ["x"] : ["x", "y"];
      const res = await api.buildBaseline({
        asset_id: selectedAssetId,
        run_ids: selectedRunIds,
        require_valid_axes: reqAxes,
      });
      setBaselineSummary(res);
      setSuccessMessage("Statistical baseline built successfully!");
      onRefreshAssets();
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to build baseline");
    }
  };

  // Create asset
  const handleCreateAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newAssetName.trim()) return;
    try {
      setErrorMessage(null);
      const asset = await api.createAsset({
        name: newAssetName.trim(),
        nominal_rpm: newNominalRpm ? Number(newNominalRpm) : null,
        expected_fps: newExpectedFps ? Number(newExpectedFps) : null,
        default_target_roi: { x: 360, y: 110, width: 160, height: 160 },
        default_anchor_roi: { x: 60, y: 100, width: 160, height: 160 },
      });
      setShowCreateModal(false);
      setNewAssetName("");
      onRefreshAssets();
      setSelectedAssetId(asset.asset_id);
      onSelectActiveAsset(asset);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to create asset");
    }
  };

  // Delete asset
  const handleDeleteAsset = async (assetId: string) => {
    if (!confirm("Are you sure you want to delete this asset and its baseline history?")) {
      return;
    }
    try {
      await api.deleteAsset(assetId);
      onRefreshAssets();
      if (assets.length > 1) {
        const next = assets.find((a) => a.asset_id !== assetId);
        if (next) setSelectedAssetId(next.asset_id);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to delete asset");
    }
  };

  // Fetch full run detail including NPZ arrays for drawer
  const inspectRunDetail = async (runId: string) => {
    try {
      setIsLoadingRun(true);
      const detail = await api.getRun(runId);
      setInspectedRun(detail);

      // Auto-select first baseline calibration run (excluding current run) if available
      const otherRuns = runs.filter((r) => r.run_id !== runId);
      const baselineIds = baselineSummary?.run_ids || [];
      const defaultRef =
        otherRuns.find((r) => baselineIds.includes(r.run_id)) ||
        otherRuns.find((r) => r.status.toUpperCase() === "NORMAL") ||
        otherRuns.find((r) => r.x_signal_quality === "VALID") ||
        null;
      setOverlayRunId(defaultRef ? defaultRef.run_id : "");
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load run detail");
    } finally {
      setIsLoadingRun(false);
    }
  };

  // Load overlay reference run arrays when selected
  useEffect(() => {
    let cancelled = false;
    if (!overlayRunId) {
      setOverlayRunDetail(null);
      return;
    }
    api
      .getRun(overlayRunId)
      .then((detail) => {
        if (!cancelled) setOverlayRunDetail(detail);
      })
      .catch(() => {
        if (!cancelled) setOverlayRunDetail(null);
      });
    return () => {
      cancelled = true;
    };
  }, [overlayRunId]);

  // Filter runs
  const filteredRuns = runs.filter((r) => {
    if (statusFilter === "all") return true;
    return r.status.toLowerCase() === statusFilter.toLowerCase();
  });

  return (
    <div className="flex flex-col gap-5">
      {/* Messages */}
      {errorMessage && (
        <div className="flex items-center justify-between p-3 bg-rose-950/40 border border-rose-800 rounded text-rose-300 text-xs font-mono">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-slate-400 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="flex items-center justify-between p-3 bg-emerald-950/40 border border-emerald-800 rounded text-emerald-300 text-xs font-mono">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" />
            <span>{successMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setSuccessMessage(null)}
            className="text-slate-400 hover:text-white"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Top Asset Management & Selection Strip */}
      <div className="p-4 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <Database className="w-4 h-4 text-[#22D3EE]" />
            <h2 className="text-sm font-bold font-display text-white">
              MACHINE ASSETS & STATISTICAL BASELINES
            </h2>
          </div>

          <button
            type="button"
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-[#22D3EE] text-black font-semibold rounded font-mono text-xs hover:bg-[#22D3EE]/90 transition"
          >
            <Plus className="w-3.5 h-3.5" />
            New Machine Asset
          </button>
        </div>

        {/* Asset cards carousel / list */}
        <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
          {assets.map((asset) => {
            const isSelected = asset.asset_id === selectedAssetId;
            const isActive = activeAsset?.asset_id === asset.asset_id;

            return (
              <div
                key={asset.asset_id}
                onClick={() => setSelectedAssetId(asset.asset_id)}
                className={`p-3 rounded border cursor-pointer transition flex flex-col justify-between gap-2 ${
                  isSelected
                    ? "bg-[#131B26] border-[#22D3EE] shadow-md shadow-[#22D3EE]/10"
                    : "bg-[#070A0F] border-white/10 hover:border-white/20"
                }`}
              >
                <div>
                  <div className="flex items-center justify-between">
                    <span className="font-semibold text-white text-xs truncate">
                      {asset.name}
                    </span>
                    {isActive && (
                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-emerald-950/60 text-emerald-400 border border-emerald-800">
                        ACTIVE
                      </span>
                    )}
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono block mt-0.5">
                    ID: {asset.asset_id}
                  </span>
                </div>

                <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 border-t border-white/5 pt-1.5">
                  <span>{asset.run_count || 0} Runs</span>
                  <span>{asset.baseline_count || 0} Baselines</span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectActiveAsset(asset);
                    }}
                    className="text-[#22D3EE] hover:underline"
                  >
                    Select
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Main Grid: Baseline Calibration Builder (Left) & Run History (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* ============================================================== */}
        {/* LEFT COLUMN: Median / MAD Baseline Builder (6 Cols)            */}
        {/* ============================================================== */}
        <div className="lg:col-span-6 flex flex-col gap-4">
          <div className="p-4 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
              <div>
                <h3 className="text-xs font-bold font-display text-white">
                  MEDIAN / SCALED MAD BASELINE BUILDER
                </h3>
                <span className="text-[11px] text-slate-400 font-mono">
                  Asset: {currentAsset?.name}
                </span>
              </div>

              {currentAsset && (
                <button
                  type="button"
                  onClick={() => handleDeleteAsset(currentAsset.asset_id)}
                  className="p-1 rounded text-slate-500 hover:text-rose-400 transition"
                  title="Delete asset"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>

            {/* Existing Baseline Summary Card */}
            {baselineSummary ? (
              <div className="p-3 bg-[#131B26] border border-emerald-900/60 rounded flex flex-col gap-2 font-mono text-xs">
                <div className="flex items-center justify-between text-emerald-400 font-semibold">
                  <span className="flex items-center gap-1.5">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    ACTIVE BASELINE ({baselineSummary.run_ids.length} RUNS)
                  </span>
                  <span className="text-[10px] text-slate-400">
                    ID: {baselineSummary.baseline_id.slice(0, 8)}...
                  </span>
                </div>

                {/* Median / MAD Table */}
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[11px]">
                    <thead>
                      <tr className="text-slate-400 border-b border-white/5">
                        <th className="py-1">Feature</th>
                        <th className="py-1 text-[#22D3EE]">X Median (MAD)</th>
                        <th className="py-1 text-[#F59E0B]">Y Median (MAD)</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-white/5">
                      <tr>
                        <td className="py-1 text-slate-400">Dominant Freq</td>
                        <td className="py-1 text-slate-200 tabular-nums">
                          {baselineSummary.x_baseline?.dominant_frequency_hz_median != null
                            ? `${baselineSummary.x_baseline.dominant_frequency_hz_median.toFixed(2)} Hz (±${(baselineSummary.x_baseline.dominant_frequency_hz_mad ?? 0).toFixed(2)})`
                            : "--"}
                        </td>
                        <td className="py-1 text-slate-200 tabular-nums">
                          {baselineSummary.y_baseline?.dominant_frequency_hz_median != null
                            ? `${baselineSummary.y_baseline.dominant_frequency_hz_median.toFixed(2)} Hz (±${(baselineSummary.y_baseline.dominant_frequency_hz_mad ?? 0).toFixed(2)})`
                            : "--"}
                        </td>
                      </tr>
                      <tr>
                        <td className="py-1 text-slate-400">RMS Displacement</td>
                        <td className="py-1 text-slate-200 tabular-nums">
                          {baselineSummary.x_baseline?.rms_displacement_px_median != null
                            ? `${baselineSummary.x_baseline.rms_displacement_px_median.toFixed(4)} px (±${(baselineSummary.x_baseline.rms_displacement_px_mad ?? 0).toFixed(4)})`
                            : "--"}
                        </td>
                        <td className="py-1 text-slate-200 tabular-nums">
                          {baselineSummary.y_baseline?.rms_displacement_px_median != null
                            ? `${baselineSummary.y_baseline.rms_displacement_px_median.toFixed(4)} px (±${(baselineSummary.y_baseline.rms_displacement_px_mad ?? 0).toFixed(4)})`
                            : "--"}
                        </td>
                      </tr>
                      <tr>
                        <td className="py-1 text-slate-400">Prominence (dB)</td>
                        <td className="py-1 text-slate-200 tabular-nums">
                          {baselineSummary.x_baseline?.peak_to_median_db_median != null
                            ? `${baselineSummary.x_baseline.peak_to_median_db_median.toFixed(1)} dB (±${(baselineSummary.x_baseline.peak_to_median_db_mad ?? 0).toFixed(1)})`
                            : "--"}
                        </td>
                        <td className="py-1 text-slate-200 tabular-nums">
                          {baselineSummary.y_baseline?.peak_to_median_db_median != null
                            ? `${baselineSummary.y_baseline.peak_to_median_db_median.toFixed(1)} dB (±${(baselineSummary.y_baseline.peak_to_median_db_mad ?? 0).toFixed(1)})`
                            : "--"}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>
            ) : (
              <div className="p-3 bg-amber-950/20 border border-amber-800/40 rounded text-amber-300 font-mono text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0" />
                <span>No statistical baseline established for this asset. Select ≥ 3 runs below to build one.</span>
              </div>
            )}

            {/* Run Selection Checklist */}
            <div className="flex flex-col gap-2 font-mono text-xs">
              <div className="flex items-center justify-between text-slate-400 text-[11px]">
                <span>SELECT ≥ 3 ELIGIBLE CALIBRATION RUNS</span>
                <span>{selectedRunIds.length} selected</span>
              </div>

              <div className="max-h-56 overflow-y-auto flex flex-col gap-1.5 border border-white/5 rounded p-2 bg-[#070A0F]">
                {runs.length === 0 ? (
                  <span className="text-slate-500 text-center py-4 text-xs">
                    No runs recorded for this asset yet.
                  </span>
                ) : (
                  runs.map((r) => {
                    const rXFreq =
                      r.x_frequency_hz ??
                      r.x_dominant_frequency_hz ??
                      r.summary?.x_axis?.dominant_frequency_hz;
                    const rMode =
                      r.mode ||
                      (r.summary?.session_mode === "continuous_monitoring"
                        ? "LIVE"
                        : "BATCH");

                    return (
                      <label
                        key={r.run_id}
                        className="flex items-center justify-between p-2 rounded bg-[#131B26] hover:bg-[#1A2433] cursor-pointer transition border border-white/5 text-[11px]"
                      >
                        <div className="flex items-center gap-2">
                          <input
                            type="checkbox"
                            checked={selectedRunIds.includes(r.run_id)}
                            onChange={() => toggleRunSelection(r.run_id)}
                            className="rounded bg-slate-800"
                          />
                          <span className="text-white font-semibold">
                            {r.run_id.slice(0, 8)}...
                          </span>
                          <span className="text-slate-400 text-[10px]">
                            ({rMode})
                          </span>
                        </div>

                        <div className="flex items-center gap-3 text-slate-300">
                          <span>{(r.duration_s ?? 0).toFixed(1)}s</span>
                          <span className="text-[#22D3EE] tabular-nums">
                            {typeof rXFreq === "number" && !isNaN(rXFreq)
                              ? `${rXFreq.toFixed(2)} Hz`
                              : "--"}
                          </span>
                          <span
                            className={`px-1 rounded text-[9px] ${
                              r.status === "NORMAL"
                                ? "bg-emerald-950 text-emerald-400"
                                : "bg-slate-800 text-slate-400"
                            }`}
                          >
                            {r.status}
                          </span>
                        </div>
                      </label>
                    );
                  })
                )}
              </div>

              {/* Single axis toggle & build button */}
              <div className="flex items-center justify-between pt-2">
                <label className="flex items-center gap-2 text-[11px] text-slate-400 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={allowSingleAxis}
                    onChange={(e) => setAllowSingleAxis(e.target.checked)}
                    className="rounded bg-slate-800"
                  />
                  <span>Allow single-axis baseline (1D synthetic rigs)</span>
                </label>

                <button
                  type="button"
                  disabled={selectedRunIds.length < 3}
                  onClick={handleBuildBaseline}
                  className="px-4 py-2 bg-[#22D3EE] hover:bg-[#22D3EE]/90 text-black font-semibold rounded font-mono text-xs transition disabled:opacity-40"
                >
                  Build Baseline ({selectedRunIds.length}/3)
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* ============================================================== */}
        {/* RIGHT COLUMN: Inspection & Session History Table (6 Cols)      */}
        {/* ============================================================== */}
        <div className="lg:col-span-6 flex flex-col gap-4">
          <div className="p-4 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
              <h3 className="text-xs font-bold font-display text-white">
                INSPECTION RUNS & SESSION HISTORY
              </h3>

              {/* Filter pills */}
              <div className="flex items-center gap-1 font-mono text-[10px]">
                {(["all", "normal", "review", "low_confidence"] as const).map(
                  (f) => (
                    <button
                      key={f}
                      type="button"
                      onClick={() => setStatusFilter(f)}
                      className={`px-2 py-0.5 rounded transition ${
                        statusFilter === f
                          ? "bg-slate-700 text-white"
                          : "text-slate-400 hover:text-white"
                      }`}
                    >
                      {f.toUpperCase()}
                    </button>
                  )
                )}
              </div>
            </div>

            {/* Run table */}
            <div className="overflow-x-auto max-h-[380px] overflow-y-auto">
              <table className="w-full text-left font-mono text-xs">
                <thead>
                  <tr className="text-slate-400 border-b border-white/10 text-[10px]">
                    <th className="py-1.5 px-2">Run ID</th>
                    <th className="py-1.5 px-2">Mode</th>
                    <th className="py-1.5 px-2">Duration</th>
                    <th className="py-1.5 px-2 text-[#22D3EE]">X Peak</th>
                    <th className="py-1.5 px-2 text-[#F59E0B]">Y Peak</th>
                    <th className="py-1.5 px-2">Status</th>
                    <th className="py-1.5 px-2"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/5">
                  {filteredRuns.length === 0 ? (
                    <tr>
                      <td
                        colSpan={7}
                        className="py-6 text-center text-slate-500 text-xs"
                      >
                        No matching runs found
                      </td>
                    </tr>
                  ) : (
                    filteredRuns.map((run) => {
                      const xFreq =
                        run.x_frequency_hz ??
                        run.x_dominant_frequency_hz ??
                        run.summary?.x_axis?.dominant_frequency_hz;
                      const yFreq =
                        run.y_frequency_hz ??
                        run.y_dominant_frequency_hz ??
                        run.summary?.y_axis?.dominant_frequency_hz;
                      const modeLabel =
                        run.mode ||
                        (run.summary?.session_mode === "continuous_monitoring"
                          ? "LIVE"
                          : "BATCH");

                      return (
                        <tr
                          key={run.run_id}
                          data-testid="run-row"
                          onClick={() => inspectRunDetail(run.run_id)}
                          className="hover:bg-white/5 cursor-pointer transition text-[11px]"
                        >
                          <td className="py-2 px-2 text-white font-semibold">
                            {run.run_id.slice(0, 8)}...
                          </td>
                          <td className="py-2 px-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
                                modeLabel === "LIVE"
                                  ? "bg-cyan-950/50 text-[#22D3EE] border-[#22D3EE]/40"
                                  : "bg-purple-950/50 text-purple-300 border-purple-800/40"
                              }`}
                            >
                              {modeLabel}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-slate-300 tabular-nums">
                            {(run.duration_s ?? 0).toFixed(1)}s
                          </td>
                          <td className="py-2 px-2 text-[#22D3EE] tabular-nums font-mono">
                            {typeof xFreq === "number" && !isNaN(xFreq)
                              ? `${xFreq.toFixed(2)} Hz`
                              : "--"}
                          </td>
                          <td className="py-2 px-2 text-[#F59E0B] tabular-nums font-mono">
                            {typeof yFreq === "number" && !isNaN(yFreq)
                              ? `${yFreq.toFixed(2)} Hz`
                              : "--"}
                          </td>
                          <td className="py-2 px-2">
                            <span
                              className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
                                run.status === "NORMAL"
                                  ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                                  : run.status === "REVIEW"
                                  ? "bg-rose-950/40 text-rose-400 border-rose-800"
                                  : "bg-slate-800 text-slate-400 border-white/10"
                              }`}
                            >
                              {run.status}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-slate-400">
                            <ChevronRight className="w-3.5 h-3.5" />
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>

      {/* Run Detail Inspection Drawer / Modal */}
      {inspectedRun && (
        <div className="p-5 bg-[#0D121A] border border-[rgba(255,255,255,0.12)] rounded-lg flex flex-col gap-4 animate-in fade-in duration-200">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/10 pb-3">
            <div className="flex items-center gap-2 font-mono">
              <FileText className="w-4 h-4 text-[#22D3EE]" />
              <span className="font-bold text-white text-sm">
                INSPECTOR: RUN {inspectedRun.run_id}
              </span>
              <span className="text-xs text-slate-400">
                ({inspectedRun.mode} · {(inspectedRun.duration_s ?? 0).toFixed(2)}s · {(inspectedRun.measured_fps ?? 0).toFixed(1)} FPS)
              </span>
            </div>
            <div className="flex flex-wrap items-center gap-2.5">
              {/* Overlay Reference Run Dropdown */}
              <div className="flex items-center gap-1.5 font-mono text-xs">
                <label
                  htmlFor="overlayRunSelect"
                  className="text-[10px] text-slate-400 uppercase tracking-wider"
                >
                  Overlay Reference Run:
                </label>
                <select
                  id="overlayRunSelect"
                  data-testid="select-overlay-run"
                  value={overlayRunId}
                  onChange={(e) => setOverlayRunId(e.target.value)}
                  className="bg-[#131B26] border border-emerald-700/50 rounded px-2 py-1 text-emerald-300 text-xs max-w-[240px]"
                >
                  <option value="">None</option>
                  {runs
                    .filter((r) => r.run_id !== inspectedRun.run_id)
                    .map((r) => {
                      const isBsl = baselineSummary?.run_ids?.includes(r.run_id);
                      const xf =
                        r.x_dominant_frequency_hz ?? r.x_frequency_hz ?? null;
                      return (
                        <option key={r.run_id} value={r.run_id}>
                          {isBsl ? "[BASELINE] " : ""}
                          {r.run_id.slice(0, 14)} ·{" "}
                          {xf != null ? `${xf.toFixed(2)} Hz` : r.status}
                        </option>
                      );
                    })}
                </select>
              </div>

              <button
                type="button"
                data-testid="btn-export-inspector-json"
                onClick={() => {
                  const runId = inspectedRun.run_id || "run";
                  const exportPayload = {
                    run_id: inspectedRun.run_id,
                    asset_id: inspectedRun.asset_id,
                    mode: inspectedRun.mode,
                    timestamp: inspectedRun.timestamp,
                    duration_s: inspectedRun.duration_s,
                    frames_analysed: inspectedRun.frames_analysed,
                    measured_fps: inspectedRun.measured_fps,
                    status: inspectedRun.status,
                    x_metrics:
                      inspectedRun.x_metrics ??
                      inspectedRun.summary?.x_axis ??
                      null,
                    y_metrics:
                      inspectedRun.y_metrics ??
                      inspectedRun.summary?.y_axis ??
                      null,
                    temporal_stability:
                      inspectedRun.summary?.temporal_stability ?? null,
                    baseline_assessment:
                      inspectedRun.baseline_assessment ??
                      inspectedRun.summary?.baseline_assessment ??
                      null,
                    summary: inspectedRun.summary ?? null,
                  };
                  const blob = new Blob(
                    [JSON.stringify(exportPayload, null, 2)],
                    { type: "application/json" }
                  );
                  const url = URL.createObjectURL(blob);
                  const link = document.createElement("a");
                  link.href = url;
                  link.download = `phasesight_${runId}_report.json`;
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                  URL.revokeObjectURL(url);
                }}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/15 text-slate-200 rounded font-mono text-xs font-semibold transition"
              >
                <Download className="w-3.5 h-3.5 text-[#22D3EE]" />
                Export Report JSON
              </button>
              <button
                type="button"
                onClick={() => {
                  setInspectedRun(null);
                  setOverlayRunId("");
                  setOverlayRunDetail(null);
                }}
                className="p-1 rounded text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </div>

          {/* Charts if NPZ arrays present */}
          {inspectedRun.arrays && (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
              <OscilloscopeCanvas
                samples={(
                  inspectedRun.arrays.times_s ||
                  inspectedRun.arrays.timestamps_s ||
                  []
                ).map((t: number, i: number) => ({
                  t,
                  rel_dx_px: (
                    inspectedRun.arrays.rel_dx_px ||
                    inspectedRun.arrays.relative_dx_px ||
                    []
                  )[i] || 0,
                  rel_dy_px: (
                    inspectedRun.arrays.rel_dy_px ||
                    inspectedRun.arrays.relative_dy_px ||
                    []
                  )[i] || 0,
                  raw_target_dx: (inspectedRun.arrays.target_dx_px || [])[i],
                  raw_anchor_dx: (inspectedRun.arrays.anchor_dx_px || [])[i],
                }))}
                isStatic={true}
                correlationResponse={
                  inspectedRun.summary?.mean_target_response ??
                  inspectedRun.summary?.mean_min_phase_correlation_response ??
                  inspectedRun.summary?.mean_min_phase_response ??
                  null
                }
                anchorCorrelationResponse={
                  inspectedRun.summary?.mean_anchor_response ??
                  inspectedRun.summary?.mean_min_phase_correlation_response ??
                  inspectedRun.summary?.mean_min_phase_response ??
                  null
                }
                height={200}
              />
              <SpectrumPlot
                xMetrics={
                  inspectedRun.x_metrics
                    ? {
                        ...inspectedRun.x_metrics,
                        frequencies:
                          inspectedRun.x_metrics.frequencies ||
                          inspectedRun.arrays.x_frequencies_hz,
                        psd:
                          inspectedRun.x_metrics.psd ||
                          inspectedRun.arrays.x_psd_px2_per_hz,
                      }
                    : null
                }
                yMetrics={
                  inspectedRun.y_metrics
                    ? {
                        ...inspectedRun.y_metrics,
                        frequencies:
                          inspectedRun.y_metrics.frequencies ||
                          inspectedRun.arrays.y_frequencies_hz,
                        psd:
                          inspectedRun.y_metrics.psd ||
                          inspectedRun.arrays.y_psd_px2_per_hz,
                      }
                    : null
                }
                baselineFreqHz={
                  baselineSummary?.x_baseline?.dominant_frequency_hz_median ?? null
                }
                overlayFrequenciesHz={
                  overlayRunDetail?.x_metrics?.frequencies ??
                  overlayRunDetail?.arrays?.x_frequencies_hz
                }
                overlayPsd={
                  overlayRunDetail?.x_metrics?.psd ??
                  overlayRunDetail?.arrays?.x_psd_px2_per_hz
                }
                overlayLabel={
                  overlayRunDetail
                    ? baselineSummary?.run_ids?.includes(overlayRunDetail.run_id)
                      ? `Baseline (${overlayRunDetail.run_id.slice(0, 12)})`
                      : overlayRunDetail.run_id
                    : undefined
                }
                height={200}
              />
            </div>
          )}

          {/* JSON Summary Dump */}
          <details className="text-xs font-mono bg-[#070A0F] border border-white/10 rounded p-3 text-slate-300">
            <summary className="cursor-pointer text-slate-400 hover:text-white select-none">
              View Complete Raw JSON Metadata
            </summary>
            <pre className="mt-2 text-[10px] overflow-x-auto text-slate-400">
              {JSON.stringify(inspectedRun, null, 2)}
            </pre>
          </details>
        </div>
      )}

      {/* Create Machine Asset Modal */}
      {showCreateModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
          <form
            onSubmit={handleCreateAsset}
            className="w-full max-w-md bg-[#0D121A] border border-white/10 rounded-lg p-5 flex flex-col gap-4 text-slate-100"
          >
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <span className="text-sm font-bold font-display">
                CREATE NEW MACHINE ASSET
              </span>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex flex-col gap-3 font-mono text-xs">
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">
                  ASSET NAME *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Pump Bearings Unit 4"
                  value={newAssetName}
                  onChange={(e) => setNewAssetName(e.target.value)}
                  className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1.5 text-white"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">
                    NOMINAL RPM
                  </label>
                  <input
                    type="number"
                    placeholder="1000"
                    value={newNominalRpm}
                    onChange={(e) => setNewNominalRpm(e.target.value)}
                    className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1.5 text-white"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-400 block mb-1">
                    EXPECTED FPS
                  </label>
                  <input
                    type="number"
                    placeholder="60"
                    value={newExpectedFps}
                    onChange={(e) => setNewExpectedFps(e.target.value)}
                    className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1.5 text-white"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-white/10">
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="px-3 py-1.5 rounded font-mono text-xs text-slate-400 hover:bg-white/5"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-1.5 bg-[#22D3EE] text-black font-semibold rounded font-mono text-xs hover:bg-[#22D3EE]/90"
              >
                Create Asset
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
};
