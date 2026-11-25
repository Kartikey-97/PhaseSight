import { API_BASE } from "./config";
import type {
  Asset,
  BaselineSummary,
  CheckROIsResult,
  HealthStatus,
  Preset,
  ROI,
  RunItem,
  SessionReport,
  VideoPreview,
} from "./types";

class ApiError extends Error {
  status: number;
  data: any;
  constructor(message: string, status: number, data?: any) {
    super(message);
    this.status = status;
    this.data = data;
  }
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    ...options,
    headers: {
      ...options?.headers,
    },
  });

  if (!response.ok) {
    let errBody: any;
    try {
      errBody = await response.json();
    } catch {
      errBody = await response.text();
    }
    const msg =
      errBody?.detail ||
      errBody?.message ||
      `Request failed with status ${response.status}`;
    throw new ApiError(msg, response.status, errBody);
  }

  return response.json();
}

export const api = {
  // Health
  getHealth: () => request<HealthStatus>("/api/v1/health"),

  // Assets
  getAssets: () => request<Asset[]>("/api/v1/assets"),
  getAsset: (assetId: string) => request<Asset>(`/api/v1/assets/${assetId}`),
  createAsset: (data: {
    name: string;
    nominal_rpm?: number | null;
    expected_fps?: number | null;
    default_target_roi?: ROI | null;
    default_anchor_roi?: ROI | null;
  }) =>
    request<Asset>("/api/v1/assets", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  deleteAsset: (assetId: string) =>
    request<{ status: string; deleted: string }>(`/api/v1/assets/${assetId}`, {
      method: "DELETE",
    }),

  // Presets & Video Previews
  getPresets: () => request<Preset[]>("/api/v1/videos/presets"),
  getPreview: (params: { preset_id?: string; upload_id?: string; file?: File }) => {
    if (params.file) {
      const fd = new FormData();
      fd.append("file", params.file);
      return request<VideoPreview>("/api/v1/videos/preview", {
        method: "POST",
        body: fd,
      });
    }
    return request<VideoPreview>("/api/v1/videos/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset_id: params.preset_id,
        upload_id: params.upload_id,
      }),
    });
  },
  checkROIs: (data: {
    target_roi: ROI;
    anchor_roi: ROI;
    preset_id?: string | null;
    upload_id?: string | null;
  }) =>
    request<CheckROIsResult>("/api/v1/videos/check-rois", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),

  // Sessions
  getActiveSession: async () => {
    try {
      return await request<any>("/api/v1/sessions/active");
    } catch (e: any) {
      if (e.status === 404) return null;
      throw e;
    }
  },
  getSession: (sessionId: string) =>
    request<any>(`/api/v1/sessions/${sessionId}`),
  startSession: (data: {
    source_type: "browser_webcam" | "video_replay";
    target_roi: ROI;
    anchor_roi: ROI;
    asset_id?: string | null;
    preset_id?: string | null;
    upload_id?: string | null;
    playback_rate?: number;
    loop?: boolean;
    fps_override?: number | null;
    nperseg?: number;
    min_texture_std?: number;
    min_response?: number;
  }) =>
    request<any>("/api/v1/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
  recalibrateSession: (sessionId: string) =>
    request<any>(`/api/v1/sessions/${sessionId}/recalibrate`, {
      method: "POST",
    }),
  stopSession: (sessionId: string) =>
    request<SessionReport>(`/api/v1/sessions/${sessionId}/stop`, {
      method: "POST",
    }),

  // Runs
  getRuns: (params?: { asset_id?: string; status?: string }) => {
    const q = new URLSearchParams();
    if (params?.asset_id) q.set("asset_id", params.asset_id);
    if (params?.status) q.set("status", params.status);
    const qs = q.toString();
    return request<RunItem[]>(`/api/v1/runs${qs ? `?${qs}` : ""}`);
  },
  getRun: (runId: string) => request<any>(`/api/v1/runs/${runId}`),
  analyzeRun: (data: {
    file?: File;
    preset_id?: string;
    upload_id?: string;
    target_roi: ROI;
    anchor_roi: ROI;
    asset_id?: string | null;
    fps_override?: number | null;
    nperseg?: number;
  }) => {
    if (data.file) {
      const fd = new FormData();
      fd.append("file", data.file);
      fd.append("target_roi", JSON.stringify(data.target_roi));
      fd.append("anchor_roi", JSON.stringify(data.anchor_roi));
      if (data.asset_id) fd.append("asset_id", data.asset_id);
      if (data.fps_override) fd.append("fps_override", String(data.fps_override));
      if (data.nperseg) fd.append("nperseg", String(data.nperseg));
      return request<any>("/api/v1/runs/analyze", {
        method: "POST",
        body: fd,
      });
    }
    return request<any>("/api/v1/runs/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preset_id: data.preset_id,
        upload_id: data.upload_id,
        target_roi: data.target_roi,
        anchor_roi: data.anchor_roi,
        asset_id: data.asset_id,
        fps_override: data.fps_override,
        nperseg: data.nperseg,
      }),
    });
  },

  // Baselines
  getBaselines: (assetId?: string) => {
    const qs = assetId ? `?asset_id=${encodeURIComponent(assetId)}` : "";
    return request<BaselineSummary[]>(`/api/v1/baselines${qs}`);
  },
  buildBaseline: (data: {
    asset_id: string;
    run_ids: string[];
    require_valid_axes?: string[];
  }) =>
    request<BaselineSummary>("/api/v1/baselines/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    }),
};
