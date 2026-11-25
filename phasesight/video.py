from __future__ import annotations

import csv
import json
from dataclasses import asdict
from pathlib import Path

import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .analysis import analyse_displacement, classify_signal_quality, is_anchor_contaminated
from .tracker import PhaseCorrelationTracker, ROI


def parse_roi(value: str) -> ROI:
    try:
        parts = [int(part.strip()) for part in value.split(",")]
    except ValueError as exc:
        raise ValueError("ROI must be x,y,width,height (integers)") from exc
    if len(parts) != 4:
        raise ValueError("ROI must be x,y,width,height")
    return ROI(*parts)


def analyse_video(
    video_path: str | Path,
    target_roi: ROI,
    anchor_roi: ROI,
    output_dir: str | Path,
    *,
    fps_override: float | None = None,
    min_frequency_hz: float = 0.5,
    max_frequency_hz: float | None = None,
    nperseg: int = 256,
    allow_unstable_sampling: bool = False,
) -> dict:
    from .capture import CaptureStabilityReport, calculate_timestamp_stability

    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    if fps_override is not None:
        try:
            fps_val = float(fps_override)
        except (TypeError, ValueError):
            cap.release()
            raise ValueError(
                f"Invalid explicit FPS override: {fps_override}. Must be a finite positive number."
            )
        if not np.isfinite(fps_val) or fps_val <= 0:
            cap.release()
            raise ValueError(
                f"Invalid explicit FPS override: {fps_override}. Must be a finite positive number."
            )
        fps = fps_val
        is_override = True
    else:
        fps_meta = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        fps = fps_meta
        if not np.isfinite(fps) or fps <= 0 or fps > 1000:
            cap.release()
            raise ValueError("Could not determine a valid FPS; pass --fps explicitly")
        is_override = False

    first_ok, first_frame = cap.read()
    if not first_ok:
        cap.release()
        raise RuntimeError("Video contains no readable frames")

    first_pts_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
    initial_pts_ok = (
        first_pts_msec is not None
        and np.isfinite(first_pts_msec)
        and float(first_pts_msec) >= 0.0
    )
    first_pts_val = float(first_pts_msec) if initial_pts_ok else 0.0

    tracker = PhaseCorrelationTracker(first_frame, target_roi, anchor_roi)
    samples = []
    pts_s: list[float] = []
    backend_pts_reliable = initial_pts_ok and not is_override
    index = 1
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if is_override:
                t_s = index / fps
            else:
                pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
                if backend_pts_reliable and pos_msec is not None and np.isfinite(pos_msec):
                    t_s = (float(pos_msec) - first_pts_val) / 1000.0
                    prev_t = pts_s[-1] if pts_s else 0.0
                    if t_s <= prev_t and pos_msec == first_pts_val:
                        # Container returns frozen / unadvancing timestamps (e.g. constant 0.0)
                        backend_pts_reliable = False
                        t_s = index / fps
                else:
                    t_s = index / fps

            pts_s.append(t_s)
            sample = tracker.process(frame, t_s)
            samples.append(sample)
            index += 1
    finally:
        cap.release()

    if len(samples) < 32:
        raise RuntimeError("Video is too short: need at least 33 frames")

    if is_override:
        pts_s = [i / fps for i in range(1, len(samples) + 1)]
        timestamp_source = "explicit_fps_override"
    elif not backend_pts_reliable:
        # If backend PTS degraded or was frozen, fall back to nominal CFR timestamps
        pts_s = [i / fps for i in range(1, len(samples) + 1)]
        timestamp_source = "inferred_cfr_fallback"
    else:
        timestamp_source = "container_pts"

    # Reject tracking failure frames explicitly
    invalid_samples = [s for s in samples if not s.valid]
    if invalid_samples:
        raise RuntimeError(
            f"Tracking quality gate failed: {len(invalid_samples)} / {len(samples)} frames rejected "
            f"({invalid_samples[0].rejection_reason}). Cannot perform vibration analysis with invalid tracking samples."
        )

    timestamps = np.asarray(pts_s, dtype=np.float64)

    # Validate temporal sampling stability
    if is_override:
        stability = CaptureStabilityReport(
            total_frames=len(timestamps),
            duration_s=float(timestamps[-1] - timestamps[0]) if len(timestamps) > 1 else 0.0,
            nominal_fps=float(fps),
            measured_fps=float(fps),
            median_dt_s=float(1.0 / fps),
            mean_dt_s=float(1.0 / fps),
            std_dt_s=float("nan"),
            min_dt_s=float(1.0 / fps),
            max_dt_s=float(1.0 / fps),
            jitter_ratio=float("nan"),
            robust_jitter_ratio=float("nan"),
            dropped_frames_count=None,
            dropped_frame_indices=[],
            large_gap_count=0,
            status="ASSUMED_UNIFORM",
            status_reasons=[
                "Timestamps were synthesized from an explicit FPS override. "
                "Physical capture timing, dropped frames, and exposure jitter were not independently verified."
            ],
        )
    else:
        stability = calculate_timestamp_stability(timestamps, nominal_fps=fps)
        if stability.status == "REJECTED_UNSTABLE" and not allow_unstable_sampling:
            raise RuntimeError(
                f"Video temporal sampling is rejected as unstable ({stability.status}): "
                f"{'; '.join(stability.status_reasons)}"
            )

    dx = np.asarray([s.relative_dx_px for s in samples], dtype=np.float64)
    dy = np.asarray([s.relative_dy_px for s in samples], dtype=np.float64)
    x_result = analyse_displacement(
        timestamps,
        dx,
        min_frequency_hz=min_frequency_hz,
        max_frequency_hz=max_frequency_hz,
        nperseg=nperseg,
    )
    y_result = analyse_displacement(
        timestamps,
        dy,
        min_frequency_hz=min_frequency_hz,
        max_frequency_hz=max_frequency_hz,
        nperseg=nperseg,
    )
    target_dx = np.asarray([s.target_dx_px for s in samples], dtype=np.float64)
    target_dy = np.asarray([s.target_dy_px for s in samples], dtype=np.float64)
    anchor_dx = np.asarray([s.anchor_dx_px for s in samples], dtype=np.float64)
    anchor_dy = np.asarray([s.anchor_dy_px for s in samples], dtype=np.float64)
    target_x_result = analyse_displacement(timestamps, target_dx, min_frequency_hz=min_frequency_hz, max_frequency_hz=max_frequency_hz, nperseg=nperseg)
    target_y_result = analyse_displacement(timestamps, target_dy, min_frequency_hz=min_frequency_hz, max_frequency_hz=max_frequency_hz, nperseg=nperseg)
    anchor_x_result = analyse_displacement(timestamps, anchor_dx, min_frequency_hz=min_frequency_hz, max_frequency_hz=max_frequency_hz, nperseg=nperseg)
    anchor_y_result = analyse_displacement(timestamps, anchor_dy, min_frequency_hz=min_frequency_hz, max_frequency_hz=max_frequency_hz, nperseg=nperseg)

    csv_path = output_dir / f"{video_path.stem}_motion.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "timestamp_s", "target_dx_px", "target_dy_px", "anchor_dx_px", "anchor_dy_px",
            "relative_dx_px", "relative_dy_px", "target_response", "anchor_response",
            "valid", "rejection_reason",
        ])
        for sample in samples:
            writer.writerow([
                sample.timestamp_s, sample.target_dx_px, sample.target_dy_px,
                sample.anchor_dx_px, sample.anchor_dy_px, sample.relative_dx_px,
                sample.relative_dy_px, sample.target_response, sample.anchor_response,
                sample.valid, sample.rejection_reason or "",
            ])

    fig, axes = plt.subplots(2, 1, figsize=(10, 7), constrained_layout=True)
    axes[0].plot(timestamps, dx, linewidth=0.8, label="relative X")
    axes[0].plot(timestamps, dy, linewidth=0.8, label="relative Y", alpha=0.7)
    axes[0].set(title="Measured relative displacement", xlabel="Time (s)", ylabel="Pixels")
    axes[0].legend()
    axes[0].grid(True, alpha=0.25)
    axes[1].semilogy(x_result.frequencies_hz, x_result.psd_px2_per_hz, label="X PSD")
    axes[1].semilogy(y_result.frequencies_hz, y_result.psd_px2_per_hz, label="Y PSD", alpha=0.7)
    axes[1].axvline(x_result.dominant_frequency_hz, linestyle="--", linewidth=1, label=f"X peak {x_result.dominant_frequency_hz:.2f} Hz")
    axes[1].set(title="Welch power spectral density", xlabel="Frequency (Hz)", ylabel="PSD (px²/Hz)")
    axes[1].legend()
    axes[1].grid(True, alpha=0.25)
    plot_path = output_dir / f"{video_path.stem}_spectrum.png"
    fig.savefig(plot_path, dpi=160)
    plt.close(fig)

    valid_response = np.asarray([min(s.target_response, s.anchor_response) for s in samples])
    mean_response = float(np.mean(np.clip(valid_response, 0.0, 1.0)))
    x_contaminated = is_anchor_contaminated(x_result, anchor_x_result)
    y_contaminated = is_anchor_contaminated(y_result, anchor_y_result)
    x_quality = "CONTAMINATED" if x_contaminated else classify_signal_quality(x_result, mean_phase_response=mean_response)
    y_quality = "CONTAMINATED" if y_contaminated else classify_signal_quality(y_result, mean_phase_response=mean_response)
    summary = {
        "video": str(video_path),
        "fps_used": fps,
        "frames_analysed": len(samples) + 1,
        "duration_s": float(timestamps[-1] - timestamps[0]),
        "timestamp_source": timestamp_source,
        "timebase_source": timestamp_source,
        "temporal_stability": stability.to_dict(),
        "target_roi_xywh": asdict(target_roi),
        "anchor_roi_xywh": asdict(anchor_roi),
        "x_axis": {
            "dominant_frequency_hz": x_result.dominant_frequency_hz,
            "rms_displacement_px": x_result.rms_px,
            "peak_to_median_db": x_result.peak_to_median_db,
            "signal_quality": x_quality,
            "anchor_dominant_frequency_hz": anchor_x_result.dominant_frequency_hz,
            "anchor_peak_to_median_db": anchor_x_result.peak_to_median_db,
            "target_dominant_frequency_hz": target_x_result.dominant_frequency_hz,
            "second_harmonic_ratio": x_result.second_harmonic_ratio if x_quality == "VALID" else None,
            "frequency_resolution_hz": x_result.frequency_resolution_hz,
            "sampling_rate_hz": x_result.sampling_rate_hz,
        },
        "y_axis": {
            "dominant_frequency_hz": y_result.dominant_frequency_hz,
            "rms_displacement_px": y_result.rms_px,
            "peak_to_median_db": y_result.peak_to_median_db,
            "signal_quality": y_quality,
            "anchor_dominant_frequency_hz": anchor_y_result.dominant_frequency_hz,
            "anchor_peak_to_median_db": anchor_y_result.peak_to_median_db,
            "target_dominant_frequency_hz": target_y_result.dominant_frequency_hz,
            "second_harmonic_ratio": y_result.second_harmonic_ratio if y_quality == "VALID" else None,
            "frequency_resolution_hz": y_result.frequency_resolution_hz,
            "sampling_rate_hz": y_result.sampling_rate_hz,
        },
        "mean_min_phase_correlation_response": mean_response,
        "interpretation": "Screening measurement in pixels; not a calibrated vibration diagnosis.",
        "quality_notes": {
            "CONTAMINATED": "A strong peak at the same frequency appears in the anchor ROI; inspect the anchor for shared motion, lighting/compression artefacts or a poor reference region.",
            "LOW_SIGNAL": "No sufficiently prominent, reliable vibration peak was found in this axis.",
        },
        "outputs": {"csv": str(csv_path), "plot": str(plot_path)},
    }
    summary_path = output_dir / f"{video_path.stem}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    summary["outputs"]["summary"] = str(summary_path)
    return summary
