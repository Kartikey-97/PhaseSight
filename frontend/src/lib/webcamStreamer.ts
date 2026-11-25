import { WS_BASE } from "./config";
import type { ROI } from "./types";

export interface WebcamInfo {
  deviceId: string;
  label: string;
  width: number;
  height: number;
  frameRate: number;
}

export class WebcamStreamer {
  private stream: MediaStream | null = null;
  private videoEl: HTMLVideoElement | null = null;
  private ws: WebSocket | null = null;
  private offscreenCanvas: HTMLCanvasElement;
  private offscreenCtx: CanvasRenderingContext2D;
  private isStreaming = false;
  private seq = 0;
  private recalibrateRequested = false;
  private animFrameId: number | null = null;
  private videoCallbackId: number | null = null;
  private targetRoi: ROI | null = null;
  private anchorRoi: ROI | null = null;
  private sessionId: string | null = null;

  // Single-pump & monotonic timestamp tracking
  private clockMode: "unresolved" | "mediaTime" | "performanceNow" = "unresolved";
  private probeMediaTime: number | null = null;
  private lastSentMediaTime = -1;
  private lastSentTimestamp = -1;
  private lastRvfTime = 0;
  private watchdogIntervalId: any = null;

  public onStatsUpdate?: (stats: {
    fps: number;
    droppedFrames: number;
    bufferedAmount: number;
  }) => void;
  public onError?: (error: Error) => void;

  private frameCount = 0;
  private lastStatsTime = performance.now();
  private droppedFrames = 0;

  constructor() {
    this.offscreenCanvas = document.createElement("canvas");
    const ctx = this.offscreenCanvas.getContext("2d", { willReadFrequently: true });
    if (!ctx) throw new Error("Could not create 2D canvas context");
    this.offscreenCtx = ctx;
  }

  async openCamera(deviceId?: string): Promise<MediaStream> {
    this.stopCamera();

    const constraints: MediaStreamConstraints = {
      audio: false,
      video: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        width: { ideal: 1280 },
        height: { ideal: 720 },
        frameRate: { ideal: 60 },
      },
    };

