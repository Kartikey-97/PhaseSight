"use client";

import React, { useEffect, useRef, useState, useCallback } from "react";
import type { CheckROIsResult, ROI } from "@/lib/types";
import { api } from "@/lib/api";
import { API_BASE } from "@/lib/config";
import { Crosshair, Move, ShieldCheck, AlertTriangle } from "lucide-react";

interface RoiInteractiveCanvasProps {
  // Source inputs
  videoRef?: React.RefObject<HTMLVideoElement | null>;
  isCameraActive?: boolean;
  previewImageBase64?: string | null;
  mjpegSessionId?: string | null;
  nativeWidth: number;
  nativeHeight: number;

  // ROIs
  targetRoi: ROI;
  anchorRoi: ROI;
  onTargetRoiChange: (roi: ROI) => void;
  onAnchorRoiChange: (roi: ROI) => void;

  // Video context for server checks
  presetId?: string | null;
  uploadId?: string | null;
  isStreaming?: boolean;
  onTextureChange?: (stats: { targetStd: number | null; anchorStd: number | null }) => void;
}

type InteractionMode = "target" | "anchor" | "adjust";
type DragHandle = "tl" | "tr" | "bl" | "br" | "move" | null;

export const RoiInteractiveCanvas: React.FC<RoiInteractiveCanvasProps> = ({
  videoRef,
  isCameraActive = false,
  previewImageBase64,
  mjpegSessionId,
  nativeWidth,
  nativeHeight,
  targetRoi,
  anchorRoi,
  onTargetRoiChange,
  onAnchorRoiChange,
  presetId,
  uploadId,
  isStreaming = false,
  onTextureChange,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mjpegImgRef = useRef<HTMLImageElement>(null);

  const [mode, setMode] = useState<InteractionMode>("adjust");
  const [activeBox, setActiveBox] = useState<"target" | "anchor" | null>(null);
  const [activeHandle, setActiveHandle] = useState<DragHandle>(null);
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null);
  const [initialRoi, setInitialRoi] = useState<ROI | null>(null);

  // Live texture stats
  const [targetStd, setTargetStd] = useState<number | null>(null);
  const [anchorStd, setAnchorStd] = useState<number | null>(null);
  const [serverCheckResult, setServerCheckResult] = useState<CheckROIsResult | null>(null);
  const [isMjpegStalled, setIsMjpegStalled] = useState(false);

  useEffect(() => {
    onTextureChange?.({ targetStd, anchorStd });
  }, [targetStd, anchorStd, onTextureChange]);

  // MJPEG fallback polling
  useEffect(() => {
    if (!mjpegSessionId || !isStreaming) return;
    let pollTimer: NodeJS.Timeout | null = null;
    let stallCheckTimer = setTimeout(() => {
      setIsMjpegStalled(true);
    }, 3000);

    const img = mjpegImgRef.current;
    if (img) {
      img.onload = () => {
        clearTimeout(stallCheckTimer);
        setIsMjpegStalled(false);
      };
      img.onerror = () => {
        setIsMjpegStalled(true);
      };
    }

    if (isMjpegStalled) {
      pollTimer = setInterval(() => {
        if (img) {
          img.src = `${API_BASE}/api/v1/sessions/${mjpegSessionId}/frame.jpg?t=${Date.now()}`;
        }
      }, 250);
    }

    return () => {
      clearTimeout(stallCheckTimer);
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [mjpegSessionId, isStreaming, isMjpegStalled]);

  // Server-side ROI check on change for video replay / batch
  useEffect(() => {
    if (isStreaming || (!presetId && !uploadId)) return;
    let cancel = false;
    const timer = setTimeout(async () => {
      try {
        const res = await api.checkROIs({
          target_roi: targetRoi,
          anchor_roi: anchorRoi,
          preset_id: presetId,
          upload_id: uploadId,
        });
        if (!cancel) {
          setServerCheckResult(res);
          setTargetStd(res.target_texture_std ?? res.target_std ?? null);
          setAnchorStd(res.anchor_texture_std ?? res.anchor_std ?? null);
        }
      } catch (err) {
        // silent fail on network glitch
      }
    }, 300);

    return () => {
      cancel = true;
      clearTimeout(timer);
    };
  }, [targetRoi, anchorRoi, presetId, uploadId, isStreaming]);

  // Client-side real-time texture computation on webcam video
  useEffect(() => {
    if (isStreaming || !isCameraActive) return;
    const calcCanvas = document.createElement("canvas");
    const calcCtx = calcCanvas.getContext("2d", { willReadFrequently: true });
    if (!calcCtx) return;

    const interval = setInterval(() => {
      const video = videoRef?.current;
      if (!video || video.readyState < 2) return;
      calcCanvas.width = video.videoWidth || nativeWidth || 1280;
      calcCanvas.height = video.videoHeight || nativeHeight || 720;
      calcCtx.drawImage(video, 0, 0, calcCanvas.width, calcCanvas.height);

      const computeStd = (roi: ROI) => {
        const tw = Math.max(1, Math.floor(roi.width));
        const th = Math.max(1, Math.floor(roi.height));
        const imgData = calcCtx.getImageData(Math.floor(roi.x), Math.floor(roi.y), tw, th).data;
        let sum = 0;
        let sumSq = 0;
        const n = tw * th;
        for (let i = 0; i < imgData.length; i += 4) {
          const g = 0.299 * imgData[i] + 0.587 * imgData[i + 1] + 0.114 * imgData[i + 2];
          sum += g;
          sumSq += g * g;
        }
        const mean = sum / n;
        const variance = Math.max(0, sumSq / n - mean * mean);
        return Math.sqrt(variance);
      };

      setTargetStd(Math.round(computeStd(targetRoi) * 10) / 10);
      setAnchorStd(Math.round(computeStd(anchorRoi) * 10) / 10);
    }, 250);

    return () => clearInterval(interval);
  }, [videoRef, isCameraActive, nativeWidth, nativeHeight, targetRoi, anchorRoi, isStreaming]);

  // Coordinate transforms
  const getScale = useCallback(() => {
    if (!containerRef.current) return { scaleX: 1, scaleY: 1, width: 1, height: 1 };
    const rect = containerRef.current.getBoundingClientRect();
    const w = nativeWidth || 1280;
    const h = nativeHeight || 720;
    return {
      scaleX: rect.width / w,
      scaleY: rect.height / h,
      width: rect.width,
      height: rect.height,
    };
  }, [nativeWidth, nativeHeight]);

  const clientToNative = useCallback(
    (clientX: number, clientY: number) => {
      if (!containerRef.current) return { x: 0, y: 0 };
      const rect = containerRef.current.getBoundingClientRect();
      const clickX = clientX - rect.left;
      const clickY = clientY - rect.top;
      const { scaleX, scaleY } = getScale();
      const nativeX = Math.round(clickX / scaleX);
      const nativeY = Math.round(clickY / scaleY);
      return {
        x: Math.max(0, Math.min(nativeWidth || 1280, nativeX)),
        y: Math.max(0, Math.min(nativeHeight || 720, nativeY)),
      };
    },
    [getScale, nativeWidth, nativeHeight]
  );

  // Hit test handles or box
  const hitTest = useCallback(
    (x: number, y: number, roi: ROI): DragHandle => {
      const handleSize = 12 / (getScale().scaleX || 1);
      const { x: rx, y: ry, width: rw, height: rh } = roi;

      // Corners
      if (Math.abs(x - rx) <= handleSize && Math.abs(y - ry) <= handleSize) return "tl";
      if (Math.abs(x - (rx + rw)) <= handleSize && Math.abs(y - ry) <= handleSize) return "tr";
      if (Math.abs(x - rx) <= handleSize && Math.abs(y - (ry + rh)) <= handleSize) return "bl";
      if (Math.abs(x - (rx + rw)) <= handleSize && Math.abs(y - (ry + rh)) <= handleSize) return "br";

      // Inside box
      if (x >= rx && x <= rx + rw && y >= ry && y <= ry + rh) return "move";

      return null;
    },
    [getScale]
  );

  // Mouse handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (isStreaming) return;
    const pt = clientToNative(e.clientX, e.clientY);

    if (mode === "target" || mode === "anchor") {
      setActiveBox(mode);
      setActiveHandle("br");
      setDragStart(pt);
      const newRoi = { x: pt.x, y: pt.y, width: 32, height: 32 };
      setInitialRoi(newRoi);
      if (mode === "target") onTargetRoiChange(newRoi);
      else onAnchorRoiChange(newRoi);
      return;
    }

    // Adjust mode: check target handles then anchor handles
    const tHandle = hitTest(pt.x, pt.y, targetRoi);
    if (tHandle) {
      setActiveBox("target");
      setActiveHandle(tHandle);
      setDragStart(pt);
      setInitialRoi({ ...targetRoi });
      return;
    }

    const aHandle = hitTest(pt.x, pt.y, anchorRoi);
    if (aHandle) {
      setActiveBox("anchor");
      setActiveHandle(aHandle);
      setDragStart(pt);
      setInitialRoi({ ...anchorRoi });
      return;
    }

    setActiveBox(null);
    setActiveHandle(null);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!activeBox || !activeHandle || !dragStart || !initialRoi || isStreaming) return;
    const pt = clientToNative(e.clientX, e.clientY);
    const dx = pt.x - dragStart.x;
    const dy = pt.y - dragStart.y;

    const nw = nativeWidth || 1280;
    const nh = nativeHeight || 720;
    let nextRoi: ROI = { ...initialRoi };

    if (mode === "target" || mode === "anchor") {
      const left = Math.min(dragStart.x, pt.x);
      const top = Math.min(dragStart.y, pt.y);
      const w = Math.max(32, Math.abs(pt.x - dragStart.x));
      const h = Math.max(32, Math.abs(pt.y - dragStart.y));
      nextRoi = {
        x: Math.max(0, Math.min(nw - w, left)),
        y: Math.max(0, Math.min(nh - h, top)),
        width: Math.min(w, nw - left),
        height: Math.min(h, nh - top),
      };
    } else if (activeHandle === "move") {
      nextRoi = {
        x: Math.max(0, Math.min(nw - initialRoi.width, initialRoi.x + dx)),
        y: Math.max(0, Math.min(nh - initialRoi.height, initialRoi.y + dy)),
        width: initialRoi.width,
        height: initialRoi.height,
      };
    } else {
      // Corner resize
      let nx = initialRoi.x;
      let ny = initialRoi.y;
      let nwBox = initialRoi.width;
      let nhBox = initialRoi.height;

      if (activeHandle === "br") {
        nwBox = Math.max(32, Math.min(nw - nx, initialRoi.width + dx));
        nhBox = Math.max(32, Math.min(nh - ny, initialRoi.height + dy));
      } else if (activeHandle === "tl") {
        const potentialX = Math.max(0, initialRoi.x + dx);
        const potentialY = Math.max(0, initialRoi.y + dy);
        nwBox = Math.max(32, initialRoi.x + initialRoi.width - potentialX);
        nhBox = Math.max(32, initialRoi.y + initialRoi.height - potentialY);
        nx = initialRoi.x + initialRoi.width - nwBox;
        ny = initialRoi.y + initialRoi.height - nhBox;
      } else if (activeHandle === "tr") {
        const potentialY = Math.max(0, initialRoi.y + dy);
        nwBox = Math.max(32, Math.min(nw - nx, initialRoi.width + dx));
        nhBox = Math.max(32, initialRoi.y + initialRoi.height - potentialY);
        ny = initialRoi.y + initialRoi.height - nhBox;
      } else if (activeHandle === "bl") {
        const potentialX = Math.max(0, initialRoi.x + dx);
        nwBox = Math.max(32, initialRoi.x + initialRoi.width - potentialX);
        nhBox = Math.max(32, Math.min(nh - ny, initialRoi.height + dy));
        nx = initialRoi.x + initialRoi.width - nwBox;
      }

      nextRoi = {
        x: Math.round(nx),
        y: Math.round(ny),
        width: Math.round(nwBox),
        height: Math.round(nhBox),
      };
    }

    if (activeBox === "target") onTargetRoiChange(nextRoi);
    else onAnchorRoiChange(nextRoi);
  };

  const handleMouseUp = () => {
    setActiveBox(null);
    setActiveHandle(null);
    setDragStart(null);
    setInitialRoi(null);
    if (mode === "target" || mode === "anchor") {
      setMode("adjust");
    }
  };

  // Render canvas overlay (corner brackets, labels, crosshairs)
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const { scaleX, scaleY, width, height } = getScale();
    if (width <= 0 || height <= 0) return;
    const dpr = window.devicePixelRatio || 1;

    const targetW = Math.round(width * dpr);
    const targetH = Math.round(height * dpr);

    if (canvas.width !== targetW || canvas.height !== targetH) {
      canvas.width = targetW;
      canvas.height = targetH;
    }

    ctx.save();
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, width, height);

    const drawBox = (
      roi: ROI,
      color: string,
      label: string,
      stdVal: number | null,
      isActive: boolean
    ) => {
      const rx = roi.x * scaleX;
      const ry = roi.y * scaleY;
      const rw = roi.width * scaleX;
      const rh = roi.height * scaleY;

      // Fill tint
      ctx.fillStyle = isActive
        ? color === "#22D3EE"
          ? "rgba(34, 211, 238, 0.12)"
          : "rgba(245, 158, 11, 0.12)"
        : "rgba(0, 0, 0, 0.15)";
      ctx.fillRect(rx, ry, rw, rh);

      // Boundary box
      ctx.strokeStyle = color;
      ctx.lineWidth = isActive ? 2 : 1.5;
      ctx.strokeRect(rx, ry, rw, rh);

      // HUD corner brackets
      const blen = Math.min(10, rw / 4, rh / 4);
      ctx.lineWidth = 2.5;
      // TL
      ctx.beginPath();
      ctx.moveTo(rx, ry + blen);
      ctx.lineTo(rx, ry);
      ctx.lineTo(rx + blen, ry);
      ctx.stroke();
      // TR
      ctx.beginPath();
      ctx.moveTo(rx + rw - blen, ry);
      ctx.lineTo(rx + rw, ry);
      ctx.lineTo(rx + rw, ry + blen);
      ctx.stroke();
      // BL
      ctx.beginPath();
      ctx.moveTo(rx, ry + rh - blen);
      ctx.lineTo(rx, ry + rh);
      ctx.lineTo(rx + blen, ry + rh);
      ctx.stroke();
      // BR
      ctx.beginPath();
      ctx.moveTo(rx + rw - blen, ry + rh);
      ctx.lineTo(rx + rw, ry + rh);
      ctx.lineTo(rx + rw, ry + rh - blen);
      ctx.stroke();

      // Center crosshair
      const cx = rx + rw / 2;
      const cy = ry + rh / 2;
      ctx.lineWidth = 1;
      ctx.strokeStyle = color;
      ctx.beginPath();
      ctx.moveTo(cx - 5, cy);
      ctx.lineTo(cx + 5, cy);
      ctx.moveTo(cx, cy - 5);
      ctx.lineTo(cx, cy + 5);
      ctx.stroke();

      // Label badge
      ctx.font = "10px var(--font-mono)";
      const stdText = typeof stdVal === "number" && !isNaN(stdVal) ? ` σ=${stdVal.toFixed(1)}` : "";
      const text = `${label} [${roi.x},${roi.y} ${roi.width}×${roi.height}]${stdText}`;
      const textWidth = ctx.measureText(text).width;
      const badgeH = 16;
      const badgeY = ry > 20 ? ry - badgeH - 2 : ry + 2;

      ctx.fillStyle = "rgba(7, 10, 15, 0.85)";
      ctx.fillRect(rx, badgeY, textWidth + 8, badgeH);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.strokeRect(rx, badgeY, textWidth + 8, badgeH);

      ctx.fillStyle = color;
      ctx.fillText(text, rx + 4, badgeY + 11);

      // Corner drag handles (in adjust mode)
      if (!isStreaming) {
        const handleR = 3.5;
        const corners = [
          [rx, ry],
          [rx + rw, ry],
          [rx, ry + rh],
          [rx + rw, ry + rh],
        ];
        ctx.fillStyle = color;
        corners.forEach(([hx, hy]) => {
          ctx.beginPath();
          ctx.arc(hx, hy, handleR, 0, Math.PI * 2);
          ctx.fill();
        });
      }
    };

    drawBox(
      targetRoi,
      "#22D3EE",
      "TARGET",
      targetStd,
      activeBox === "target" || mode === "target"
    );
    drawBox(
      anchorRoi,
      "#F59E0B",
      "ANCHOR",
      anchorStd,
      activeBox === "anchor" || mode === "anchor"
    );
    ctx.restore();
  }, [
    targetRoi,
    anchorRoi,
    targetStd,
    anchorStd,
    activeBox,
    mode,
    getScale,
    isStreaming,
  ]);

  return (
    <div className="flex flex-col gap-2">
      {/* Top mode bar */}
      <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 bg-[#0D121A] border border-[rgba(255,255,255,0.08)] rounded text-xs">
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            disabled={isStreaming}
            onClick={() => setMode("target")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded font-medium transition ${
              mode === "target"
                ? "bg-[#22D3EE]/20 text-[#22D3EE] border border-[#22D3EE]"
                : "text-slate-300 hover:bg-white/5 border border-transparent"
            } disabled:opacity-40`}
          >
            <Crosshair className="w-3.5 h-3.5" />
            Draw Target (Cyan)
          </button>
          <button
            type="button"
            disabled={isStreaming}
            onClick={() => setMode("anchor")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded font-medium transition ${
              mode === "anchor"
                ? "bg-[#F59E0B]/20 text-[#F59E0B] border border-[#F59E0B]"
                : "text-slate-300 hover:bg-white/5 border border-transparent"
            } disabled:opacity-40`}
          >
            <Crosshair className="w-3.5 h-3.5" />
            Draw Anchor (Amber)
          </button>
          <button
            type="button"
            disabled={isStreaming}
            onClick={() => setMode("adjust")}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded font-medium transition ${
              mode === "adjust"
                ? "bg-slate-700 text-white border border-slate-500"
                : "text-slate-400 hover:bg-white/5 border border-transparent"
            } disabled:opacity-40`}
          >
            <Move className="w-3.5 h-3.5" />
            Adjust
          </button>
        </div>

        {/* Validation badges */}
        <div className="flex items-center gap-2 font-mono">
          {typeof targetStd === "number" && !isNaN(targetStd) && (
            <span
              className={`flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] ${
                targetStd >= 2.0
                  ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                  : "bg-rose-950/40 text-rose-400 border-rose-800"
              }`}
            >
              {targetStd >= 2.0 ? (
                <ShieldCheck className="w-3 h-3" />
              ) : (
                <AlertTriangle className="w-3 h-3" />
              )}
              Tgt σ={targetStd.toFixed(1)} {targetStd < 2.0 && "Low"}
            </span>
          )}
          {typeof anchorStd === "number" && !isNaN(anchorStd) && (
            <span
              className={`flex items-center gap-1 px-2 py-0.5 rounded border text-[11px] ${
                anchorStd >= 2.0
                  ? "bg-emerald-950/40 text-emerald-400 border-emerald-800"
                  : "bg-rose-950/40 text-rose-400 border-rose-800"
              }`}
            >
              {anchorStd >= 2.0 ? (
                <ShieldCheck className="w-3 h-3" />
              ) : (
                <AlertTriangle className="w-3 h-3" />
              )}
              Anc σ={anchorStd.toFixed(1)} {anchorStd < 2.0 && "Low"}
            </span>
          )}
        </div>
      </div>

      {/* Main viewport canvas stack */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        className="relative w-full aspect-video bg-[#070A0F] border border-[rgba(255,255,255,0.08)] rounded overflow-hidden select-none cursor-crosshair"
      >
        {/* Underlay: Webcam Video */}
        {videoRef && (
          <video
            ref={videoRef}
            playsInline
            muted
            autoPlay
            className={`absolute inset-0 w-full h-full object-contain pointer-events-none z-0 ${
              isCameraActive ? "block" : "hidden"
            }`}
          />
        )}

        {/* Underlay: Video Replay or Image Preview */}
        {isStreaming && mjpegSessionId ? (
          <img
            ref={mjpegImgRef}
            src={`${API_BASE}/api/v1/sessions/${mjpegSessionId}/mjpeg`}
            alt="Live Replay Stream"
            className="absolute inset-0 w-full h-full object-contain pointer-events-none z-0"
          />
        ) : previewImageBase64 ? (
          <img
            src={
              previewImageBase64.startsWith("data:")
                ? previewImageBase64
                : `data:image/png;base64,${previewImageBase64}`
            }
            alt="Preview Frame 0"
            className="absolute inset-0 w-full h-full object-contain pointer-events-none z-0"
          />
        ) : !isCameraActive ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center text-slate-500 font-mono text-xs z-0">
            <span>NO VIDEO FEED CONNECTED</span>
            <span className="text-[10px] text-slate-600">
              Select a preset or start webcam
            </span>
          </div>
        ) : null}

        {/* Overlay Canvas */}
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full pointer-events-none z-10"
        />
      </div>

      {/* Two-way Numeric ROI Inputs */}
      <div className="grid grid-cols-2 gap-3 text-xs font-mono">
        {/* Target ROI Inputs */}
        <div className="p-2.5 bg-[#0D121A] border border-[#22D3EE]/30 rounded flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-[#22D3EE] font-semibold">
            <span>TARGET ROI (CYAN)</span>
            <span className="text-[10px] text-slate-400">
              {targetRoi.width}×{targetRoi.height} px
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            <div>
              <label className="text-[10px] text-slate-400">X</label>
              <input
                type="number"
                data-testid="target-roi-x"
                disabled={isStreaming}
                value={targetRoi.x}
                onChange={(e) =>
                  onTargetRoiChange({ ...targetRoi, x: Number(e.target.value) })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">Y</label>
              <input
                type="number"
                data-testid="target-roi-y"
                disabled={isStreaming}
                value={targetRoi.y}
                onChange={(e) =>
                  onTargetRoiChange({ ...targetRoi, y: Number(e.target.value) })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">W</label>
              <input
                type="number"
                data-testid="target-roi-w"
                disabled={isStreaming}
                min={32}
                value={targetRoi.width}
                onChange={(e) =>
                  onTargetRoiChange({
                    ...targetRoi,
                    width: Math.max(32, Number(e.target.value)),
                  })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">H</label>
              <input
                type="number"
                data-testid="target-roi-h"
                disabled={isStreaming}
                min={32}
                value={targetRoi.height}
                onChange={(e) =>
                  onTargetRoiChange({
                    ...targetRoi,
                    height: Math.max(32, Number(e.target.value)),
                  })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
          </div>
        </div>

        {/* Anchor ROI Inputs */}
        <div className="p-2.5 bg-[#0D121A] border border-[#F59E0B]/30 rounded flex flex-col gap-1.5">
          <div className="flex items-center justify-between text-[#F59E0B] font-semibold">
            <span>ANCHOR ROI (AMBER)</span>
            <span className="text-[10px] text-slate-400">
              {anchorRoi.width}×{anchorRoi.height} px
            </span>
          </div>
          <div className="grid grid-cols-4 gap-1.5">
            <div>
              <label className="text-[10px] text-slate-400">X</label>
              <input
                type="number"
                data-testid="anchor-roi-x"
                disabled={isStreaming}
                value={anchorRoi.x}
                onChange={(e) =>
                  onAnchorRoiChange({ ...anchorRoi, x: Number(e.target.value) })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">Y</label>
              <input
                type="number"
                data-testid="anchor-roi-y"
                disabled={isStreaming}
                value={anchorRoi.y}
                onChange={(e) =>
                  onAnchorRoiChange({ ...anchorRoi, y: Number(e.target.value) })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">W</label>
              <input
                type="number"
                data-testid="anchor-roi-w"
                disabled={isStreaming}
                min={32}
                value={anchorRoi.width}
                onChange={(e) =>
                  onAnchorRoiChange({
                    ...anchorRoi,
                    width: Math.max(32, Number(e.target.value)),
                  })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
            <div>
              <label className="text-[10px] text-slate-400">H</label>
              <input
                type="number"
                data-testid="anchor-roi-h"
                disabled={isStreaming}
                min={32}
                value={anchorRoi.height}
                onChange={(e) =>
                  onAnchorRoiChange({
                    ...anchorRoi,
                    height: Math.max(32, Number(e.target.value)),
                  })
                }
                className="w-full bg-[#131B26] border border-white/10 rounded px-1.5 py-0.5 text-slate-200"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
