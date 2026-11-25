import { useEffect, useRef, useState, useCallback } from "react";
import { WS_BASE } from "./config";
import type {
  RollingUpdate,
  SessionReport,
  TelemetrySnapshot,
  TraceSample,
} from "./types";

interface UseTelemetrySocketOptions {
  sessionId: string | null;
  onSnapshot?: (snapshot: TelemetrySnapshot) => void;
  onTraceBatch?: (samples: TraceSample[]) => void;
  onRollingUpdate?: (update: RollingUpdate) => void;
  onSessionEnded?: (report?: SessionReport) => void;
  onError?: (err: Event | Error) => void;
}

export function normalizeTraceSample(s: any): TraceSample {
  const t = s.t ?? s.timestamp_s ?? 0;
  const rel_dx_px = s.rel_dx_px ?? s.relative_dx_px ?? 0;
  const rel_dy_px = s.rel_dy_px ?? s.relative_dy_px ?? 0;
  const target_corr = s.target_corr ?? s.target_response ?? 0.8;
  const anchor_corr = s.anchor_corr ?? s.anchor_response ?? 0.8;
  const raw_target_dx = s.raw_target_dx ?? s.target_dx_px ?? 0;
  const raw_target_dy = s.raw_target_dy ?? s.target_dy_px ?? 0;
  const raw_anchor_dx = s.raw_anchor_dx ?? s.anchor_dx_px ?? 0;
  const raw_anchor_dy = s.raw_anchor_dy ?? s.anchor_dy_px ?? 0;
  return {
    t: Number(t),
    rel_dx_px: isNaN(Number(rel_dx_px)) ? 0 : Number(rel_dx_px),
    rel_dy_px: isNaN(Number(rel_dy_px)) ? 0 : Number(rel_dy_px),
    target_corr: Number(target_corr),
    anchor_corr: Number(anchor_corr),
    raw_target_dx: Number(raw_target_dx),
    raw_target_dy: Number(raw_target_dy),
    raw_anchor_dx: Number(raw_anchor_dx),
    raw_anchor_dy: Number(raw_anchor_dy),
  };
}

function normalizeRollingUpdate(data: any, sessionId: string): RollingUpdate {
  const xMetrics = data.x_metrics || (data.x_axis ? {
    ...data.x_axis,
    frequencies: data.frequencies_hz,
    psd: data.x_psd,
    nyquist_hz: data.nyquist_hz,
    usable_max_hz: data.usable_max_hz,
  } : null);

  const yMetrics = data.y_metrics || (data.y_axis ? {
    ...data.y_axis,
    frequencies: data.frequencies_hz,
    psd: data.y_psd,
    nyquist_hz: data.nyquist_hz,
    usable_max_hz: data.usable_max_hz,
  } : null);

  const req = data.required_warmup_samples ?? 512;
  const filled = data.buffer_filled ?? (typeof data.warmup_progress === "object" ? data.warmup_progress?.filled_samples : 0) ?? 0;
  const pct = typeof data.warmup_progress === "object" && data.warmup_progress?.percentage != null
    ? data.warmup_progress.percentage
    : typeof data.warmup_progress === "number"
    ? Math.round(data.warmup_progress * 100)
    : req > 0
    ? Math.min(100, Math.round((filled / req) * 100))
    : 100;

  const warmupProgress = {
    filled_samples: filled,
    required_samples: req,
    percentage: pct,
  };

  let baselineAssessment = null;
  if (data.baseline_assessment) {
    const rawBa = data.baseline_assessment;
    const status = (rawBa.overall_status || rawBa.status || "NORMAL").toUpperCase();
    const triggerFeatures = rawBa.triggered_features || rawBa.trigger_features || [];
    let maxZ = rawBa.max_z_score;
    if (maxZ === undefined && rawBa.deviations) {
      maxZ = 0;
      for (const dev of Object.values(rawBa.deviations) as any[]) {
        const z = Math.abs(dev.z_robust ?? dev.z_score ?? 0);
        if (z > maxZ) maxZ = z;
      }
    }
    baselineAssessment = {
      ...rawBa,
      status: rawBa.status || status,
      overall_status: status,
      max_z_score: maxZ ?? 0,
      triggered_features: triggerFeatures,
      trigger_features: triggerFeatures,
    };
  }

  return {
    message_type: "rolling_update",
    session_id: data.session_id || sessionId,
    seq: data.seq || 0,
    state: data.state || "BUFFERING",
    warmup_progress: warmupProgress,
    measured_fps: data.measured_fps,
    timebase_source: data.timebase_source,
    timing_status: data.timing_status,
    jitter_ratio: data.jitter_ratio,
    dropped_frames: data.dropped_frames,
    x_metrics: xMetrics,
    y_metrics: yMetrics,
    baseline_assessment: baselineAssessment,
    warnings: data.warnings || [],
    timestamp: Date.now(),
  };
}