    try {
      this.stream = await navigator.mediaDevices.getUserMedia(constraints);
      return this.stream;
    } catch (err: any) {
      let friendly = err.message || "Could not access camera";
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        friendly = "Camera access denied. Please grant permission in browser settings.";
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        friendly = "No camera found on this device.";
      } else if (err.name === "NotReadableError" || err.name === "TrackStartError") {
        friendly = "Camera is currently locked by another application.";
      }
      const wrapped = new Error(friendly);
      this.onError?.(wrapped);
      throw wrapped;
    }
  }

  attachVideoElement(video: HTMLVideoElement) {
    this.videoEl = video;
    if (this.stream) {
      video.srcObject = this.stream;
      video.play().catch(() => {});
    }
  }

  getTrackSettings(): WebcamInfo | null {
    if (!this.stream) return null;
    const track = this.stream.getVideoTracks()[0];
    if (!track) return null;
    const s = track.getSettings();
    return {
      deviceId: s.deviceId || "",
      label: track.label || "Default Camera",
      width: s.width || 1280,
      height: s.height || 720,
      frameRate: s.frameRate || 30,
    };
  }

  startStreaming(sessionId: string, targetRoi: ROI, anchorRoi: ROI) {
    if (!this.stream || !this.videoEl) {
      throw new Error("Camera not initialized");
    }

    this.sessionId = sessionId;
    this.targetRoi = targetRoi;
    this.anchorRoi = anchorRoi;
    this.seq = 0;
    this.droppedFrames = 0;
    this.frameCount = 0;
    this.lastStatsTime = performance.now();
    this.clockMode = "unresolved";
    this.probeMediaTime = null;
    this.lastSentMediaTime = -1;
    this.lastSentTimestamp = -1;
    this.lastRvfTime = performance.now();

    const wsUrl = `${WS_BASE}/ws/v1/sessions/${sessionId}/ingest`;
    this.ws = new WebSocket(wsUrl);
    this.ws.binaryType = "arraybuffer";

    this.ws.onopen = () => {
      this.isStreaming = true;
      this.scheduleNextFrame();
    };

    this.ws.onerror = (e) => {
      this.onError?.(new Error("Webcam WebSocket error"));
    };

    this.ws.onclose = () => {
      this.isStreaming = false;
      this.clearWatchdog();
    };
  }

  updateROIs(targetRoi: ROI, anchorRoi: ROI) {
    this.targetRoi = targetRoi;
    this.anchorRoi = anchorRoi;
  }

  triggerNextFrameRecalibrate() {
    this.recalibrateRequested = true;
  }

  private clearWatchdog() {
    if (this.watchdogIntervalId !== null) {
      clearInterval(this.watchdogIntervalId);
      this.watchdogIntervalId = null;
    }
  }

  private scheduleNextFrame() {
    if (!this.isStreaming || !this.videoEl) return;

    if ("requestVideoFrameCallback" in this.videoEl) {
      this.videoCallbackId = (this.videoEl as any).requestVideoFrameCallback(
        (now: number, metadata: any) => {
          this.videoCallbackId = null;
          this.lastRvfTime = performance.now();
          this.handleFrameDelivery(now, metadata);
          if (this.isStreaming) {
            this.scheduleNextFrame();
          }
        }
      );

      // Single active pump: only trigger fallback if requestVideoFrameCallback hasn't fired for >500ms
      if (!this.watchdogIntervalId) {
        this.watchdogIntervalId = setInterval(() => {
          if (!this.isStreaming) {
            this.clearWatchdog();
            return;
          }
          if (performance.now() - this.lastRvfTime > 500) {
            this.handleFrameDelivery(performance.now(), null);
          }
        }, 200);
      }
    } else {
      this.animFrameId = requestAnimationFrame((now: number) => {
        this.animFrameId = null;
        this.handleFrameDelivery(now, null);
        if (this.isStreaming) {
          this.scheduleNextFrame();
        }
      });
    }
  }

  private handleFrameDelivery(now: number, metadata?: any) {
    if (!this.isStreaming || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;

    let timestamp: number;

    if (this.clockMode === "unresolved") {
      const mt = metadata?.mediaTime;
      if (typeof mt === "number" && Number.isFinite(mt)) {
        if (this.probeMediaTime === null) {
          // Hold 1 frame to verify whether metadata.mediaTime advances monotonically or stays frozen at 0
          this.probeMediaTime = mt;
          return;
        }
        if (mt > this.probeMediaTime + 1e-6) {
          this.clockMode = "mediaTime";
          this.lastSentMediaTime = this.probeMediaTime;
        } else {
          this.clockMode = "performanceNow";
        }
      } else {
        this.clockMode = "performanceNow";
      }
    }

    if (this.clockMode === "mediaTime") {
      const mt = metadata?.mediaTime;
      // Deduplicate identical metadata.mediaTime (skip if mediaTime <= lastSentMediaTime + 1e-6)
      if (typeof mt !== "number" || !Number.isFinite(mt) || mt <= this.lastSentMediaTime + 1e-6) {
        return;
      }
      this.lastSentMediaTime = mt;
      timestamp = mt;
    } else {
      // performanceNow clock mode (monotonically advancing)
      const t = now / 1000.0;
      if (t <= this.lastSentTimestamp) {
        timestamp = this.lastSentTimestamp + 1e-4;
      } else {
        timestamp = t;
      }
    }

    this.lastSentTimestamp = timestamp;
    this.processFrame(timestamp);
  }

  private processFrame(mediaTime: number) {
    if (!this.isStreaming || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    if (!this.videoEl || !this.targetRoi || !this.anchorRoi) return;

    // Flow control: drop frame locally if client buffer exceeds 1 MB
    if (this.ws.bufferedAmount > 1048576) {
      this.droppedFrames++;
      return;
    }

    const tx = Math.max(0, Math.floor(this.targetRoi.x));
    const ty = Math.max(0, Math.floor(this.targetRoi.y));
    const tw = Math.floor(this.targetRoi.width);
    const th = Math.floor(this.targetRoi.height);
    const ax = Math.max(0, Math.floor(this.anchorRoi.x));
    const ay = Math.max(0, Math.floor(this.anchorRoi.y));
    const aw = Math.floor(this.anchorRoi.width);
    const ah = Math.floor(this.anchorRoi.height);

    if (tw <= 0 || th <= 0 || aw <= 0 || ah <= 0) return;

    const minX = Math.min(tx, ax);
    const minY = Math.min(ty, ay);
    const maxX = Math.max(tx + tw, ax + aw);
    const maxY = Math.max(ty + th, ay + ah);
    const spanW = maxX - minX;
    const spanH = maxY - minY;

    // Resize canvas only when needed
    if (this.offscreenCanvas.width < spanW || this.offscreenCanvas.height < spanH) {
      this.offscreenCanvas.width = Math.max(this.offscreenCanvas.width, spanW);
      this.offscreenCanvas.height = Math.max(this.offscreenCanvas.height, spanH);
    }

    // Single drawImage + single getImageData readback covering both Target and Anchor ROIs
    this.offscreenCtx.drawImage(
      this.videoEl,
      minX,
      minY,
      spanW,
      spanH,
      0,
      0,
      spanW,
      spanH
    );
    const spanData = this.offscreenCtx.getImageData(0, 0, spanW, spanH).data;

    const targetGray = new Uint8Array(tw * th);
    const txOff = tx - minX;
    const tyOff = ty - minY;
    for (let row = 0; row < th; row++) {
      let srcIdx = ((tyOff + row) * spanW + txOff) * 4;
      let dstIdx = row * tw;
      for (let col = 0; col < tw; col++, srcIdx += 4, dstIdx++) {
        targetGray[dstIdx] = Math.round(
          0.299 * spanData[srcIdx] +
          0.587 * spanData[srcIdx + 1] +
          0.114 * spanData[srcIdx + 2]
        );
      }
    }

    const anchorGray = new Uint8Array(aw * ah);
    const axOff = ax - minX;
    const ayOff = ay - minY;
    for (let row = 0; row < ah; row++) {
      let srcIdx = ((ayOff + row) * spanW + axOff) * 4;
      let dstIdx = row * aw;
      for (let col = 0; col < aw; col++, srcIdx += 4, dstIdx++) {
        anchorGray[dstIdx] = Math.round(
          0.299 * spanData[srcIdx] +
          0.587 * spanData[srcIdx + 1] +
          0.114 * spanData[srcIdx + 2]
        );
      }
    }

    // 3. Assemble binary packet: 24-byte header + target + anchor
    const totalBytes = 24 + targetGray.length + anchorGray.length;
    const buffer = new ArrayBuffer(totalBytes);
    const view = new DataView(buffer);
    const payload = new Uint8Array(buffer);

    let flags = 0;
    if (this.recalibrateRequested) {
      flags |= 1; // bit 0 = recalibrate reference
      this.recalibrateRequested = false;
    }

    // Header layout: <dIHHHHI
    view.setFloat64(0, mediaTime, true);
    view.setUint32(8, this.seq++, true);
    view.setUint16(12, tw, true);
    view.setUint16(14, th, true);
    view.setUint16(16, aw, true);
    view.setUint16(18, ah, true);
    view.setUint32(20, flags, true);

    payload.set(targetGray, 24);
    payload.set(anchorGray, 24 + targetGray.length);

    try {
      this.ws.send(buffer);
      this.frameCount++;
    } catch (e) {
      this.droppedFrames++;
    }

    const now = performance.now();
    if (now - this.lastStatsTime >= 1000) {
      const dt = (now - this.lastStatsTime) / 1000;
      this.onStatsUpdate?.({
        fps: Math.round((this.frameCount / dt) * 10) / 10,
        droppedFrames: this.droppedFrames,
        bufferedAmount: this.ws.bufferedAmount,
      });
      this.frameCount = 0;
      this.lastStatsTime = now;
    }
  }

  stopStreaming() {
    this.isStreaming = false;
    this.clearWatchdog();
    if (this.videoCallbackId !== null && this.videoEl && "cancelVideoFrameCallback" in this.videoEl) {
      try {
        (this.videoEl as any).cancelVideoFrameCallback(this.videoCallbackId);
      } catch {}
      this.videoCallbackId = null;
    }
    if (this.animFrameId !== null) {
      cancelAnimationFrame(this.animFrameId);
      this.animFrameId = null;
    }
    if (this.ws) {
      try {
        this.ws.close();
      } catch {}
      this.ws = null;
    }
  }

  stopCamera() {
    this.stopStreaming();
    if (this.stream) {
      this.stream.getTracks().forEach((t) => t.stop());
      this.stream = null;
    }
    if (this.videoEl) {
      this.videoEl.srcObject = null;
    }
  }
}
