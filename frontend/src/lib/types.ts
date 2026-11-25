export interface ROI {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface Asset {
  asset_id: string;
  name: string;
  nominal_rpm?: number | null;
  expected_fps?: number | null;
  default_target_roi?: ROI | null;
  default_anchor_roi?: ROI | null;
  created_at: string;
  baseline_count?: number;
  run_count?: number;
  active_baseline?: BaselineSummary | null;
}

export interface Preset {
  preset_id: string;
  label: string;
  category: "synthetic_validation" | "rotor_benchmark" | string;
  rel_path: string;
  exists: boolean;
  recommended_fps_override?: number | null;
  recommended_playback_rate?: number | null;
  default_target_roi?: ROI | null;
  default_anchor_roi?: ROI | null;
  description: string;
}

export interface VideoPreview {
  frame_width?: number;
  frame_height?: number;
  fps?: number;
  total_frames?: number;
  preview_image_base64?: string;
  width?: number;
  height?: number;
  container_fps?: number;
  frame_count?: number;
  preview_png_base64?: string;
  duration_s?: number;
  recommended_fps_override?: number | null;
  default_target_roi?: ROI | null;
  default_anchor_roi?: ROI | null;
  preset_id?: string | null;
  upload_id?: string | null;
}

export interface CheckROIsResult {
  valid: boolean;
  target_std?: number;
  anchor_std?: number;
  target_texture_std?: number;
  anchor_texture_std?: number;
  overlap?: boolean;
  errors: string[];
}

export interface SpectralMetrics {
  dominant_frequency_hz: number;
  dominant_period_s?: number;
  rms_displacement_px: number;
  peak_to_median_db: number;
  second_harmonic_ratio?: number | null;
  signal_quality: "VALID" | "LOW_SIGNAL" | "CONTAMINATED" | string;
  usable_max_hz?: number;
  nyquist_hz?: number;
  frequencies?: number[];
  psd?: number[];
  frequency_resolution_hz?: number;
}

export interface BaselineFeatureZ {
  feature_name: string;
  current_value: number;
  median_baseline: number;
  mad_scaled: number;
  z_score: number;
}

export interface BaselineDeviationDetail {
  feature_name: string;
  axis: string;
  current_value?: number | null;
  baseline_median?: number | null;
  baseline_mad?: number | null;
  z_robust?: number | null;
  is_trigger?: boolean;
  notes?: string;
}

export interface BaselineAssessment {
  baseline_id: string;
  overall_status: "NORMAL" | "REVIEW" | "LOW_CONFIDENCE" | string;
  status?: string;
  max_z_score: number;
  z_scores?: Record<string, number>;
  triggered_features?: string[];
  trigger_features?: string[];
  deviations?: Record<string, BaselineDeviationDetail>;
  reasons?: string[];
  interpretation?: string;
  x_features?: BaselineFeatureZ[];
  y_features?: BaselineFeatureZ[];
  warnings?: string[];
}

export interface RollingUpdate {
  message_type: "rolling_update";
  session_id: string;
  seq: number;
  state: "CREATED" | "BUFFERING" | "WARMING_UP" | "ACTIVE" | "DEGRADED" | string;
  warmup_progress?: {
    filled_samples: number;
    required_samples: number;
    percentage: number;
  } | null;
  measured_fps?: number | null;
  timebase_source?: string | null;
  timing_status?: string | null;
  jitter_ratio?: number | null;
  dropped_frames?: number | null;
  x_metrics?: SpectralMetrics | null;
  y_metrics?: SpectralMetrics | null;
  baseline_assessment?: BaselineAssessment | null;
  warnings: string[];
  mean_target_response?: number | null;
  mean_anchor_response?: number | null;
  timestamp: number;
}

export interface TraceSample {
  t: number;
  rel_dx_px: number;
  rel_dy_px: number;
  target_corr?: number;
  anchor_corr?: number;
  raw_target_dx?: number;
  raw_target_dy?: number;
  raw_anchor_dx?: number;
  raw_anchor_dy?: number;
}

export interface TraceBatch {
  message_type: "trace_batch";
  session_id: string;
  samples: TraceSample[];
}

export interface TelemetrySnapshot {
  message_type?: "snapshot";
  type?: "snapshot";
  session_id: string;
  state?: string;
  source_type?: string;
  fps_override?: number | null;
  target_roi?: ROI;
  anchor_roi?: ROI;
  recent_samples: TraceSample[];
  latest_update?: RollingUpdate | null;
}

export interface SessionReport {
  session_id: string;
  run_id?: string | null;
  asset_id?: string | null;
  source_type: string;
  duration_s: number;
  frames_analysed: number;
  measured_fps: number;
  timebase_source: string;
  temporal_stability?: {
    status: string;
    median_dt_s?: number;
    jitter_ratio?: number;
    dropped_frames_count?: number;
  } | null;
  x_metrics?: SpectralMetrics | null;
  y_metrics?: SpectralMetrics | null;
  baseline_assessment?: BaselineAssessment | null;
  disclosures?: {
    measurement_units: string;
    optical_method: string;
    bandwidth_disclosure: string;
    screening_purpose_only: boolean;
  } | null;
}

export interface RunItem {
  run_id: string;
  asset_id: string;
  mode: string;
  timestamp: string;
  fps: number;
  duration_s: number;
  x_frequency_hz?: number | null;
  y_frequency_hz?: number | null;
  x_dominant_frequency_hz?: number | null;
  y_dominant_frequency_hz?: number | null;
  x_rms_px?: number | null;
  y_rms_px?: number | null;
  x_signal_quality?: string | null;
  y_signal_quality?: string | null;
  source_type?: string;
  status: "NORMAL" | "REVIEW" | "LOW_CONFIDENCE" | "UNASSESSED" | string;
  summary?: any;
}

export interface BaselineAxisStats {
  dominant_frequency_hz_median: number;
  dominant_frequency_hz_mad: number;
  rms_displacement_px_median: number;
  rms_displacement_px_mad: number;
  peak_to_median_db_median: number;
  peak_to_median_db_mad: number;
  second_harmonic_ratio_median?: number | null;
  second_harmonic_ratio_mad?: number | null;
}

export interface BaselineSummary {
  baseline_id: string;
  asset_id: string;
  created_at: string;
  run_ids: string[];
  x_baseline?: BaselineAxisStats | null;
  y_baseline?: BaselineAxisStats | null;
}

export interface HealthStatus {
  status: string;
  python_version: string;
  versions: {
    numpy: string;
    scipy: string;
    cv2: string;
    fastapi: string;
  };
  active_session_id?: string | null;
  storage_ready: boolean;
  asset_count: number;
  run_count: number;
}
