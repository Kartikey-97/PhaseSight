from __future__ import annotations

import collections
from dataclasses import asdict, dataclass, field
import datetime
import threading
from typing import Any
import uuid

import numpy as np

from phasesight.baseline import BaselineRecord
from phasesight.monitoring.ring_buffer import BufferSnapshot, RollingMotionBuffer
from phasesight.monitoring.rolling_analysis import (
    RollingAnalysisResult,
    analyze_rolling_window,
)
from phasesight.storage import RunArrays, StorageManager
from phasesight.tracker import MotionSample, PhaseCorrelationTracker, ROI


@dataclass(frozen=True)
class MonitoringConfig:
    session_id: str
    source_type: str  # "browser_webcam" | "video_replay" | "mock_stream"
    target_roi: ROI
    anchor_roi: ROI
    expected_fps: float = 30.0
    timebase_source: str = "measured"
    buffer_capacity: int = 512
    archive_capacity: int = 18000
    analysis_interval_s: float = 0.25
    nperseg_override: int | None = None
    asset_id: str | None = None
    video_path: str | None = None
    baseline: BaselineRecord | None = None
    baseline_id: str | None = None
    min_texture_std: float = 2.0


class MonitoringSession:
    """Thread-safe continuous vibration monitoring session."""

    def __init__(self, config: MonitoringConfig) -> None:
        self.config = config
        self.state = "CREATED"
        self.tracker: PhaseCorrelationTracker | None = None
        self.rolling_buffer = RollingMotionBuffer(config.buffer_capacity)
        self.archive_buffer: collections.deque[MotionSample] = collections.deque(
            maxlen=config.archive_capacity
        )
        self.pending_traces: list[dict[str, Any]] = []
        self._recalibrate_requested = False
        self._last_timestamp_s: float | None = None
        self._last_analysis_time_s: float = 0.0
        self._last_telemetry: dict[str, Any] | None = None
        self.error_message: str | None = None
        self.warnings: list[str] = []
        self._lock = threading.RLock()

    def ingest_patches(
        self,
        target_patch: np.ndarray,
        anchor_patch: np.ndarray,
        timestamp_s: float,
    ) -> MotionSample | None:
        """Process isolated target and anchor patch frames."""
        with self._lock:
            if self.state in ("STOPPING", "PERSISTED", "ERROR"):
                return None

            # First call locks reference patches
            if self.tracker is None:
                self.state = "CALIBRATING"
                try:
                    self.tracker = PhaseCorrelationTracker.from_patches(
                        target_patch,
                        anchor_patch,
                        self.config.target_roi,
                        self.config.anchor_roi,
                        min_texture_std=self.config.min_texture_std,
                    )
                    self.state = "BUFFERING"
                except Exception as exc:
                    self.state = "ERROR"
                    self.error_message = str(exc)
                    raise

            # Handle pending recalibration request
            if self._recalibrate_requested:
                self._recalibrate_requested = False
                try:
                    self.tracker.recalibrate(target_patch, anchor_patch)
                    self.rolling_buffer.clear()
                    self.state = "BUFFERING"
                except Exception as exc:
                    self.warnings.append(f"Recalibration failed: {exc}")

            # Handle severe inter-frame gap
            if (
                self._last_timestamp_s is not None
                and self.config.timebase_source != "explicit_fps_override"
            ):
                expected_dt = 1.0 / self.config.expected_fps
                dt = timestamp_s - self._last_timestamp_s
                if dt > 2.5 * expected_dt and len(self.rolling_buffer) >= 10:
                    self.rolling_buffer.clear()
                    self.warnings.append(
                        f"Severe timestamp gap ({dt:.3f}s > 2.5 * {expected_dt:.3f}s); reset rolling buffer."
                    )
                    self.state = "BUFFERING"

            self._last_timestamp_s = timestamp_s

            sample = self.tracker.process_patches(
                target_patch, anchor_patch, timestamp_s
            )
            self.rolling_buffer.append(sample)
            self.archive_buffer.append(sample)
            self.pending_traces.append(
                {
                    "timestamp_s": float(sample.timestamp_s),
                    "t": float(sample.timestamp_s),
                    "target_dx_px": float(sample.target_dx_px),
                    "target_dy_px": float(sample.target_dy_px),
                    "anchor_dx_px": float(sample.anchor_dx_px),
                    "anchor_dy_px": float(sample.anchor_dy_px),
                    "relative_dx_px": float(sample.relative_dx_px),
                    "relative_dy_px": float(sample.relative_dy_px),
                    "rel_dx_px": float(sample.relative_dx_px),
                    "rel_dy_px": float(sample.relative_dy_px),
                    "raw_target_dx": float(sample.target_dx_px),
                    "raw_target_dy": float(sample.target_dy_px),
                    "raw_anchor_dx": float(sample.anchor_dx_px),
                    "raw_anchor_dy": float(sample.anchor_dy_px),
                    "valid": bool(sample.valid),
                    "target_response": float(sample.target_response),
                    "anchor_response": float(sample.anchor_response),
                    "target_corr": float(sample.target_response),
                    "anchor_corr": float(sample.anchor_response),
                }
            )
            return sample

    def ingest_frame(
        self, frame: np.ndarray, timestamp_s: float
    ) -> MotionSample | None:
        """Crop ROIs from a full image frame and ingest patches."""
        target_patch = self.config.target_roi.crop(frame)
        anchor_patch = self.config.anchor_roi.crop(frame)
        return self.ingest_patches(target_patch, anchor_patch, timestamp_s)

    def request_recalibration(self) -> None:
        """Signal that the next ingested frame should recalibrate references."""
        with self._lock:
            self._recalibrate_requested = True

    def drain_trace_batch(self) -> list[dict[str, Any]]:
        """Drain accumulated trace points for streaming down WebSockets."""
        with self._lock:
            batch = list(self.pending_traces)
            self.pending_traces.clear()
            return batch

    def get_rolling_telemetry(self, force: bool = False) -> dict[str, Any] | None:
        """Run rolling spectral analysis and return JSON-serializable telemetry."""
        with self._lock:
            import time

            now = time.perf_counter()
            if not force and self._last_telemetry is not None:
                if (now - self._last_analysis_time_s) < self.config.analysis_interval_s:
                    return self._last_telemetry

            snapshot = self.rolling_buffer.snapshot()
            analysis: RollingAnalysisResult = analyze_rolling_window(
                snapshot,
                expected_fps=self.config.expected_fps,
                timebase_source=self.config.timebase_source,
                nperseg_override=self.config.nperseg_override,
                target_roi=self.config.target_roi,
                anchor_roi=self.config.anchor_roi,
                baseline=self.config.baseline,
            )

            if analysis.should_reset_buffer:
                self.rolling_buffer.clear()

            if self.state not in ("ERROR", "STOPPING", "PERSISTED"):
                self.state = analysis.state

            telemetry = {
                "session_id": self.config.session_id,
                "state": self.state,
                "timestamp_utc": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "seq": len(self.archive_buffer),
                "processed_samples": len(self.archive_buffer),
                "buffer_filled": analysis.buffer_filled,
                "buffer_capacity": analysis.buffer_capacity,
                "required_warmup_samples": analysis.required_warmup_samples,
                "window_duration_s": analysis.window_duration_s,
                "valid_ratio": analysis.valid_ratio,
                "measured_fps": analysis.measured_fps,
                "nyquist_hz": analysis.nyquist_hz,
                "usable_max_hz": analysis.usable_max_hz,
                "timebase_source": analysis.timebase_source,
                "timing_status": analysis.timing_status,
                "jitter_ratio": analysis.jitter_ratio,
                "dropped_frames": analysis.dropped_frames,
                "nperseg_used": analysis.nperseg_used,
                "x_axis": asdict(analysis.x_axis),
                "y_axis": asdict(analysis.y_axis),
                "frequencies_hz": analysis.frequencies_hz,
                "x_psd": analysis.x_psd,
                "y_psd": analysis.y_psd,
                "mean_min_phase_response": analysis.mean_min_phase_response,
                "mean_target_response": analysis.mean_target_response,
                "mean_anchor_response": analysis.mean_anchor_response,
                "baseline_assessment": analysis.baseline_assessment,
                "warnings": list(set(self.warnings + analysis.warnings)),
                "error_message": self.error_message,
            }
            self._last_analysis_time_s = now
            self._last_telemetry = telemetry
            return telemetry

    def stop_and_persist(self, storage: StorageManager | None = None) -> dict[str, Any]:
        """Finalize monitoring session, compute final run summary, and persist to storage."""
        with self._lock:
            self.state = "STOPPING"
            telemetry = self.get_rolling_telemetry(force=True)

            samples = list(self.archive_buffer)
            if not samples:
                self.state = "PERSISTED"
                return {
                    "session_id": self.config.session_id,
                    "session_mode": "continuous_monitoring",
                    "status": "NoData",
                    "frames_analysed": 0,
                    "run_id": None,
                }

            timestamps = np.asarray([s.timestamp_s for s in samples], dtype=np.float64)
            duration_s = (
                float(timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0
            )
            valid_count = sum(1 for s in samples if s.valid)
            valid_ratio = float(valid_count / len(samples)) if samples else 0.0

            x_axis_summary = telemetry["x_axis"] if telemetry else {}
            y_axis_summary = telemetry["y_axis"] if telemetry else {}
            eval_dict = telemetry.get("baseline_assessment") if telemetry else None
            run_status = (
                eval_dict.get("status", "Unassessed") if eval_dict else "Unassessed"
            )

            measured_fps_val = float(
                telemetry.get("measured_fps", self.config.expected_fps)
                if telemetry and telemetry.get("measured_fps")
                else (self.config.expected_fps if self.config.expected_fps else 30.0)
            )
            if not np.isfinite(measured_fps_val) or measured_fps_val <= 0.0:
                if len(timestamps) > 1 and duration_s > 0:
                    measured_fps_val = float((len(timestamps) - 1) / duration_s)
                elif self.config.expected_fps and self.config.expected_fps > 0:
                    measured_fps_val = float(self.config.expected_fps)
                else:
                    measured_fps_val = 30.0

            summary: dict[str, Any] = {
                "session_mode": "continuous_monitoring",
                "source_type": self.config.source_type,
                "session_id": self.config.session_id,
                "timebase_source": self.config.timebase_source,
                "timestamp_source": self.config.timebase_source,
                "timestamp_utc": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "duration_s": duration_s,
                "frames_analysed": len(samples),
                "valid_patch_ratio": valid_ratio,
                "measured_fps": measured_fps_val,
                "fps_used": measured_fps_val,
                "sampling_rate_hz": measured_fps_val,
                "target_roi_xywh": {
                    "x": self.config.target_roi.x,
                    "y": self.config.target_roi.y,
                    "width": self.config.target_roi.width,
                    "height": self.config.target_roi.height,
                },
                "anchor_roi_xywh": {
                    "x": self.config.anchor_roi.x,
                    "y": self.config.anchor_roi.y,
                    "width": self.config.anchor_roi.width,
                    "height": self.config.anchor_roi.height,
                },
                "temporal_stability": {
                    "status": telemetry.get("timing_status", "UNKNOWN")
                    if telemetry
                    else "UNKNOWN",
                    "timebase_source": self.config.timebase_source,
                    "jitter_ratio": telemetry.get("jitter_ratio")
                    if telemetry
                    else None,
                    "dropped_frames": telemetry.get("dropped_frames")
                    if telemetry
                    else None,
                },
                "x_axis": x_axis_summary,
                "y_axis": y_axis_summary,
                "baseline_assessment": eval_dict,
                "warnings": telemetry.get("warnings", []) if telemetry else [],
            }

            run_id = None
            if storage is not None and self.config.asset_id:
                # Check that asset exists in storage
                asset = storage.get_asset(self.config.asset_id)
                if asset is not None:
                    freqs = np.asarray(
                        telemetry.get("frequencies_hz", []), dtype=np.float64
                    )
                    x_psd = np.asarray(telemetry.get("x_psd", []), dtype=np.float64)
                    y_psd = np.asarray(telemetry.get("y_psd", []), dtype=np.float64)

                    run_arrays = RunArrays(
                        timestamps_s=timestamps,
                        relative_dx_px=np.asarray(
                            [s.relative_dx_px for s in samples], dtype=np.float64
                        ),
                        relative_dy_px=np.asarray(
                            [s.relative_dy_px for s in samples], dtype=np.float64
                        ),
                        target_dx_px=np.asarray(
                            [s.target_dx_px for s in samples], dtype=np.float64
                        ),
                        target_dy_px=np.asarray(
                            [s.target_dy_px for s in samples], dtype=np.float64
                        ),
                        anchor_dx_px=np.asarray(
                            [s.anchor_dx_px for s in samples], dtype=np.float64
                        ),
                        anchor_dy_px=np.asarray(
                            [s.anchor_dy_px for s in samples], dtype=np.float64
                        ),
                        target_response=np.asarray(
                            [s.target_response for s in samples], dtype=np.float64
                        ),
                        anchor_response=np.asarray(
                            [s.anchor_response for s in samples], dtype=np.float64
                        ),
                        x_frequencies_hz=freqs if len(freqs) > 0 else None,
                        x_psd_px2_per_hz=x_psd if len(x_psd) > 0 else None,
                        y_frequencies_hz=freqs if len(freqs) > 0 else None,
                        y_psd_px2_per_hz=y_psd if len(y_psd) > 0 else None,
                    )

                    video_target = (
                        self.config.video_path
                        or f"stream://{self.config.source_type}/{self.config.session_id}"
                    )
                    actual_baseline_id = None
                    if self.config.baseline_id and storage.get_baseline(self.config.baseline_id):
                        actual_baseline_id = self.config.baseline_id
                    elif self.config.baseline and storage.get_baseline(self.config.baseline.baseline_id):
                        actual_baseline_id = self.config.baseline.baseline_id
                    elif self.config.asset_id:
                        latest_b = storage.get_latest_baseline_for_asset(self.config.asset_id)
                        if latest_b:
                            actual_baseline_id = latest_b.baseline_id

                    rec = storage.create_inspection_run(
                        asset_id=self.config.asset_id,
                        video_path=video_target,
                        measured_fps=float(
                            telemetry.get("measured_fps", self.config.expected_fps)
                            if telemetry
                            else self.config.expected_fps
                        ),
                        duration_s=duration_s,
                        frames_analysed=len(samples),
                        summary=summary,
                        baseline_id=actual_baseline_id,
                        arrays=run_arrays,
                        valid_patch_ratio=valid_ratio,
                        status=run_status if run_status in ("Normal", "Review", "Low confidence") else "Unassessed",
                    )
                    run_id = rec.run_id
                    summary["run_id"] = run_id

            self.state = "PERSISTED"
            return summary