export function useTelemetrySocket({
  sessionId,
  onSnapshot,
  onTraceBatch,
  onRollingUpdate,
  onSessionEnded,
  onError,
}: UseTelemetrySocketOptions) {
  const [isConnected, setIsConnected] = useState(false);
  const [latestUpdate, setLatestUpdate] = useState<RollingUpdate | null>(null);
  const [latestSamples, setLatestSamples] = useState<TraceSample[]>([]);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const callbacksRef = useRef({
    onSnapshot,
    onTraceBatch,
    onRollingUpdate,
    onSessionEnded,
    onError,
  });
  callbacksRef.current = {
    onSnapshot,
    onTraceBatch,
    onRollingUpdate,
    onSessionEnded,
    onError,
  };

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
    setIsConnected(false);
  }, []);

  useEffect(() => {
    // Immediately clean up previous socket and reset stale telemetry state
    cleanup();
    setLatestUpdate(null);
    setLatestSamples([]);

    if (!sessionId) {
      return;
    }

    let isSubscribed = true;

    function connect() {
      if (!sessionId || !isSubscribed) return;
      const url = `${WS_BASE}/ws/v1/sessions/${sessionId}/telemetry`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isSubscribed) return;
        setIsConnected(true);
      };

      ws.onmessage = (event) => {
        if (!isSubscribed) return;
        try {
          const data = JSON.parse(event.data);
          const msgType = data.type || data.message_type;

          if (msgType === "snapshot") {
            const raw = (data.latest_update || data) as any;
            const normalized = normalizeRollingUpdate(raw, sessionId);
            setLatestUpdate(normalized);
            const normalizedSamples = (data.recent_samples || []).map(normalizeTraceSample);
            if (normalizedSamples.length) {
              setLatestSamples(normalizedSamples);
            }
            callbacksRef.current.onSnapshot?.({
              message_type: "snapshot",
              type: "snapshot",
              session_id: sessionId,
              state: data.state || "ACTIVE",
              source_type: data.source_type || "unknown",
              target_roi: data.target_roi,
              anchor_roi: data.anchor_roi,
              latest_update: normalized,
              recent_samples: normalizedSamples,
            });
          } else if (msgType === "trace_batch") {
            const batch = ((data.samples || []) as any[]).map(normalizeTraceSample);
            if (batch?.length) {
              setLatestSamples(batch);
              callbacksRef.current.onTraceBatch?.(batch);
            }
          } else if (msgType === "rolling_update") {
            const normalizedUpdate = normalizeRollingUpdate(data, sessionId);
            setLatestUpdate(normalizedUpdate);
            callbacksRef.current.onRollingUpdate?.(normalizedUpdate);
          } else if (msgType === "session_ended") {
            callbacksRef.current.onSessionEnded?.(data.report);
          }
        } catch (err) {
          console.error("Telemetry message parse error:", err);
        }
      };

      ws.onerror = (e) => {
        if (!isSubscribed) return;
        callbacksRef.current.onError?.(e);
      };

      ws.onclose = () => {
        if (!isSubscribed) return;
        setIsConnected(false);
        // Attempt reconnect if session still mounted
        reconnectTimeoutRef.current = setTimeout(() => {
          if (isSubscribed) connect();
        }, 2000);
      };
    }

    connect();

    return () => {
      isSubscribed = false;
      cleanup();
    };
  }, [sessionId, cleanup]);

  return {
    isConnected,
    latestUpdate,
    latestSamples,
    disconnect: cleanup,
  };
}
