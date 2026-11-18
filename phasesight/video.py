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
) -> dict:
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps_meta = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    fps = float(fps_override or fps_meta)
    if not np.isfinite(fps) or fps <= 0 or fps > 1000:
        cap.release()
        raise ValueError("Could not determine a valid FPS; pass --fps explicitly")

    first_ok, first_frame = cap.read()
    if not first_ok:
        cap.release()
        raise RuntimeError("Video contains no readable frames")
    tracker = PhaseCorrelationTracker(first_frame, target_roi, anchor_roi)
    samples = []
    index = 1
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            # Use frame index / nominal FPS for this first prototype. Variable
            # frame-rate sources should be converted to constant frame rate first.
            timestamp_s = index / fps
            samples.append(tracker.process(frame, timestamp_s))
            index += 1
    finally:
        cap.release()

    if len(samples) < 32:
        raise RuntimeError("Video is too short: need at least 33 frames")

    timestamps = np.asarray([s.timestamp_s for s in samples], dtype=np.float64)
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
        ])
        for sample in samples:
            writer.writerow([
                sample.timestamp_s, sample.target_dx_px, sample.target_dy_px,
                sample.anchor_dx_px, sample.anchor_dy_px, sample.relative_dx_px,
                sample.relative_dy_px, sample.target_response, sample.anchor_response,
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
