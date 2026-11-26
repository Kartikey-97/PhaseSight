"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import type {
  Asset,
  BaselineAssessment,
  BaselineSummary,
  Preset,
  ROI,
  RollingUpdate,
  SessionReport,
  TelemetrySnapshot,
  TraceSample,
  VideoPreview,
} from "@/lib/types";
import { api } from "@/lib/api";
import { WebcamStreamer, WebcamInfo } from "@/lib/webcamStreamer";
import { useTelemetrySocket } from "@/lib/useTelemetrySocket";
import { RoiInteractiveCanvas } from "./RoiInteractiveCanvas";
import { OscilloscopeCanvas } from "./OscilloscopeCanvas";
import { SpectrumPlot } from "./SpectrumPlot";
import { SessionReportModal } from "./SessionReportModal";
import {
  Camera,
  Film,
  Play,
  Square,
  RefreshCw,
  Sliders,
  CheckCircle2,
  AlertTriangle,
  Activity,
  Layers,
  Radio,
  Clock,
  ShieldAlert,
  Upload,
  Loader2,
} from "lucide-react";

interface LiveMonitorViewProps {
  activeAsset: Asset | null;
}

export const LiveMonitorView: React.FC<LiveMonitorViewProps> = ({
  activeAsset,
}) => {
  // Source selection: browser_webcam vs video_replay
  const [sourceType, setSourceType] = useState<"browser_webcam" | "video_replay">(
    "video_replay"
  );

  // Video Replay state
  const [presets, setPresets] = useState<Preset[]>([]);
  const [selectedPresetId, setSelectedPresetId] = useState<string>("portable_baseline");
  const [previewData, setPreviewData] = useState<VideoPreview | null>(null);
  const [fpsOverride, setFpsOverride] = useState<number | null>(null);
  const [playbackRate, setPlaybackRate] = useState<number>(1.0);
  const [loopReplay, setLoopReplay] = useState<boolean>(true);
  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState<boolean>(false);

  // Browser Webcam state
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamerRef = useRef<WebcamStreamer | null>(null);
  const [isCameraActive, setIsCameraActive] = useState(false);
  const [availableCameras, setAvailableCameras] = useState<MediaDeviceInfo[]>([]);
  const [selectedCameraId, setSelectedCameraId] = useState<string>("");
  const [cameraInfo, setCameraInfo] = useState<WebcamInfo | null>(null);
  const [webcamStats, setWebcamStats] = useState<{
    fps: number;
    droppedFrames: number;
    bufferedAmount: number;
  }>({ fps: 0, droppedFrames: 0, bufferedAmount: 0 });

  // ROIs (default compact 96x96 for low WebSocket payload & low jitter)
  const [targetRoi, setTargetRoi] = useState<ROI>({
    x: 350,
    y: 150,
    width: 96,
    height: 96,
  });
  const [anchorRoi, setAnchorRoi] = useState<ROI>({
    x: 60,
    y: 100,
    width: 96,
    height: 96,
  });

  // Active Session state
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [latestReport, setLatestReport] = useState<SessionReport | null>(null);
  const [showReportModal, setShowReportModal] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Real-time telemetry state
  const [liveSamples, setLiveSamples] = useState<TraceSample[]>([]);
  const [rollingUpdate, setRollingUpdate] = useState<RollingUpdate | null>(null);
  const [totalSamplesReceived, setTotalSamplesReceived] = useState(0);

  // Live texture tracking for preflight gating
  const [liveTargetStd, setLiveTargetStd] = useState<number | null>(null);
  const [liveAnchorStd, setLiveAnchorStd] = useState<number | null>(null);

  // Active asset's flattened statistical baseline
  const [activeBaseline, setActiveBaseline] = useState<BaselineSummary | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!activeAsset?.asset_id) {
      setActiveBaseline(null);
      return;
    }
    api
      .getBaselines(activeAsset.asset_id)
      .then((baselines) => {
        if (!cancelled) {
          setActiveBaseline(baselines.length > 0 ? baselines[0] : null);
        }
      })
      .catch(() => {
        if (!cancelled) setActiveBaseline(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeAsset?.asset_id]);

  // Initialize webcam streamer instance
  useEffect(() => {
    const s = new WebcamStreamer();
    s.onStatsUpdate = (stats) => setWebcamStats(stats);
    s.onError = (err) => setErrorMessage(err.message);
    streamerRef.current = s;

    return () => {
      s.stopCamera();
    };
  }, []);

  // Fetch presets on mount
  useEffect(() => {
    let cancel = false;
    api
      .getPresets()
      .then((data) => {
        if (!cancel) {
          setPresets(data);
          if (data.length > 0 && !selectedPresetId) {
            setSelectedPresetId(data[0].preset_id);
          }
        }
      })
      .catch((err) => console.error("Error loading presets:", err));

    return () => {
      cancel = true;
    };
  }, []);

  // Fetch preview when preset or uploaded file changes
  const loadPreview = useCallback(async (presetId?: string, file?: File) => {
    try {
      setErrorMessage(null);
      const res = await api.getPreview({ preset_id: presetId, file });
      setPreviewData(res);

      // Auto populate preset defaults
      const curPreset = presets.find((p) => p.preset_id === presetId);
      if (curPreset) {
        if (curPreset.default_target_roi) setTargetRoi(curPreset.default_target_roi);
        if (curPreset.default_anchor_roi) setAnchorRoi(curPreset.default_anchor_roi);
        if (curPreset.recommended_fps_override) {
          setFpsOverride(curPreset.recommended_fps_override);
        } else {
          setFpsOverride(null);
        }
        if (curPreset.recommended_playback_rate) {
          setPlaybackRate(curPreset.recommended_playback_rate);
        } else {
          setPlaybackRate(1.0);
        }
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to load video preview");
    }
  }, [presets]);

  useEffect(() => {
    if (sourceType === "video_replay" && selectedPresetId && !uploadedFile) {
      loadPreview(selectedPresetId);
    }
  }, [sourceType, selectedPresetId, uploadedFile, loadPreview]);

  // File upload handler for custom video replay
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

  // Check for any currently active session on backend on mount
  useEffect(() => {
    api
      .getActiveSession()
      .then((active) => {
        if (active && active.session_id) {
          setActiveSessionId(active.session_id);
        }
      })
      .catch(() => {});
  }, []);

  // Sync default ROIs from Active Asset if changed
  const applyAssetRois = () => {
    if (activeAsset?.default_target_roi) {
      setTargetRoi(activeAsset.default_target_roi);
    }
    if (activeAsset?.default_anchor_roi) {
      setAnchorRoi(activeAsset.default_anchor_roi);
    }
  };

  // Telemetry WebSocket subscription
  const handleSnapshot = useCallback((snap: TelemetrySnapshot) => {
    if (snap.latest_update) setRollingUpdate(snap.latest_update);
    if (snap.recent_samples?.length) {
      setLiveSamples(snap.recent_samples);
      setTotalSamplesReceived((prev) => Math.max(prev, snap.recent_samples!.length));
    }
  }, []);

  const handleTraceBatch = useCallback((samples: TraceSample[]) => {
    setLiveSamples(samples);
    setTotalSamplesReceived((prev) => prev + samples.length);
  }, []);

  const handleRollingUpdate = useCallback((update: RollingUpdate) => {
    setRollingUpdate(update);
  }, []);

  const handleSessionEnded = useCallback((report?: SessionReport) => {
    setActiveSessionId(null);
    if (report) {
      setLatestReport(report);
      setShowReportModal(true);
    }
  }, []);

  const { isConnected: isTelemetryConnected } = useTelemetrySocket({
    sessionId: activeSessionId,
    onSnapshot: handleSnapshot,
    onTraceBatch: handleTraceBatch,
    onRollingUpdate: handleRollingUpdate,
    onSessionEnded: handleSessionEnded,
    onError: (e) => console.error("Telemetry socket error:", e),
  });

  // Camera activation handlers
  const handleToggleCamera = async () => {
    if (isCameraActive) {
      streamerRef.current?.stopCamera();
      setIsCameraActive(false);
      setCameraInfo(null);
    } else {
      try {
        setErrorMessage(null);
        await streamerRef.current?.openCamera(selectedCameraId || undefined);
        if (videoRef.current) {
          streamerRef.current?.attachVideoElement(videoRef.current);
        }
        setIsCameraActive(true);
        const info = streamerRef.current?.getTrackSettings();
        if (info) setCameraInfo(info);

        // Enumerate devices
        const devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevs = devices.filter((d) => d.kind === "videoinput");
        setAvailableCameras(videoDevs);
      } catch (err: any) {
        setErrorMessage(err.message || "Could not start camera");
      }
    }
  };

  // Start Session
  const handleStartSession = async () => {
    try {
      setIsStarting(true);
      setErrorMessage(null);
      // Immediately reset stale telemetry and oscilloscope waveforms
      setRollingUpdate(null);
      setLiveSamples([]);
      setTotalSamplesReceived(0);

      const session = await api.startSession({
        source_type: sourceType,
        target_roi: targetRoi,
        anchor_roi: anchorRoi,
        asset_id: activeAsset?.asset_id || null,
        preset_id:
          sourceType === "video_replay"
            ? uploadedFile
              ? null
              : selectedPresetId || null
            : null,
        upload_id:
          sourceType === "video_replay"
            ? uploadedFile
              ? previewData?.upload_id || null
              : null
            : null,
        playback_rate: playbackRate,
        loop: loopReplay,
        fps_override: sourceType === "video_replay" ? fpsOverride : null,
      });

      setActiveSessionId(session.session_id);
      setTotalSamplesReceived(0);

      // If browser webcam, start local binary streamer
      if (sourceType === "browser_webcam" && streamerRef.current) {
        streamerRef.current.startStreaming(session.session_id, targetRoi, anchorRoi);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to start session");
    } finally {
      setIsStarting(false);
    }
  };

  // Re-lock reference / recalibrate
  const handleRecalibrate = async () => {
    if (!activeSessionId) return;
    try {
      if (sourceType === "browser_webcam") {
        streamerRef.current?.triggerNextFrameRecalibrate();
      } else {
        await api.recalibrateSession(activeSessionId);
      }
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to recalibrate");
    }
  };

  // Stop Session
  const handleStopSession = async () => {
    if (!activeSessionId) return;
    try {
      setIsStopping(true);
      if (sourceType === "browser_webcam") {
        streamerRef.current?.stopStreaming();
      }
      const res = await api.stopSession(activeSessionId);
      setActiveSessionId(null);
      const rep = (res as any).report
        ? { ...(res as any).report, run_id: (res as any).run_id, session_id: (res as any).session_id }
        : res;
      setLatestReport(rep);
      setShowReportModal(true);
    } catch (err: any) {
      setErrorMessage(err.message || "Failed to stop session");
    } finally {
      setIsStopping(false);
    }
  };

  const isStreaming = activeSessionId !== null;
  const curPreset = presets.find((p) => p.preset_id === selectedPresetId);

  return (
    <div className="flex flex-col gap-4">
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

      {/* Main 12-column Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        {/* ============================================================== */}
        {/* LEFT COLUMN: Setup, Viewport & Transport (7 Cols)             */}
        {/* ============================================================== */}
        <div className="lg:col-span-7 flex flex-col gap-4">
          {/* Source Switcher Toolbar */}
          <div className="p-3 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
              <span className="text-xs font-semibold text-slate-300 font-display flex items-center gap-2">
                <Radio className="w-4 h-4 text-[#22D3EE]" />
                VIDEO INGEST SOURCE
              </span>

              {/* Mode toggles */}
              <div className="flex items-center bg-[#131B26] border border-white/10 rounded p-0.5 text-xs font-mono">
                <button
                  type="button"
                  data-testid="mode-video-replay"
                  disabled={isStreaming}
                  onClick={() => {
                    setSourceType("video_replay");
                    if (curPreset?.default_target_roi) setTargetRoi(curPreset.default_target_roi);
                    if (curPreset?.default_anchor_roi) setAnchorRoi(curPreset.default_anchor_roi);
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition ${
                    sourceType === "video_replay"
                      ? "bg-[#22D3EE] text-black font-semibold"
                      : "text-slate-400 hover:text-white"
                  } disabled:opacity-40`}
                >
                  <Film className="w-3.5 h-3.5" />
                  Video Replay
                </button>
                <button
                  type="button"
                  data-testid="mode-browser-camera"
                  disabled={isStreaming}
                  onClick={() => {
                    setSourceType("browser_webcam");
                    setTargetRoi({ x: 350, y: 150, width: 96, height: 96 });
                    setAnchorRoi({ x: 60, y: 100, width: 96, height: 96 });
                  }}
                  className={`flex items-center gap-1.5 px-3 py-1 rounded transition ${
                    sourceType === "browser_webcam"
                      ? "bg-[#22D3EE] text-black font-semibold"
                      : "text-slate-400 hover:text-white"
                  } disabled:opacity-40`}
                >
                  <Camera className="w-3.5 h-3.5" />
                  Browser Camera
                </button>
              </div>
            </div>

            {/* Mode A: Browser Camera configuration */}
            {sourceType === "browser_webcam" && (
              <div className="flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    disabled={isStreaming}
                    onClick={handleToggleCamera}
                    className={`px-3 py-1.5 rounded font-semibold transition ${
                      isCameraActive
                        ? "bg-rose-900/40 text-rose-300 border border-rose-700 hover:bg-rose-900/60"
                        : "bg-emerald-900/40 text-emerald-300 border border-emerald-700 hover:bg-emerald-900/60"
                    } disabled:opacity-40`}
                  >
                    {isCameraActive ? "Stop Camera" : "Enable Camera"}
                  </button>

                  {availableCameras.length > 0 && (
                    <select
                      disabled={isStreaming}
                      value={selectedCameraId}
                      onChange={(e) => setSelectedCameraId(e.target.value)}
                      className="bg-[#131B26] border border-white/10 rounded px-2 py-1 text-slate-200"
                    >
                      {availableCameras.map((dev) => (
                        <option key={dev.deviceId} value={dev.deviceId}>
                          {dev.label || `Camera ${dev.deviceId.slice(0, 5)}`}
                        </option>
                      ))}
                    </select>
                  )}
                </div>

                {cameraInfo && (
                  <div className="flex items-center gap-3 text-slate-400 text-[11px]">
                    <span>
                      {cameraInfo.width}×{cameraInfo.height} px
                    </span>
                    <span>{cameraInfo.frameRate} FPS target</span>
                    {isStreaming && (
                      <span className="text-[#22D3EE] tabular-nums">
                        Ingest: {webcamStats.fps} FPS
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Mode B: Video Replay configuration */}
            {sourceType === "video_replay" && (
              <div className="flex flex-col gap-2.5 text-xs font-mono">
                <div className="flex flex-wrap items-center gap-3">
                  <div className="flex-1 min-w-[200px]">
                    <label className="text-[10px] text-slate-400 block mb-0.5">
                      BENCHMARK DATASET PRESET
                    </label>
                    <select
                      data-testid="select-video-preset"
                      disabled={isStreaming || isUploading || uploadedFile !== null}
                      value={selectedPresetId}
                      onChange={(e) => {
                        setSelectedPresetId(e.target.value);
                        setUploadedFile(null);
                        loadPreview(e.target.value);
                      }}
                      className="w-full bg-[#131B26] border border-white/10 rounded px-2.5 py-1 text-slate-200"
                    >
                      {presets.map((p) => (
                        <option key={p.preset_id} value={p.preset_id}>
                          {p.label} ({p.category})
                        </option>
                      ))}
                    </select>
                  </div>

                  {/* File Upload for Replay */}
                  <div className="w-48">
                    <label className="text-[10px] text-slate-400 block mb-0.5">
                      OR UPLOAD CUSTOM VIDEO
                    </label>
                    <div className="flex items-center gap-1.5">
                      <label className="flex-1 flex items-center justify-center gap-1.5 px-2.5 py-1 bg-[#131B26] hover:bg-[#1A2433] border border-white/10 rounded cursor-pointer text-slate-300">
                        <Upload className="w-3.5 h-3.5 text-[#22D3EE]" />
                        <span className="truncate text-xs">
                          {uploadedFile ? uploadedFile.name : "Choose File"}
                        </span>
                        <input
                          type="file"
                          accept="video/*"
                          disabled={isStreaming || isUploading}
                          onChange={handleFileUpload}
                          className="hidden"
                        />
                      </label>
                      {uploadedFile && (
                        <button
                          type="button"
                          disabled={isStreaming || isUploading}
                          onClick={() => {
                            setUploadedFile(null);
                            const defaultPreset = presets[0]?.preset_id || "portable_baseline";
                            setSelectedPresetId(defaultPreset);
                            loadPreview(defaultPreset);
                          }}
                          className="px-2 py-1 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-slate-400 text-xs"
                        >
                          Clear
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="w-28">
                    <label className="text-[10px] text-slate-400 block mb-0.5">
                      FPS OVERRIDE
                    </label>
                    <input
                      type="number"
                      disabled={isStreaming}
                      placeholder="Auto"
                      value={fpsOverride ?? ""}
                      onChange={(e) =>
                        setFpsOverride(e.target.value ? Number(e.target.value) : null)
                      }
                      className="w-full bg-[#131B26] border border-white/10 rounded px-2 py-1 text-slate-200"
                    />
                  </div>

                  <div className="w-32">
                    <label className="text-[10px] text-slate-400 block mb-0.5">
                      SPEED: {playbackRate.toFixed(2)}×
                    </label>
                    <input
                      type="range"
                      min={0.05}
                      max={2.0}
                      step={0.05}
                      disabled={isStreaming}
                      value={playbackRate}
                      onChange={(e) => setPlaybackRate(Number(e.target.value))}
                      className="w-full"
                    />
                  </div>

                  <div className="flex items-center gap-1.5 pt-4">
                    <input
                      type="checkbox"
                      id="loopReplay"
                      disabled={isStreaming}
                      checked={loopReplay}
                      onChange={(e) => setLoopReplay(e.target.checked)}
                      className="rounded bg-[#131B26]"
                    />
                    <label htmlFor="loopReplay" className="text-slate-300 select-none">
                      Continuous Loop
                    </label>
                  </div>
                </div>

                {/* 500 FPS Mendeley AVI explanation banner */}
                {curPreset?.recommended_fps_override === 500 && (
                  <div className="p-2 bg-amber-950/20 border border-amber-800/50 rounded text-amber-300 text-[11px] leading-tight flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                    <span>
                      High-Speed Mendeley Benchmark: AVI container header advertises 100 FPS, but physical capture was performed at 500 FPS. FPS override set to 500.0 (Nyquist = 250 Hz).
                    </span>
                  </div>
                )}

                {/* Upload in flight banner */}
                {isUploading && (
                  <div className="p-2 bg-[#22D3EE]/10 border border-[#22D3EE]/30 rounded text-[#22D3EE] text-xs flex items-center gap-2">
                    <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0 text-[#22D3EE]" />
                    <span>Uploading &amp; decoding frame 0...</span>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Interactive ROI Canvas Viewport */}
          <RoiInteractiveCanvas
            videoRef={videoRef}
            isCameraActive={sourceType === "browser_webcam" && isCameraActive}
            previewImageBase64={
              sourceType === "video_replay"
                ? previewData?.preview_image_base64 ||
                  (previewData as any)?.preview_png_base64 ||
                  null
                : null
            }
            mjpegSessionId={sourceType === "video_replay" ? activeSessionId : null}
            nativeWidth={
              sourceType === "browser_webcam"
                ? cameraInfo?.width || 1280
                : previewData?.frame_width || previewData?.width || 1280
            }
            nativeHeight={
              sourceType === "browser_webcam"
                ? cameraInfo?.height || 720
                : previewData?.frame_height || previewData?.height || 720
            }
            targetRoi={targetRoi}
            anchorRoi={anchorRoi}
            onTargetRoiChange={(roi) => {
              setTargetRoi(roi);
              if (isStreaming && sourceType === "browser_webcam") {
                streamerRef.current?.updateROIs(roi, anchorRoi);
              }
            }}
            onAnchorRoiChange={(roi) => {
              setAnchorRoi(roi);
              if (isStreaming && sourceType === "browser_webcam") {
                streamerRef.current?.updateROIs(targetRoi, roi);
              }
            }}
            presetId={
              sourceType === "video_replay"
                ? uploadedFile
                  ? null
                  : selectedPresetId || null
                : null
            }
            uploadId={
              sourceType === "video_replay"
                ? uploadedFile
                  ? previewData?.upload_id || null
                  : null
                : null
            }
            isStreaming={isStreaming}
            onTextureChange={({ targetStd, anchorStd }) => {
              setLiveTargetStd(targetStd);
              setLiveAnchorStd(anchorStd);
            }}
          />

          {/* Pre-flight texture warning banner for browser_webcam mode */}
          {sourceType === "browser_webcam" &&
            isCameraActive &&
            !isStreaming &&
            liveTargetStd !== null &&
            liveAnchorStd !== null &&
            (liveTargetStd < 2.0 || liveAnchorStd < 2.0) && (
              <div className="p-2.5 bg-amber-950/40 border border-amber-600/60 rounded text-amber-300 text-xs flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                <span>
                  Move Target/Anchor ROI onto a textured edge or machine feature — σ ≥ 2.0 required for sub-pixel tracking
                </span>
              </div>
            )}

          {/* ROI Size Warning for Browser Camera Mode */}
          {sourceType === "browser_webcam" &&
            (targetRoi.width * targetRoi.height > 25600 ||
              anchorRoi.width * anchorRoi.height > 25600) && (
              <div className="p-2.5 bg-amber-950/30 border border-amber-600/50 rounded text-amber-300 text-xs flex items-center gap-2 font-mono">
                <AlertTriangle className="w-4 h-4 shrink-0 text-amber-400" />
                <span>
                  Large ROI (&gt;160×160 px) increases WebSocket payload and FFT load — use 64×64 to 128×128 px for smooth 30 FPS tracking.
                </span>
              </div>
            )}

          {/* Session Transport Action Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded">
            <div className="flex items-center gap-2">
              {!isStreaming ? (
                <button
                  type="button"
                  data-testid="btn-start-session"
                  disabled={
                    isStarting ||
                    isUploading ||
                    (sourceType === "browser_webcam" &&
                      (!isCameraActive ||
                        liveTargetStd === null ||
                        liveAnchorStd === null ||
                        liveTargetStd < 2.0 ||
                        liveAnchorStd < 2.0))
                  }
                  onClick={handleStartSession}
                  className="flex items-center gap-2 px-5 py-2.5 bg-[#22D3EE] hover:bg-[#22D3EE]/90 text-black font-semibold rounded font-mono text-xs transition disabled:opacity-40 shadow-lg shadow-[#22D3EE]/20"
                >
                  <Play className="w-4 h-4 fill-black" />
                  {isStarting ? "Initializing..." : "Start Continuous Monitoring"}
                </button>
              ) : (
                <>
                  <button
                    type="button"
                    data-testid="btn-stop-session"
                    disabled={isStopping}
                    onClick={handleStopSession}
                    className="flex items-center gap-2 px-5 py-2.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded font-mono text-xs transition shadow-lg shadow-rose-600/20"
                  >
                    <Square className="w-4 h-4 fill-white" />
                    {isStopping ? "Stopping..." : "Stop & Save Report"}
                  </button>

                  <button
                    type="button"
                    onClick={handleRecalibrate}
                    className="flex items-center gap-2 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-white/10 rounded font-mono text-xs transition"
                    title="Re-locks the phase correlation reference templates to current patches"
                  >
                    <RefreshCw className="w-3.5 h-3.5 text-[#22D3EE]" />
                    Re-lock Reference
                  </button>
                </>
              )}
            </div>

            {/* Asset default ROI shortcut */}
            {activeAsset && !isStreaming && (
              <button
                type="button"
                onClick={applyAssetRois}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 hover:bg-white/10 border border-white/10 rounded text-slate-300 text-xs font-mono transition"
              >
                <Layers className="w-3.5 h-3.5 text-[#22D3EE]" />
                Apply Asset ROIs
              </button>
            )}
          </div>
        </div>

        {/* ============================================================== */}
        {/* RIGHT COLUMN: Live Telemetry, Scope & PSD (5 Cols)             */}
        {/* ============================================================== */}
        <div className="lg:col-span-5 flex flex-col gap-4">
          {/* Honest State & Warm-up Banner */}
          <div className="p-3 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 font-mono text-xs">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    isStreaming
                      ? rollingUpdate?.state === "ACTIVE"
                        ? "bg-emerald-400 animate-pulse-subtle"
                        : rollingUpdate?.state === "DEGRADED"
                        ? "bg-rose-500 animate-pulse"
                        : "bg-amber-400 animate-pulse"
                      : "bg-slate-600"
                  }`}
                />
                <span className="font-bold text-white tracking-wider">
                  ENGINE STATE:{" "}
                  <span
                    className={
                      rollingUpdate?.state === "ACTIVE"
                        ? "text-emerald-400"
                        : rollingUpdate?.state === "WARMING_UP"
                        ? "text-amber-400"
                        : rollingUpdate?.state === "DEGRADED"
                        ? "text-rose-400 font-bold"
                        : "text-slate-400"
                    }
                  >
                    {isStreaming ? rollingUpdate?.state || "INITIALIZING" : "STANDBY"}
                  </span>
                </span>
              </div>

              {isStreaming && (
                <span className="text-[10px] font-mono text-slate-400">
                  Seq #{rollingUpdate?.seq ?? totalSamplesReceived} ({totalSamplesReceived} pts)
                </span>
              )}
            </div>

            {/* Warm-up progress bar */}
            {isStreaming &&
              rollingUpdate?.warmup_progress &&
              (() => {
                const filled =
                  rollingUpdate.warmup_progress.filled_samples ?? 0;
                const requiredWarmup =
                  rollingUpdate.warmup_progress.required_samples ?? 128;
                const capacity =
                  (rollingUpdate as any).buffer_capacity || 512;
                const pct = (
                  rollingUpdate.warmup_progress.percentage ?? 0
                ).toFixed(0);
                const isWarm = filled >= requiredWarmup;

                return (
                  <div className="flex flex-col gap-1 font-mono text-[11px]">
                    <div className="flex justify-between text-slate-400">
                      <span>
                        {rollingUpdate.state === "BUFFERING"
                          ? "Buffering Initial Welch Window"
                          : rollingUpdate.state === "WARMING_UP"
                          ? "Accumulating Welch Segments (Warm-up)"
                          : "Spectral Window Buffer"}
                      </span>
                      <span>
                        {!isWarm
                          ? `${filled} / ${requiredWarmup} samples (${pct}%)`
                          : `${filled} / ${capacity} buffer (min ${requiredWarmup} · Ready)`}
                      </span>
                    </div>
                    <div className="w-full h-1.5 bg-slate-800 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-[#22D3EE] transition-all duration-150"
                        style={{
                          width: !isWarm
                            ? `${Math.min(
                                100,
                                rollingUpdate.warmup_progress.percentage ?? 0
                              )}%`
                            : `${Math.min(
                                100,
                                Math.max(10, (filled / capacity) * 100)
                              )}%`,
                        }}
                      />
                    </div>
                    {rollingUpdate.state === "BUFFERING" && (
                      <p className="text-[10px] text-slate-400 leading-tight">
                        * Scientific gate: Buffering initial frame samples (
                        {filled}/{Math.round(requiredWarmup / 2)}) for initial
                        FFT estimate.
                      </p>
                    )}
                    {rollingUpdate.state === "WARMING_UP" && (
                      <p className="text-[10px] text-amber-400/90 leading-tight">
                        * Scientific honesty: Spectral peaks are refined as
                        Welch segments accumulate up to {requiredWarmup}{" "}
                        samples.
                      </p>
                    )}
                  </div>
                );
              })()}

            {/* Inline Degraded State Diagnostic Callout */}
            {isStreaming && rollingUpdate?.state === "DEGRADED" && (
              <div className="p-2.5 bg-rose-950/40 border border-rose-500/60 rounded flex flex-col gap-1.5 text-xs font-mono text-rose-300">
                <div className="flex items-center gap-2 font-bold text-rose-400">
                  <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                  <span>MONITORING DEGRADED — ROOT CAUSE DIAGNOSTICS:</span>
                </div>
                {rollingUpdate.warnings && rollingUpdate.warnings.length > 0 ? (
                  <ul className="list-disc list-inside space-y-1 text-rose-200 text-[11px]">
                    {rollingUpdate.warnings.map((w, idx) => (
                      <li key={idx} className="leading-relaxed">
                        {w}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-rose-200 text-[11px]">
                    Tracking validity dropped below 85% or severe timestamp instability was detected.
                  </p>
                )}
              </div>
            )}
          </div>

          {/* Acquisition & Bandwidth Telemetry Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-xs">
            <div className="p-2 bg-[#131B26] border border-white/5 rounded">
              <span className="text-slate-400 text-[10px] block">MEASURED FPS</span>
              <span className="text-sm font-bold text-[#22D3EE] tabular-nums">
                {rollingUpdate?.measured_fps != null ? `${rollingUpdate.measured_fps.toFixed(1)} Hz` : "--"}
              </span>
            </div>
            <div className="p-2 bg-[#131B26] border border-white/5 rounded">
              <span className="text-slate-400 text-[10px] block">NYQUIST (fs/2)</span>
              <span className="text-sm font-bold text-slate-200 tabular-nums">
                {rollingUpdate?.x_metrics?.nyquist_hz != null
                  ? `${rollingUpdate.x_metrics.nyquist_hz.toFixed(1)} Hz`
                  : "--"}
              </span>
            </div>
            <div className="p-2 bg-[#131B26] border border-white/5 rounded">
              <span className="text-slate-400 text-[10px] block">TIMING STATUS</span>
              <span
                data-testid="live-timing-status-value"
                className={`text-xs font-bold tracking-tight block truncate ${
                  rollingUpdate?.timing_status === "STABLE"
                    ? "text-emerald-400"
                    : rollingUpdate?.timing_status === "ASSUMED_UNIFORM"
                    ? "text-slate-300"
                    : "text-amber-400"
                }`}
                title={rollingUpdate?.timing_status || "--"}
              >
                {(rollingUpdate?.timing_status || "--").replace(/_/g, " ")}
              </span>
            </div>
            <div className="p-2 bg-[#131B26] border border-white/5 rounded">
              <span className="text-slate-400 text-[10px] block">DROPPED FRAMES</span>
              <span data-testid="live-dropped-frames-value" className="text-sm font-bold text-slate-200 tabular-nums">
                {rollingUpdate?.dropped_frames ?? 0}
              </span>
            </div>
          </div>

          {/* X & Y Axis Live Measurement Cards */}
          <div className="grid grid-cols-2 gap-3">
            {/* X Axis */}
            <div data-testid="live-x-metrics" className="p-3 bg-[#0D121A] border border-[#22D3EE]/30 rounded flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#22D3EE] font-mono">
                  X-AXIS (Δx)
                </span>
                <span
                  className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-semibold border ${
                    rollingUpdate?.x_metrics?.signal_quality === "VALID"
                      ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                      : rollingUpdate?.x_metrics?.signal_quality === "CONTAMINATED"
                      ? "bg-rose-950/40 text-rose-400 border-rose-800"
                      : "bg-slate-800 text-slate-400 border-white/10"
                  }`}
                >
                  {rollingUpdate?.x_metrics?.signal_quality || "IDLE"}
                </span>
              </div>
              <div className="flex flex-col gap-1 font-mono text-xs">
                <div>
                  <span className="text-[10px] text-slate-400 block">DOMINANT FREQ</span>
                  <span data-testid="live-x-dominant-freq" className="text-base font-bold text-white tabular-nums">
                    {rollingUpdate?.x_metrics?.dominant_frequency_hz != null
                      ? `${rollingUpdate.x_metrics.dominant_frequency_hz.toFixed(2)} Hz`
                      : "--"}
                  </span>
                </div>
                <div className="flex justify-between text-[11px] pt-1 border-t border-white/5">
                  <span className="text-slate-400">RMS:</span>
                  <span className="text-slate-200 tabular-nums font-semibold">
                    {rollingUpdate?.x_metrics?.rms_displacement_px != null
                      ? `${rollingUpdate.x_metrics.rms_displacement_px.toFixed(4)} px`
                      : "--"}
                  </span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-slate-400">Peak/Med:</span>
                  <span className="text-slate-200 tabular-nums">
                    {rollingUpdate?.x_metrics?.peak_to_median_db != null
                      ? `${rollingUpdate.x_metrics.peak_to_median_db.toFixed(1)} dB`
                      : "--"}
                  </span>
                </div>
              </div>
            </div>

            {/* Y Axis */}
            <div className="p-3 bg-[#0D121A] border border-[#F59E0B]/30 rounded flex flex-col gap-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-[#F59E0B] font-mono">
                  Y-AXIS (Δy)
                </span>
                <span
                  className={`px-1.5 py-0.2 rounded text-[9px] font-mono font-semibold border ${
                    rollingUpdate?.y_metrics?.signal_quality === "VALID"
                      ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                      : rollingUpdate?.y_metrics?.signal_quality === "CONTAMINATED"
                      ? "bg-rose-950/40 text-rose-400 border-rose-800"
                      : "bg-slate-800 text-slate-400 border-white/10"
                  }`}
                >
                  {rollingUpdate?.y_metrics?.signal_quality || "IDLE"}
                </span>
              </div>
              <div className="flex flex-col gap-1 font-mono text-xs">
                <div>
                  <span className="text-[10px] text-slate-400 block">DOMINANT FREQ</span>
                  <span className="text-base font-bold text-white tabular-nums">
                    {rollingUpdate?.y_metrics?.dominant_frequency_hz != null
                      ? `${rollingUpdate.y_metrics.dominant_frequency_hz.toFixed(2)} Hz`
                      : "--"}
                  </span>
                </div>
                <div className="flex justify-between text-[11px] pt-1 border-t border-white/5">
                  <span className="text-slate-400">RMS:</span>
                  <span className="text-slate-200 tabular-nums font-semibold">
                    {rollingUpdate?.y_metrics?.rms_displacement_px != null
                      ? `${rollingUpdate.y_metrics.rms_displacement_px.toFixed(4)} px`
                      : "--"}
                  </span>
                </div>
                <div className="flex justify-between text-[11px]">
                  <span className="text-slate-400">Peak/Med:</span>
                  <span className="text-slate-200 tabular-nums">
                    {rollingUpdate?.y_metrics?.peak_to_median_db != null
                      ? `${rollingUpdate.y_metrics.peak_to_median_db.toFixed(1)} dB`
                      : "--"}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Live Baseline Screening Card */}
          {(rollingUpdate?.baseline_assessment || activeBaseline) &&
            (() => {
              const assess: BaselineAssessment | null =
                rollingUpdate?.baseline_assessment ?? null;
              if (!assess && activeBaseline) {
                const medFreq =
                  activeBaseline.x_baseline?.dominant_frequency_hz_median;
                const medRms =
                  activeBaseline.x_baseline?.rms_displacement_px_median;
                return (
                  <div
                    data-testid="live-baseline-screening-card"
                    className="p-3 rounded border border-emerald-800/40 bg-emerald-950/15 font-mono text-xs flex flex-col gap-1"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-slate-200 flex items-center gap-1.5">
                        <ShieldAlert className="w-3.5 h-3.5 text-emerald-400" />
                        LIVE BASELINE SCREENING
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold border bg-emerald-950/50 text-emerald-400 border-emerald-700/60">
                        ARMED
                      </span>
                    </div>
                    <p className="text-[11px] text-emerald-300/90">
                      Baseline Armed: {activeAsset?.name || activeBaseline.asset_id} (Median X:{" "}
                      {medFreq != null ? `${medFreq.toFixed(2)} Hz` : "--"},{" "}
                      {medRms != null ? `${medRms.toFixed(3)} px` : "--"})
                    </p>
                  </div>
                );
              }

              if (!assess) return null;
              const rawStatus = (
                assess.status ||
                assess.overall_status ||
                "LOW CONFIDENCE"
              ).toUpperCase();
              const isNormal = rawStatus === "NORMAL";
              const isReview = rawStatus === "REVIEW";
              const displayStatus =
                rawStatus === "LOW_CONFIDENCE" ? "LOW CONFIDENCE" : rawStatus;

              const triggers =
                assess.triggered_features || assess.trigger_features || [];
              const featureLabels: Record<string, string> = {
                dominant_frequency_hz: "Freq",
                rms_displacement_px: "RMS Displacement",
                peak_to_median_db: "Peak Prominence",
                second_harmonic_ratio: "2x Harmonic Ratio",
              };

              const formatFeatureChip = (key: string) => {
                const dev = assess.deviations?.[key];
                if (dev) {
                  const ax = (dev.axis || "").toUpperCase();
                  const lbl =
                    featureLabels[dev.feature_name] || dev.feature_name;
                  const zPart =
                    dev.z_robust != null
                      ? ` (${dev.z_robust >= 0 ? "+" : ""}${dev.z_robust.toFixed(2)} z)`
                      : "";
                  return `${ax} ${lbl}${zPart}`.trim();
                }
                return key;
              };

              return (
                <div
                  data-testid="live-baseline-screening-card"
                  className={`p-3 rounded border font-mono text-xs flex flex-col gap-2 ${
                    isNormal
                      ? "bg-emerald-950/20 border-emerald-700/70 text-emerald-200"
                      : isReview
                      ? "bg-rose-950/30 border-rose-500 text-rose-200 animate-border-rose-pulse"
                      : "bg-amber-950/20 border-amber-700/70 text-amber-200"
                  }`}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <ShieldAlert
                        className={`w-4 h-4 shrink-0 ${
                          isNormal
                            ? "text-emerald-400"
                            : isReview
                            ? "text-rose-400"
                            : "text-amber-400"
                        }`}
                      />
                      <span className="font-bold text-white tracking-wide">
                        LIVE BASELINE SCREENING
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                          isNormal
                            ? "bg-emerald-950/70 text-emerald-400 border-emerald-600"
                            : isReview
                            ? "bg-rose-950/80 text-rose-300 border-rose-500"
                            : "bg-amber-950/70 text-amber-300 border-amber-600"
                        }`}
                      >
                        {displayStatus}
                      </span>
                    </div>
                    <span className="text-xs font-bold tabular-nums">
                      Max |z| ={" "}
                      {assess.max_z_score != null
                        ? assess.max_z_score.toFixed(2)
                        : "--"}
                    </span>
                  </div>

                  {triggers.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {triggers.map((featKey) => (
                        <span
                          key={featKey}
                          className="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-700/70 text-rose-200 text-[10px] tabular-nums"
                        >
                          {formatFeatureChip(featKey)}
                        </span>
                      ))}
                    </div>
                  )}

                  <p className="text-[10px] text-slate-400 leading-relaxed">
                    {assess.interpretation ||
                      "Statistical screening flag relative to healthy baseline — does not diagnose specific mechanical faults."}
                  </p>
                </div>
              );
            })()}

          {/* Live Oscilloscope Component */}
          <OscilloscopeCanvas
            samples={liveSamples}
            maxSamples={300}
            height={200}
            correlationResponse={rollingUpdate?.mean_target_response ?? null}
            anchorCorrelationResponse={rollingUpdate?.mean_anchor_response ?? null}
            resetKey={activeSessionId}
          />

          {/* Live Spectrum Plot Component */}
          <SpectrumPlot
            xMetrics={rollingUpdate?.x_metrics}
            yMetrics={rollingUpdate?.y_metrics}
            baselineFreqHz={
              activeBaseline?.x_baseline?.dominant_frequency_hz_median ??
              activeAsset?.active_baseline?.x_baseline?.dominant_frequency_hz_median ??
              null
            }
            baselineFreqY={
              activeBaseline?.y_baseline?.dominant_frequency_hz_median ??
              activeAsset?.active_baseline?.y_baseline?.dominant_frequency_hz_median ??
              null
            }
            height={200}
          />
        </div>
      </div>

      {/* Session Report Modal */}
      {showReportModal && latestReport && (
        <SessionReportModal
          report={latestReport}
          onClose={() => setShowReportModal(false)}
        />
      )}
    </div>
  );
};
