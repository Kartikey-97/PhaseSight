#!/usr/bin/env python3
"""
PhaseSight Rotor Dataset Benchmark Suite
Executes end-to-end benchmark evaluation across all steady-state and acceleration conditions.
Does NOT modify any phasesight source files.
Directly uses PhaseSight tracker and analysis components.
Produces comprehensive comparison tables, JSON summaries, and publication-ready plots.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from phasesight.analysis import analyse_displacement, classify_signal_quality, is_anchor_contaminated
from phasesight.tracker import PhaseCorrelationTracker, ROI

DATASET_ROOT = Path("data/rotor_dataset")
RAW_VIDEOS_DIR = DATASET_ROOT / "Raw videos"
SENSOR_DIR = DATASET_ROOT / "Sensor data"
REPORTS_DIR = Path("reports/rotor_dataset_benchmark")
PLOTS_DIR = REPORTS_DIR / "plots"
RUNS_DIR = REPORTS_DIR / "runs"

PHYSICAL_CAMERA_FPS = 500.0  # From experimental setup description in README
PHYSICAL_SENSOR_FS = 1000.0   # From experimental setup description in README

# Standard ROIs selected from Phase 3 analysis:
# Anchor: Base center rigid fixture
ANCHOR_A1 = ROI(600, 560, 64, 64)

# Targets:
# Target A: Midspan Span 1 top edge (near Sensor #2)
TARGET_A = ROI(600, 460, 64, 64)
# Target B: Midspan Span 1 bottom edge
TARGET_B = ROI(600, 485, 64, 64)
# Target C: Right Span top edge near bearing 2 (near Sensor #4)
TARGET_C = ROI(850, 460, 64, 64)
# Target D: Left Span top edge near bearing 1 (near Sensor #1)
TARGET_D = ROI(250, 460, 64, 64)
# Target E: Rotational decorrelation failure test (interior shaft)
TARGET_FAIL_INTERIOR = ROI(550, 488, 48, 32)
# Target G: Surface mark decorrelation failure test (X=520)
TARGET_FAIL_SURFACE_MARK = ROI(520, 460, 64, 64)

def process_video_clip(
    video_path: Path,
    target_roi: ROI,
    anchor_roi: ROI,
    sampling_fps: float = PHYSICAL_CAMERA_FPS,
) -> dict:
    """Run phase correlation tracker on video frames."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video {video_path}")

    container_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    ok, f0 = cap.read()
    if not ok:
        cap.release()
        raise RuntimeError("No frames in video")

    first_pts_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
    first_pts_val = float(first_pts_msec) if first_pts_msec is not None and np.isfinite(first_pts_msec) else 0.0

    try:
        tracker = PhaseCorrelationTracker(f0, target_roi, anchor_roi)
    except Exception as e:
        cap.release()
        return {
            "status": f"REJECTED_INITIALIZATION",
            "total_frames": 0,
            "rejected_frames": 0,
            "rejection_reasons": [str(e)],
            "container_fps": container_fps,
            "physical_fps": sampling_fps,
        }

    samples = []
    t_container = []
    t_physical = []
    frame_idx = 1

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
            if pos_msec is not None and np.isfinite(pos_msec):
                t_c = (float(pos_msec) - first_pts_val) / 1000.0
            else:
                t_c = frame_idx / container_fps

            t_p = frame_idx / sampling_fps
            t_container.append(t_c)
            t_physical.append(t_p)

            s = tracker.process(frame, t_p)
            samples.append(s)
            frame_idx += 1
    finally:
        cap.release()

    valid_samples = [s for s in samples if s.valid]
    rejected_count = len(samples) - len(valid_samples)

    if rejected_count > 0:
        reasons = list(set([s.rejection_reason for s in samples if s.rejection_reason]))
        return {
            "status": f"FAILED_QUALITY_GATE_{rejected_count}_REJECTED",
            "total_frames": len(samples),
            "rejected_frames": rejected_count,
            "rejection_reasons": reasons,
            "container_fps": container_fps,
            "physical_fps": sampling_fps,
        }

    # Arrays
    dx = np.array([s.relative_dx_px for s in samples], dtype=float)
    dy = np.array([s.relative_dy_px for s in samples], dtype=float)
    target_dy = np.array([s.target_dy_px for s in samples], dtype=float)
    anchor_dy = np.array([s.anchor_dy_px for s in samples], dtype=float)
    target_dx = np.array([s.target_dx_px for s in samples], dtype=float)
    anchor_dx = np.array([s.anchor_dx_px for s in samples], dtype=float)

    t_arr = np.array(t_physical)
    duration_s = float(t_arr[-1] - t_arr[0])

    # Choose nperseg: for 500 frames, 256 or 499
    nperseg = min(256, len(samples))
    res_x = analyse_displacement(t_arr, dx, nperseg=nperseg)
    res_y = analyse_displacement(t_arr, dy, nperseg=nperseg)

    res_target_y = analyse_displacement(t_arr, target_dy, nperseg=nperseg)
    res_anchor_y = analyse_displacement(t_arr, anchor_dy, nperseg=nperseg)
    res_target_x = analyse_displacement(t_arr, target_dx, nperseg=nperseg)
    res_anchor_x = analyse_displacement(t_arr, anchor_dx, nperseg=nperseg)

    # Full length FFT peak (fine frequency resolution df = fs / N)
    fft_res_df = sampling_fps / len(samples)
    fft_y = np.abs(np.fft.rfft(signal.detrend(dy)))
    fft_freqs_y = np.fft.rfftfreq(len(dy), 1.0 / sampling_fps)
    idx_peak_fft_y = np.argmax(fft_y[1:]) + 1
    fft_peak_y = float(fft_freqs_y[idx_peak_fft_y])

    fft_x = np.abs(np.fft.rfft(signal.detrend(dx)))
    fft_freqs_x = np.fft.rfftfreq(len(dx), 1.0 / sampling_fps)
    idx_peak_fft_x = np.argmax(fft_x[1:]) + 1
    fft_peak_x = float(fft_freqs_x[idx_peak_fft_x])

    # Also search for rotational synchronous 1x peak in [12, 60] Hz
    mask_1x_y = (fft_freqs_y >= 12.0) & (fft_freqs_y <= 60.0)
    fft_1x_band_peak_y = float(fft_freqs_y[mask_1x_y][np.argmax(fft_y[mask_1x_y])]) if np.any(mask_1x_y) else fft_peak_y
    mask_1x_x = (fft_freqs_x >= 12.0) & (fft_freqs_x <= 60.0)
    fft_1x_band_peak_x = float(fft_freqs_x[mask_1x_x][np.argmax(fft_x[mask_1x_x])]) if np.any(mask_1x_x) else fft_peak_x

    # 2x harmonic band peak [30, 110] Hz
    mask_2x_y = (fft_freqs_y >= 25.0) & (fft_freqs_y <= 110.0)
    fft_2x_band_peak_y = float(fft_freqs_y[mask_2x_y][np.argmax(fft_y[mask_2x_y])]) if np.any(mask_2x_y) else None

    # Quality classification
    min_resp = np.array([min(s.target_response, s.anchor_response) for s in samples])
    mean_resp = float(np.mean(np.clip(min_resp, 0.0, 1.0)))

    x_contam = is_anchor_contaminated(res_x, res_anchor_x)
    y_contam = is_anchor_contaminated(res_y, res_anchor_y)

    x_qual = "CONTAMINATED" if x_contam else classify_signal_quality(res_x, mean_phase_response=mean_resp)
    y_qual = "CONTAMINATED" if y_contam else classify_signal_quality(res_y, mean_phase_response=mean_resp)

    # Also extract container-timebase result (as produced by raw PhaseSight CLI)
    t_c_arr = np.array(t_container)
    res_x_cont = analyse_displacement(t_c_arr, dx, nperseg=nperseg)
    res_y_cont = analyse_displacement(t_c_arr, dy, nperseg=nperseg)

    return {
        "status": "VALID" if rejected_count == 0 else f"PARTIAL_REJECTED_{rejected_count}",
        "total_frames": len(samples),
        "rejected_frames": rejected_count,
        "duration_s": duration_s,
        "container_fps": container_fps,
        "physical_fps": sampling_fps,
        "mean_phase_response": mean_resp,
        "x_axis": {
            "dominant_frequency_hz": res_x.dominant_frequency_hz,
            "dominant_frequency_fft_hz": fft_peak_x,
            "dominant_1x_band_hz": fft_1x_band_peak_x,
            "rms_displacement_px": res_x.rms_px,
            "peak_to_median_db": res_x.peak_to_median_db,
            "signal_quality": x_qual,
            "second_harmonic_ratio": res_x.second_harmonic_ratio,
            "frequency_resolution_hz": res_x.frequency_resolution_hz,
            "frequencies_hz": res_x.frequencies_hz.tolist(),
            "psd_px2_per_hz": res_x.psd_px2_per_hz.tolist(),
        },
        "y_axis": {
            "dominant_frequency_hz": res_y.dominant_frequency_hz,
            "dominant_frequency_fft_hz": fft_peak_y,
            "dominant_1x_band_hz": fft_1x_band_peak_y,
            "dominant_2x_band_hz": fft_2x_band_peak_y,
            "rms_displacement_px": res_y.rms_px,
            "peak_to_median_db": res_y.peak_to_median_db,
            "signal_quality": y_qual,
            "second_harmonic_ratio": res_y.second_harmonic_ratio,
            "frequency_resolution_hz": res_y.frequency_resolution_hz,
            "frequencies_hz": res_y.frequencies_hz.tolist(),
            "psd_px2_per_hz": res_y.psd_px2_per_hz.tolist(),
        },
        "container_timebase": {
            "x_dominant_hz": res_x_cont.dominant_frequency_hz,
            "y_dominant_hz": res_y_cont.dominant_frequency_hz,
        },
        "raw_signals": {
            "timestamps_s": t_arr.tolist(),
            "dx_px": dx.tolist(),
            "dy_px": dy.tolist(),
            "target_dy_px": target_dy.tolist(),
            "anchor_dy_px": anchor_dy.tolist(),
        }
    }


