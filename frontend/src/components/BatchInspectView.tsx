"use client";

import React, { useState, useEffect, useCallback } from "react";
import type { Asset, Preset, ROI, VideoPreview } from "@/lib/types";
import { api } from "@/lib/api";
import { RoiInteractiveCanvas } from "./RoiInteractiveCanvas";
import { OscilloscopeCanvas } from "./OscilloscopeCanvas";
import { SpectrumPlot } from "./SpectrumPlot";
import {
  Upload,
  Play,
  Film,
  AlertTriangle,
  Clock,
  ShieldCheck,
  CheckCircle2,
  FileCheck,
  Sliders,
  Loader2,
} from "lucide-react";

interface BatchInspectViewProps {
  assets: Asset[];
  activeAsset: Asset | null;
}

export const BatchInspectView: React.FC<BatchInspectViewProps> = ({
  assets,
  activeAsset,
}) => {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>("portable_baseline");
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [selectedAssetId, setSelectedAssetId] = useState<string>(activeAsset?.asset_id || "");

  const [previewData, setPreviewData] = useState<VideoPreview | null>(null);
  const [targetRoi, setTargetRoi] = useState<ROI>({ x: 360, y: 110, width: 160, height: 160 });
  const [anchorRoi, setAnchorRoi] = useState<ROI>({ x: 60, y: 100, width: 160, height: 160 });
  const [fpsOverride, setFpsOverride] = useState<number | null>(null);
  const [nperseg, setNperseg] = useState<number>(256);

  const [isAnalyzing, setIsAnalyzing] = useState<boolean>(false);
  const [analysisResult, setAnalysisResult] = useState<any | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Sync activeAsset
  useEffect(() => {
    if (activeAsset?.asset_id) setSelectedAssetId(activeAsset.asset_id);
  }, [activeAsset]);

  // Load presets on mount
  useEffect(() => {
    api
      .getPresets()
      .then((data) => {
        setPresets(data);
        if (data.length > 0 && !selectedPresetId) {
          setSelectedPresetId(data[0].preset_id);
        }
      })
      .catch((err) => console.error("Error loading presets:", err));
  }, []);

  // Load video preview
  const loadPreview = useCallback(async (presetId?: string, file?: File) => {
    try {
      setErrorMessage(null);
      const res = await api.getPreview({ preset_id: presetId, file });
      setPreviewData(res);

      if (presetId) {
        const curPreset = presets.find((p) => p.preset_id === presetId);
        if (curPreset) {
          if (curPreset.default_target_roi) setTargetRoi(curPreset.default_target_roi);
          if (curPreset.default_anchor_roi) setAnchorRoi(curPreset.default_anchor_roi);
          if (curPreset.recommended_fps_override) {
            setFpsOverride(curPreset.recommended_fps_override);
          } else {
            setFpsOverride(null);
          }
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load preview");
    }
  }, [presets]);

  useEffect(() => {
    if (!uploadedFile && selectedPresetId) {
      loadPreview(selectedPresetId);
    }
  }, [selectedPresetId, uploadedFile, loadPreview]);

  // File upload handler
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      try {
        setIsUploading(true);
        setErrorMessage(null);
        setUploadedFile(file);

        const res = await api.getPreview({ file });
        setPreviewData(res);
        setSelectedPresetId("");

        // Auto-clamp / initialize targetRoi and anchorRoi inside actual dimensions
        const fw = res.frame_width || res.width || 1280;
        const fh = res.frame_height || res.height || 720;
        const roiSize = fw < 400 || fh < 400 ? 64 : 96;
        const cy = Math.max(10, Math.floor((fh - roiSize) / 2));
        const ancX = Math.max(10, Math.floor(fw * 0.2 - roiSize / 2));
        const tgtX = Math.min(
          fw - roiSize - 10,
          Math.max(ancX + roiSize + 20, Math.floor(fw * 0.6 - roiSize / 2))
        );
        setAnchorRoi({ x: ancX, y: cy, width: roiSize, height: roiSize });
        setTargetRoi({ x: tgtX, y: cy, width: roiSize, height: roiSize });

        if (res.recommended_fps_override) {
          setFpsOverride(res.recommended_fps_override);
        } else {
          setFpsOverride(null);
        }
      } catch (err: any) {
        setErrorMessage(err.message || "Failed to upload and decode video preview");
      } finally {
        setIsUploading(false);
      }
    }
  };

  // Run offline batch analysis
  const handleAnalyze = async () => {
    try {
      setIsAnalyzing(true);
      setErrorMessage(null);
      setAnalysisResult(null);

      const res = await api.analyzeRun({
        file: undefined,
        preset_id: uploadedFile ? undefined : (selectedPresetId || undefined),
        upload_id: uploadedFile ? (previewData?.upload_id || undefined) : undefined,
        target_roi: targetRoi,
        anchor_roi: anchorRoi,
        asset_id: selectedAssetId || null,
        fps_override: fpsOverride,
        nperseg,
      });

      setAnalysisResult(res);
    } catch (err: any) {
      setErrorMessage(err.message || "Analysis failed");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const curPreset = presets.find((p) => p.preset_id === selectedPresetId);

  // Convert analysis result arrays to Oscilloscope samples format
  const traceSamples = React.useMemo(() => {
    const t = analysisResult?.arrays?.times_s || analysisResult?.arrays?.timestamps_s;
    const dx = analysisResult?.arrays?.rel_dx_px || analysisResult?.arrays?.relative_dx_px;
    const dy = analysisResult?.arrays?.rel_dy_px || analysisResult?.arrays?.relative_dy_px;
    if (!t || !dx || !dy) return [];
    const samples = [];
    for (let i = 0; i < t.length; i++) {
      samples.push({
        t: t[i],
        rel_dx_px: dx[i],
        rel_dy_px: dy[i],
      });
    }
    return samples;
  }, [analysisResult]);

  const plotXMetrics = React.useMemo(() => {
    const xm = analysisResult?.x_metrics || analysisResult?.summary?.x_axis;
    if (!xm) return null;
    return {
      ...xm,
      frequencies: xm.frequencies || analysisResult?.arrays?.x_frequencies_hz,
      psd: xm.psd || analysisResult?.arrays?.x_psd_px2_per_hz,
    };
  }, [analysisResult]);

  const plotYMetrics = React.useMemo(() => {
    const ym = analysisResult?.y_metrics || analysisResult?.summary?.y_axis;
    if (!ym) return null;
    return {
      ...ym,
      frequencies: ym.frequencies || analysisResult?.arrays?.y_frequencies_hz,
      psd: ym.psd || analysisResult?.arrays?.y_psd_px2_per_hz,
    };
  }, [analysisResult]);

  return (
    <div className="flex flex-col gap-5">
      {/* Error banner */}
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

      {/* Top Configuration Bar */}
      <div className="p-4 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-white/5 pb-3">
          <div className="flex items-center gap-2">
            <Film className="w-4 h-4 text-[#22D3EE]" />
            <h2 className="text-sm font-bold font-display text-white">
              OFFLINE VIDEO BATCH & BENCHMARK INSPECTOR
            </h2>
          </div>
          <span className="text-xs text-slate-400 font-mono">
            High-speed optical inspection on recorded datasets
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs font-mono">
          {/* Preset Selector */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">
              BENCHMARK DATASET PRESET
            </label>
            <select
              disabled={isAnalyzing || uploadedFile !== null}
              value={selectedPresetId}
              onChange={(e) => setSelectedPresetId(e.target.value)}
              className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1.5 text-slate-200"
            >
              {presets.map((p) => (
                <option key={p.preset_id} value={p.preset_id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>

          {/* File Upload */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">
              OR UPLOAD CUSTOM VIDEO (.MP4, .AVI)
            </label>
            <div className="flex items-center gap-2">
              <label className="flex-1 flex items-center justify-center gap-2 px-3 py-1.5 bg-[#131B26] hover:bg-[#1A2433] border border-white/10 rounded cursor-pointer text-slate-300">
                <Upload className="w-3.5 h-3.5 text-[#22D3EE]" />
                <span className="truncate">
                  {uploadedFile ? uploadedFile.name : "Choose File"}
                </span>
                <input
                  type="file"
                  accept="video/*"
                  onChange={handleFileUpload}
                  className="hidden"
                />
              </label>
              {uploadedFile && (
                <button
                  type="button"
                  onClick={() => {
                    setUploadedFile(null);
                    loadPreview(selectedPresetId);
                  }}
                  className="px-2 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-slate-400"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Target Asset Link */}
          <div>
            <label className="text-[10px] text-slate-400 block mb-1">
              LINK TO MACHINE ASSET
            </label>
            <select
              value={selectedAssetId}
              onChange={(e) => setSelectedAssetId(e.target.value)}
              className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1.5 text-slate-200"
            >
              <option value="">None (Unassigned run)</option>
              {assets.map((a) => (
                <option key={a.asset_id} value={a.asset_id}>
                  {a.name}
                </option>
              ))}
            </select>
          </div>

          {/* Advanced analysis knobs: FPS override & nperseg */}
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <label className="text-[10px] text-slate-400 block mb-1">
                FPS OVERRIDE
              </label>
              <input
                type="number"
                placeholder="Auto"
                value={fpsOverride ?? ""}
                onChange={(e) =>
                  setFpsOverride(e.target.value ? Number(e.target.value) : null)
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-2 py-1.5 text-slate-200"
              />
            </div>
            <div className="w-24">
              <label className="text-[10px] text-slate-400 block mb-1">
                NPERSEG
              </label>
              <select
                value={nperseg}
                onChange={(e) => setNperseg(Number(e.target.value))}
                className="w-full bg-[#131B26] border border-white/10 rounded px-2 py-1.5 text-slate-200"
              >
                <option value={64}>64</option>
                <option value={128}>128</option>
                <option value={256}>256</option>
                <option value={512}>512</option>
              </select>
            </div>
          </div>
        </div>

        {/* 500 FPS Mendeley explanation banner */}
        {curPreset?.recommended_fps_override === 500 && !uploadedFile && (
          <div className="p-2.5 bg-amber-950/20 border border-amber-800/50 rounded text-amber-300 text-xs font-mono leading-tight flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              High-Speed Rotor Dataset: 1000/2000/3000 RPM AVIs advertise 100 FPS in the container header, but physical strobe capture was performed at 500 FPS. FPS override is set to 500.0 for accurate spectral scaling.
            </span>
          </div>
        )}
      </div>

      {/* Viewport and Execution Section */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* Left Column: Canvas ROI setup */}
        <div className="lg:col-span-7 flex flex-col gap-3">
          <RoiInteractiveCanvas
            previewImageBase64={
              previewData?.preview_image_base64 ||
              (previewData as any)?.preview_png_base64 ||
              null
            }
            nativeWidth={previewData?.frame_width || previewData?.width || 1280}
            nativeHeight={previewData?.frame_height || previewData?.height || 720}
            targetRoi={targetRoi}
            anchorRoi={anchorRoi}
            onTargetRoiChange={setTargetRoi}
            onAnchorRoiChange={setAnchorRoi}
            presetId={uploadedFile ? null : (selectedPresetId || null)}
            uploadId={uploadedFile ? (previewData?.upload_id || null) : null}
            isStreaming={isAnalyzing}
          />

          <div className="flex items-center justify-between pt-2">
            {isUploading ? (
              <div className="flex items-center gap-2 text-xs font-mono text-[#22D3EE]">
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Uploading &amp; decoding frame 0...</span>
              </div>
            ) : (
              <div />
            )}
            <button
              type="button"
              disabled={isAnalyzing || isUploading || !previewData}
              onClick={handleAnalyze}
              className="flex items-center gap-2 px-6 py-2.5 bg-[#22D3EE] hover:bg-[#22D3EE]/90 text-black font-semibold rounded font-mono text-xs transition disabled:opacity-40 shadow-lg shadow-[#22D3EE]/20"
            >
              {isAnalyzing ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Processing Frames (Welch PSD)...
                </>
              ) : isUploading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Uploading Video...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-black" />
                  Run Offline Inspection Analysis
                </>
              )}
            </button>
          </div>
        </div>

        {/* Right Column: Execution results or prompt */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          {analysisResult ? (
            <div className="flex flex-col gap-4 animate-in fade-in duration-200">
              {/* Executive Metrics Header */}
              <div className="p-3 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-2">
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <div className="flex items-center gap-2 font-mono text-xs text-white">
                    <FileCheck className="w-4 h-4 text-[#22D3EE]" />
                    <span className="font-bold">INSPECTION SUMMARY</span>
                  </div>
                  <span className="text-[11px] font-mono text-slate-400">
                    Run ID: {analysisResult.run_id}
                  </span>
                </div>

                <div className="grid grid-cols-3 gap-2 font-mono text-xs">
                  <div className="p-2 bg-[#131B26] rounded">
                    <span className="text-slate-400 text-[10px] block">FRAMES</span>
                    <span className="font-bold text-white tabular-nums">
                      {analysisResult.frames_analysed}
                    </span>
                  </div>
                  <div className="p-2 bg-[#131B26] rounded">
                    <span className="text-slate-400 text-[10px] block">SAMPLING FPS</span>
                    <span className="font-bold text-[#22D3EE] tabular-nums">
                      {analysisResult.measured_fps != null ? `${analysisResult.measured_fps.toFixed(1)} Hz` : "--"}
                    </span>
                  </div>
                  <div className="p-2 bg-[#131B26] rounded">
                    <span className="text-slate-400 text-[10px] block">NYQUIST LIMIT</span>
                    <span className="font-bold text-white tabular-nums">
                      {analysisResult.measured_fps != null ? `${(analysisResult.measured_fps / 2).toFixed(1)} Hz` : "--"}
                    </span>
                  </div>
                </div>
              </div>

              {/* X & Y Cards */}
              <div className="grid grid-cols-2 gap-3">
                {/* X Axis */}
                <div className="p-3 bg-[#0D121A] border border-[#22D3EE]/30 rounded flex flex-col gap-1.5 font-mono text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-[#22D3EE] font-bold">X-AXIS</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
                        analysisResult.x_metrics?.signal_quality === "VALID"
                          ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                          : "bg-rose-950/40 text-rose-400 border-rose-800"
                      }`}
                    >
                      {analysisResult.x_metrics?.signal_quality || "--"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">PEAK FREQ</span>
                    <span className="text-base font-bold text-white tabular-nums">
                      {analysisResult.x_metrics?.dominant_frequency_hz != null
                        ? `${analysisResult.x_metrics.dominant_frequency_hz.toFixed(2)} Hz`
                        : "--"}
                    </span>
                  </div>
                  <div className="flex justify-between text-[11px] pt-1 border-t border-white/5">
                    <span className="text-slate-400">RMS:</span>
                    <span className="tabular-nums font-semibold">
                      {analysisResult.x_metrics?.rms_displacement_px != null
                        ? `${analysisResult.x_metrics.rms_displacement_px.toFixed(4)} px`
                        : "--"}
                    </span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Prominence:</span>
                    <span className="tabular-nums">
                      {analysisResult.x_metrics?.peak_to_median_db != null
                        ? `${analysisResult.x_metrics.peak_to_median_db.toFixed(1)} dB`
                        : "--"}
                    </span>
                  </div>
                </div>

                {/* Y Axis */}
                <div className="p-3 bg-[#0D121A] border border-[#F59E0B]/30 rounded flex flex-col gap-1.5 font-mono text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-[#F59E0B] font-bold">Y-AXIS</span>
                    <span
                      className={`px-1.5 py-0.5 rounded text-[9px] font-semibold border ${
                        analysisResult.y_metrics?.signal_quality === "VALID"
                          ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                          : "bg-rose-950/40 text-rose-400 border-rose-800"
                      }`}
                    >
                      {analysisResult.y_metrics?.signal_quality || "--"}
                    </span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 block">PEAK FREQ</span>
                    <span className="text-base font-bold text-white tabular-nums">
                      {analysisResult.y_metrics?.dominant_frequency_hz != null
                        ? `${analysisResult.y_metrics.dominant_frequency_hz.toFixed(2)} Hz`
                        : "--"}
                    </span>
                  </div>
                  <div className="flex justify-between text-[11px] pt-1 border-t border-white/5">
                    <span className="text-slate-400">RMS:</span>
                    <span className="tabular-nums font-semibold">
                      {analysisResult.y_metrics?.rms_displacement_px != null
                        ? `${analysisResult.y_metrics.rms_displacement_px.toFixed(4)} px`
                        : "--"}
                    </span>
                  </div>
                  <div className="flex justify-between text-[11px]">
                    <span className="text-slate-400">Prominence:</span>
                    <span className="tabular-nums">
                      {analysisResult.y_metrics?.peak_to_median_db != null
                        ? `${analysisResult.y_metrics.peak_to_median_db.toFixed(1)} dB`
                        : "--"}
                    </span>
                  </div>
                </div>
              </div>

              {/* Baseline Assessment (if available) */}
              {analysisResult.baseline_assessment && (
                <div
                  className={`p-3 rounded border font-mono text-xs flex flex-col gap-1.5 ${
                    analysisResult.baseline_assessment.overall_status === "NORMAL"
                      ? "bg-emerald-950/20 border-emerald-800 text-emerald-300"
                      : "bg-rose-950/20 border-rose-800 text-rose-300"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-bold flex items-center gap-1.5">
                      <ShieldCheck className="w-4 h-4" />
                      BASELINE: {analysisResult.baseline_assessment.overall_status}
                    </span>
                    <span>
                      Max |Z| = {analysisResult.baseline_assessment.max_z_score != null
                        ? analysisResult.baseline_assessment.max_z_score.toFixed(2)
                        : "--"}
                    </span>
                  </div>
                </div>
              )}

              {/* Temporal Stability Audit */}
              {analysisResult.temporal_stability && (
                <div className="p-3 bg-[#0D121A] border border-white/10 rounded font-mono text-xs flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Clock className="w-4 h-4 text-slate-400" />
                    <span className="text-slate-300">TIMEBASE:</span>
                    <span className="font-semibold text-emerald-400">
                      {analysisResult.temporal_stability.status}
                    </span>
                  </div>
                  <span className="text-slate-400 text-[11px]">
                    Jitter:{" "}
                    {(
                      (analysisResult.temporal_stability.jitter_ratio ?? 0) * 100
                    ).toFixed(2)}
                    %
                  </span>
                </div>
              )}
            </div>
          ) : (
            <div className="p-8 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col items-center justify-center text-center text-slate-500 font-mono text-xs gap-2 min-h-[300px]">
              <Film className="w-8 h-8 text-slate-600" />
              <span>NO OFFLINE RUN EXECUTED</span>
              <p className="text-[11px] text-slate-600 max-w-xs">
                Adjust Target & Anchor ROIs on frame 0 and click "Run Offline Inspection Analysis" to process the entire video.
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Full Duration Oscilloscope and Welch Spectrum Plots */}
      {analysisResult && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 mt-2">
          <OscilloscopeCanvas
            samples={traceSamples}
            maxSamples={traceSamples.length}
            isStatic={true}
            resetKey={analysisResult.run_id}
            correlationResponse={
              analysisResult.summary?.mean_target_response ??
              analysisResult.summary?.mean_min_phase_correlation_response ??
              analysisResult.summary?.mean_min_phase_response ??
              null
            }
            anchorCorrelationResponse={
              analysisResult.summary?.mean_anchor_response ??
              analysisResult.summary?.mean_min_phase_correlation_response ??
              analysisResult.summary?.mean_min_phase_response ??
              null
            }
            height={220}
          />
          <SpectrumPlot
            xMetrics={plotXMetrics}
            yMetrics={plotYMetrics}
            height={220}
          />
        </div>
      )}
    </div>
  );
};