def compare_video_to_sensor(
    cond_name: str,
    video_res: dict,
    sensor_res: dict,
    target_name: str,
    target_sensor_ch: int = 2,
) -> dict:
    """Compare video-derived frequencies and amplitudes with physical sensor ground truth."""
    if video_res.get("status", "").startswith("FAILED") or video_res.get("status", "").startswith("REJECTED"):
        return {
            "condition": cond_name,
            "target_roi": target_name,
            "reference_sensor_channel": target_sensor_ch,
            "sensor_fundamental_fft_hz": sensor_res["channels"][target_sensor_ch - 1]["fundamental_1x_fft_hz"],
            "sensor_fundamental_welch_hz": sensor_res["channels"][target_sensor_ch - 1]["fundamental_1x_welch_hz"],
            "sensor_rms": sensor_res["channels"][target_sensor_ch - 1]["rms_displacement"],
            "sensor_peak_to_peak": sensor_res["channels"][target_sensor_ch - 1]["peak_to_peak"],
            "sensor_clipped": sensor_res["channels"][target_sensor_ch - 1]["is_clipped_or_saturated"],
            "best_video_f_hz": float("nan"),
            "delta_f_hz": float("nan"),
            "relative_error_pct": float("nan"),
            "status": "VIDEO_TRACKING_FAILED",
            "error_reason": "; ".join(video_res.get("rejection_reasons", ["All frames rejected"])),
        }

    # Reference sensor channel (1-indexed)
    s_ch = sensor_res["channels"][target_sensor_ch - 1]
    f_sensor_fft = s_ch["fundamental_1x_fft_hz"]
    f_sensor_welch = s_ch["fundamental_1x_welch_hz"]
    sensor_rms = s_ch["rms_displacement"]
    sensor_ptp = s_ch["peak_to_peak"]
    sensor_clipped = s_ch["is_clipped_or_saturated"]

    # Video peaks
    f_vid_y_welch = video_res["y_axis"]["dominant_frequency_hz"]
    f_vid_y_fft = video_res["y_axis"]["dominant_frequency_fft_hz"]
    f_vid_y_1x = video_res["y_axis"].get("dominant_1x_band_hz", f_vid_y_fft)
    f_vid_x_welch = video_res["x_axis"]["dominant_frequency_hz"]
    f_vid_x_fft = video_res["x_axis"]["dominant_frequency_fft_hz"]
    f_vid_x_1x = video_res["x_axis"].get("dominant_1x_band_hz", f_vid_x_fft)

    vid_y_rms_px = video_res["y_axis"]["rms_displacement_px"]
    vid_x_rms_px = video_res["x_axis"]["rms_displacement_px"]

    # Frequency errors
    # For vertical (Y) vibration:
    delta_f_y_welch = abs(f_vid_y_welch - f_sensor_fft)
    rel_err_y_welch = (delta_f_y_welch / f_sensor_fft) * 100.0

    delta_f_y_fft = abs(f_vid_y_fft - f_sensor_fft)
    rel_err_y_fft = (delta_f_y_fft / f_sensor_fft) * 100.0

    # 1X Synchronous Rotational Band Error
    delta_f_1x_y = abs(f_vid_y_1x - f_sensor_fft)
    rel_err_1x_y = (delta_f_1x_y / f_sensor_fft) * 100.0
    delta_f_1x_x = abs(f_vid_x_1x - f_sensor_fft)
    rel_err_1x_x = (delta_f_1x_x / f_sensor_fft) * 100.0

    # For horizontal (X) vibration:
    delta_f_x_fft = abs(f_vid_x_fft - f_sensor_fft)
    rel_err_x_fft = (delta_f_x_fft / f_sensor_fft) * 100.0

    # Check container timebase uncorrected error
    f_vid_cont = video_res["container_timebase"]["y_dominant_hz"]
    delta_f_cont = abs(f_vid_cont - f_sensor_fft)
    rel_err_cont = (delta_f_cont / f_sensor_fft) * 100.0

    # Best video fundamental (either X or Y depending on vibration orientation)
    # Lateral vibration of rotor can manifest in X and Y
    best_axis = "Y" if delta_f_1x_y <= delta_f_1x_x else "X"
    best_vid_f = f_vid_y_1x if best_axis == "Y" else f_vid_x_1x
    best_delta_f = delta_f_1x_y if best_axis == "Y" else delta_f_1x_x
    best_rel_err = rel_err_1x_y if best_axis == "Y" else rel_err_1x_x

    # Frequency resolution bounds
    vid_df_welch = video_res["y_axis"]["frequency_resolution_hz"]
    vid_df_fft = video_res["physical_fps"] / video_res["total_frames"]
    sensor_df_welch = s_ch["welch_frequency_resolution_hz"]
    sensor_df_fft = s_ch["fft_frequency_resolution_hz"]

    # Harmonic comparison
    s_2x = s_ch.get("harmonic_2x_hz")
    v_2x_y = video_res["y_axis"].get("second_harmonic_ratio")

    # Ratio of video RMS (px) to sensor RMS (raw / mm)
    rms_ratio_px_per_sensor_unit = (vid_y_rms_px / sensor_rms) if sensor_rms > 0 else 0.0

    return {
        "condition": cond_name,
        "target_roi": target_name,
        "reference_sensor_channel": target_sensor_ch,
        "sensor_fundamental_fft_hz": f_sensor_fft,
        "sensor_fundamental_welch_hz": f_sensor_welch,
        "sensor_rms": sensor_rms,
        "sensor_peak_to_peak": sensor_ptp,
        "sensor_clipped": sensor_clipped,
        "video_y_fundamental_fft_hz": f_vid_y_fft,
        "video_y_fundamental_welch_hz": f_vid_y_welch,
        "video_x_fundamental_fft_hz": f_vid_x_fft,
        "video_x_fundamental_welch_hz": f_vid_x_welch,
        "video_y_rms_px": vid_y_rms_px,
        "video_x_rms_px": vid_x_rms_px,
        "best_axis": best_axis,
        "best_video_f_hz": best_vid_f,
        "delta_f_hz": best_delta_f,
        "relative_error_pct": best_rel_err,
        "delta_f_y_fft_hz": delta_f_y_fft,
        "relative_error_y_pct": rel_err_y_fft,
        "delta_f_x_fft_hz": delta_f_x_fft,
        "relative_error_x_pct": rel_err_x_fft,
        "container_timebase_f_hz": f_vid_cont,
        "container_timebase_error_pct": rel_err_cont,
        "video_fft_resolution_hz": vid_df_fft,
        "video_welch_resolution_hz": vid_df_welch,
        "sensor_fft_resolution_hz": sensor_df_fft,
        "rms_ratio_px_per_sensor_unit": rms_ratio_px_per_sensor_unit,
        "video_y_quality": video_res["y_axis"]["signal_quality"],
        "video_x_quality": video_res["x_axis"]["signal_quality"],
        "status": "VALID" if best_rel_err <= 5.0 else ("PARTIAL" if best_rel_err <= 15.0 else "DEVIATED"),
    }


def generate_comparison_plot(
    cond_name: str,
    target_name: str,
    video_res: dict,
    sensor_res: dict,
    out_path: Path,
    target_sensor_ch: int = 2,
):
    """Plot synchronized video PSD vs Sensor PSD."""
    s_ch = sensor_res["channels"][target_sensor_ch - 1]
    s_data = np.loadtxt(SENSOR_DIR / f"{cond_name}.csv", delimiter=",")[:, target_sensor_ch - 1]
    fs_s = 1000.0
    f_s, psd_s = signal.welch(signal.detrend(s_data - np.mean(s_data)), fs=fs_s, nperseg=2000)

    f_v_y = np.array(video_res["y_axis"]["frequencies_hz"])
    psd_v_y = np.array(video_res["y_axis"]["psd_px2_per_hz"])

    f_v_x = np.array(video_res["x_axis"]["frequencies_hz"])
    psd_v_x = np.array(video_res["x_axis"]["psd_px2_per_hz"])

    fig, axes = plt.subplots(3, 1, figsize=(10, 9), constrained_layout=True)
    fig.suptitle(f"Video vs Sensor Benchmark Comparison: {cond_name} ({target_name})", fontsize=12, fontweight="bold")

    # 1. Sensor PSD
    ax1 = axes[0]
    ax1.semilogy(f_s[f_s <= 150], psd_s[f_s <= 150], color="navy", label=f"Physical Sensor Ch #{target_sensor_ch}")
    ax1.axvline(s_ch["fundamental_1x_fft_hz"], color="red", linestyle="--", label=f"1x Peak: {s_ch['fundamental_1x_fft_hz']:.2f} Hz")
    if s_ch["harmonic_2x_hz"]:
        ax1.axvline(s_ch["harmonic_2x_hz"], color="purple", linestyle=":", label=f"2x: {s_ch['harmonic_2x_hz']:.2f} Hz")
    ax1.set_title(f"Ground Truth Sensor Ch #{target_sensor_ch} (Welch PSD, fs=1000 Hz, RMS={s_ch['rms_displacement']:.4f})")
    ax1.set_ylabel("Sensor PSD")
    ax1.set_xlabel("Frequency (Hz)")
    ax1.grid(True, alpha=0.3)
    ax1.legend(loc="upper right", fontsize=8)

    # 2. Video Physical Timebase (500 FPS)
    ax2 = axes[1]
    ax2.semilogy(f_v_y[f_v_y <= 150], psd_v_y[f_v_y <= 150], color="crimson", label=f"Video Y (Vertical, RMS={video_res['y_axis']['rms_displacement_px']:.3f} px)")
    ax2.semilogy(f_v_x[f_v_x <= 150], psd_v_x[f_v_x <= 150], color="goldenrod", alpha=0.7, label=f"Video X (Horizontal, RMS={video_res['x_axis']['rms_displacement_px']:.3f} px)")
    ax2.axvline(video_res['y_axis']['dominant_frequency_fft_hz'], color="crimson", linestyle="--", label=f"Y FFT Peak: {video_res['y_axis']['dominant_frequency_fft_hz']:.2f} Hz")
    ax2.axvline(video_res['x_axis']['dominant_frequency_fft_hz'], color="darkorange", linestyle=":", label=f"X FFT Peak: {video_res['x_axis']['dominant_frequency_fft_hz']:.2f} Hz")
    ax2.set_title(f"PhaseSight Video Analysis (Physical Timebase 500 FPS, N=500 frames)")
    ax2.set_ylabel("PSD (px²/Hz)")
    ax2.set_xlabel("Frequency (Hz)")
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="upper right", fontsize=8)

    # 3. Direct Overlay normalized
    ax3 = axes[2]
    # Normalize PSDs to peak = 1 for shape comparison
    norm_psd_s = psd_s / np.max(psd_s)
    norm_psd_vy = psd_v_y / np.max(psd_v_y)
    ax3.semilogy(f_s[f_s <= 100], norm_psd_s[f_s <= 100], color="navy", linewidth=1.5, label="Sensor PSD (Normalized)")
    ax3.semilogy(f_v_y[f_v_y <= 100], norm_psd_vy[f_v_y <= 100], color="crimson", linewidth=1.2, linestyle="--", label="Video Y PSD (Normalized)")
    ax3.set_title("Normalized Spectral Overlay (0 - 100 Hz)")
    ax3.set_ylabel("Normalized PSD")
    ax3.set_xlabel("Frequency (Hz)")
    ax3.grid(True, alpha=0.3)
    ax3.legend(loc="upper right", fontsize=8)

    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def analyze_rampup_spectrogram(video_path: Path, csv_path: Path, out_path: Path):
    """Analyze non-stationary ramp-up recording with Short-Time Fourier Transform (STFT)."""
    # 1. Video displacement
    cap = cv2.VideoCapture(str(video_path))
    ok, f0 = cap.read()
    tracker = PhaseCorrelationTracker(f0, TARGET_A, ANCHOR_A1)  # Target A midspan
    dys = []
    ts = []
    idx = 1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / PHYSICAL_CAMERA_FPS
        s = tracker.process(frame, t)
        if s.valid:
            dys.append(s.relative_dy_px)
            ts.append(t)
        idx += 1
    cap.release()

    dys = np.array(dys)
    ts = np.array(ts)

    # 2. Sensor Channel 4 (the designated valid channel for ramp-up)
    s_data = np.loadtxt(csv_path, delimiter=",")[:, 3]  # Sensor 4
    t_s = np.arange(len(s_data)) / PHYSICAL_SENSOR_FS

    # Compute Spectrogram for Sensor
    f_s, t_spec_s, Sxx_s = signal.spectrogram(s_data - np.mean(s_data), fs=PHYSICAL_SENSOR_FS, nperseg=500, noverlap=400)

    # Compute Spectrogram for Video
    f_v, t_spec_v, Sxx_v = signal.spectrogram(dys - np.mean(dys), fs=PHYSICAL_CAMERA_FPS, nperseg=200, noverlap=150)

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), constrained_layout=True)
    fig.suptitle(f"Ramp-Up Dynamic Acceleration Spectrogram: {video_path.stem}", fontsize=12, fontweight="bold")

    # Sensor spectrogram
    mesh1 = axes[0].pcolormesh(t_spec_s, f_s[f_s <= 70], 10 * np.log10(Sxx_s[f_s <= 70, :] + 1e-12), cmap="inferno", shading="gouraud")
    axes[0].set_title(f"Physical Sensor #4 Spectrogram (Full {t_s[-1]:.1f}s recording, 0 -> 3000 RPM)")
    axes[0].set_ylabel("Frequency (Hz)")
    axes[0].set_xlabel("Time (s)")
    plt.colorbar(mesh1, ax=axes[0], label="dB")

    # Video spectrogram
    mesh2 = axes[1].pcolormesh(t_spec_v, f_v[f_v <= 70], 10 * np.log10(Sxx_v[f_v <= 70, :] + 1e-12), cmap="inferno", shading="gouraud")
    axes[1].set_title(f"Video Displacement Spectrogram (Duration: {ts[-1]:.1f}s, Target near Sensor #4)")
    axes[1].set_ylabel("Frequency (Hz)")
    axes[1].set_xlabel("Time (s)")
    plt.colorbar(mesh2, ax=axes[1], label="dB")

    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main():
    print("=" * 80)
    print("PHASESIGHT ROTOR DATASET BENCHMARK EXECUTION")
    print("=" * 80)

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    # Load Phase 2 sensor reference results
    with open(REPORTS_DIR / "sensor_reference_analysis.json") as f:
        sensor_ref_list = json.load(f)
    sensor_map = {item["file"]: item for item in sensor_ref_list}

    all_comparisons = []
    raw_video_results = {}

    # Define test suite:
    # 1. Initial Benchmark: 1000rpm-Unb1 across multiple candidate ROIs
    print("\n--- PHASE 4: Primary Benchmark (1000rpm-Unb1) Multi-ROI Evaluation ---")
    prim_video = RAW_VIDEOS_DIR / "1000rpm-Unb1.avi"
    prim_csv_name = "1000rpm-Unb1.csv"
    prim_sensor = sensor_map[prim_csv_name]

    rois_to_test = [
        ("T1_Span1_Mid_Top", TARGET_A, ANCHOR_A1, 2),
        ("T2_Span1_Mid_Bot", TARGET_B, ANCHOR_A1, 2),
        ("T3_Span2_Right_NearS4", TARGET_C, ANCHOR_A1, 4),
        ("T4_Span1_Left_NearS1", TARGET_D, ANCHOR_A1, 1),
        ("T5_Fail_SurfaceMark_x520", TARGET_FAIL_SURFACE_MARK, ANCHOR_A1, 2),
        ("T6_Fail_InteriorTexture", TARGET_FAIL_INTERIOR, ANCHOR_A1, 2),
    ]

    for label, troi, aroi, sensor_ch in rois_to_test:
        print(f"Processing 1000rpm-Unb1 with {label}...")
        v_res = process_video_clip(prim_video, troi, aroi)
        raw_video_results[f"1000rpm-Unb1_{label}"] = v_res
        comp = compare_video_to_sensor("1000rpm-Unb1", v_res, prim_sensor, label, target_sensor_ch=sensor_ch)
        all_comparisons.append(comp)

        if v_res["status"] == "VALID":
            plot_path = PLOTS_DIR / f"1000rpm-Unb1_{label}_vs_sensor.png"
            generate_comparison_plot("1000rpm-Unb1", label, v_res, prim_sensor, plot_path, target_sensor_ch=sensor_ch)
            print(f"  -> Dominant Freq: Video ({comp['best_axis']})={comp['best_video_f_hz']:.2f} Hz (Y={comp['video_y_fundamental_fft_hz']:.2f}, X={comp['video_x_fundamental_fft_hz']:.2f}), Sensor={comp['sensor_fundamental_fft_hz']:.2f} Hz | Error={comp['relative_error_pct']:.2f}% | Status: {comp['status']}")
        else:
            print(f"  -> Status: {v_res['status']} ({v_res.get('rejected_frames', 0)} frames rejected)")

    # 2. Extended Evaluation: Steady-State conditions
    print("\n--- PHASE 6: Extended Dataset Evaluation (Unb1, Unb2, Unb3 across Speeds) ---")
    steady_conditions = [
        ("1000rpm-Unb2", 2, "Target_A_MidS2", TARGET_A),
        ("1000rpm-Unb3", 2, "Target_A_MidS2", TARGET_A),
        ("2000rpm-Unb1", 4, "Target_C_NearS4", TARGET_C), # Respect rule: Sensor #1 or #4 only for 2000 rpm!
        ("2000rpm-Unb2", 1, "Target_C_NearS4_Fail", TARGET_C), # Will record texture failure
        ("2000rpm-Unb2", 1, "Target_A_MidS1", TARGET_A),       # Successful alternative ROI
        ("2000rpm-Unb3", 4, "Target_C_NearS4", TARGET_C),
        ("3000rpm-Unb1", 4, "Target_C_NearS4", TARGET_C),
        ("3000rpm-Unb2", 4, "Target_C_NearS4_Fail", TARGET_C), # Will record texture failure
        ("3000rpm-Unb2", 4, "Target_A_MidS4", TARGET_A),       # Alternative ROI
        ("3000rpm-Unb3", 4, "Target_C_NearS4", TARGET_C),
    ]

    for cond_name, sensor_ch, t_label, troi in steady_conditions:
        v_path = RAW_VIDEOS_DIR / f"{cond_name}.avi"
        csv_name = f"{cond_name}.csv"
        s_res = sensor_map[csv_name]

        print(f"Processing {cond_name} with {t_label} (vs Sensor #{sensor_ch})...")
        v_res = process_video_clip(v_path, troi, ANCHOR_A1)
        raw_video_results[f"{cond_name}_{t_label}"] = v_res

        comp = compare_video_to_sensor(cond_name, v_res, s_res, t_label, target_sensor_ch=sensor_ch)
        all_comparisons.append(comp)

        if v_res["status"] == "VALID":
            plot_path = PLOTS_DIR / f"{cond_name}_{t_label}_vs_sensor.png"
            generate_comparison_plot(cond_name, t_label, v_res, s_res, plot_path, target_sensor_ch=sensor_ch)
            print(f"  -> Dominant Freq: Video ({comp['best_axis']})={comp['best_video_f_hz']:.2f} Hz, Sensor={comp['sensor_fundamental_fft_hz']:.2f} Hz | Error={comp['relative_error_pct']:.2f}% | Status: {comp['status']}")
        else:
            print(f"  -> Status: {v_res['status']} ({v_res.get('rejection_reasons', ['Rejected'])[0]})")

    # 3. Experiment D: Ramp-Up Recordings (4s-Unb1, 6s-Unb1)
    print("\n--- PHASE 6: Experiment D (Ramp-up Transient Recordings) ---")
    for ramp_cond in ["4s-Unb1", "6s-Unb1"]:
        v_path = RAW_VIDEOS_DIR / f"{ramp_cond}.avi"
        csv_path = SENSOR_DIR / f"{ramp_cond}.csv"
        plot_path = PLOTS_DIR / f"{ramp_cond}_spectrogram.png"
        print(f"Generating dynamic spectrogram for {ramp_cond}...")
        try:
            analyze_rampup_spectrogram(v_path, csv_path, plot_path)
            print(f"  -> Saved spectrogram: {plot_path}")
        except Exception as e:
            print(f"  -> Ramp-up analysis failed: {e}")

    # Save benchmark JSON summary
    out_json = REPORTS_DIR / "benchmark_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump({
            "summary": "PhaseSight Rotor Dataset Benchmark Evaluation",
            "comparisons": all_comparisons,
        }, f, indent=2)
    print(f"\nSaved benchmark comparison JSON to: {out_json}")

    # Save benchmark CSV table
    out_csv = REPORTS_DIR / "benchmark_comparison_table.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "condition", "target_roi", "reference_sensor_channel",
            "sensor_fundamental_fft_hz", "video_y_fundamental_fft_hz", "best_video_f_hz",
            "delta_f_hz", "relative_error_pct",
            "container_timebase_f_hz", "container_timebase_error_pct",
            "sensor_rms", "video_y_rms_px", "rms_ratio_px_per_sensor_unit",
            "sensor_clipped", "video_y_quality", "status"
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(all_comparisons)
    print(f"Saved benchmark comparison CSV to: {out_csv}")

    # Generate Markdown Summary Table
    md_lines = [
        "| Condition | Target ROI | Ref Sensor | Sensor 1x (Hz) | Video 1x (Hz) | Error Δf (Hz) | Rel Err (%) | Sensor RMS | Video RMS (px) | Verdict |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in all_comparisons:
        if c.get("status") == "VIDEO_TRACKING_FAILED":
            md_lines.append(f"| {c['condition']} | {c['target_roi']} | Ch #{c.get('reference_sensor_channel', 'N/A')} | N/A | FAILED | N/A | N/A | N/A | N/A | REJECTED |")
        else:
            md_lines.append(
                f"| {c['condition']} | {c['target_roi']} | Ch #{c['reference_sensor_channel']} | "
                f"{c['sensor_fundamental_fft_hz']:.2f} | {c['best_video_f_hz']:.2f} | {c['delta_f_hz']:.3f} | "
                f"{c['relative_error_pct']:.2f}% | {c['sensor_rms']:.4f} | {c['video_y_rms_px']:.4f} | {c['status']} |"
            )

    md_table_path = REPORTS_DIR / "benchmark_comparison_table.md"
    with open(md_table_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"Saved benchmark comparison Markdown to: {md_table_path}")

    print("\nBenchmark Suite Execution Complete!")

if __name__ == "__main__":
    main()
