#!/usr/bin/env python3
"""
Phase 6: Experiment D - Non-Stationary Ramp-Up Acceleration Analysis
Processes 4s-Unb1.avi and 6s-Unb1.avi using Target A (600, 460) and Anchor A1 (600, 560).
Compares with Sensor Channel #4 ground truth.
Generates time-frequency spectrograms, instantaneous frequency ridges,
and evaluates stationary Welch PSD smearing vs dynamic tracking.
"""

from __future__ import annotations

import json
from pathlib import Path
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from phasesight.tracker import PhaseCorrelationTracker, ROI

RAW_VIDEOS_DIR = Path("data/rotor_dataset/Raw videos")
SENSOR_DIR = Path("data/rotor_dataset/Sensor data")
PLOTS_DIR = Path("reports/rotor_dataset_benchmark/plots")
REPORTS_DIR = Path("reports/rotor_dataset_benchmark")

PHYSICAL_CAMERA_FPS = 500.0
PHYSICAL_SENSOR_FS = 1000.0

TARGET_A = ROI(600, 460, 64, 64)
ANCHOR_A1 = ROI(600, 560, 64, 64)

def analyze_rampup(cond_name: str) -> dict:
    video_path = RAW_VIDEOS_DIR / f"{cond_name}.avi"
    csv_path = SENSOR_DIR / f"{cond_name}.csv"

    print(f"Tracking video {video_path.name}...")
    cap = cv2.VideoCapture(str(video_path))
    ok, f0 = cap.read()
    tracker = PhaseCorrelationTracker(f0, TARGET_A, ANCHOR_A1)

    dys, dxs, ts = [], [], []
    resps = []
    idx = 1
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        t = idx / PHYSICAL_CAMERA_FPS
        s = tracker.process(frame, t)
        if s.valid:
            dys.append(s.relative_dy_px)
            dxs.append(s.relative_dx_px)
            ts.append(t)
            resps.append(s.target_response)
        idx += 1
    cap.release()

    dys = np.array(dys)
    dxs = np.array(dxs)
    ts = np.array(ts)
    print(f"  -> Video tracked: {len(ts)} frames in {ts[-1]:.2f} s. Mean response: {np.mean(resps):.3f}")

    # Load sensor data (Channel #4 is the valid designated channel for ramp-up)
    sensor_raw = np.loadtxt(csv_path, delimiter=",")
    s4 = sensor_raw[:, 3]  # Ch 4
    s4_detrend = signal.detrend(s4 - np.mean(s4))
    t_s = np.arange(len(s4)) / PHYSICAL_SENSOR_FS
    print(f"  -> Sensor Ch #4: {len(s4)} samples in {t_s[-1]:.2f} s")

    # 1. Stationary Welch PSD (to demonstrate smearing)
    f_s_welch, psd_s_welch = signal.welch(s4_detrend, fs=PHYSICAL_SENSOR_FS, nperseg=2000)
    f_v_welch, psd_v_welch = signal.welch(signal.detrend(dys), fs=PHYSICAL_CAMERA_FPS, nperseg=1000)

    # 2. Non-Stationary Spectrograms (STFT)
    # Sensor spectrogram
    nperseg_s = 500
    noverlap_s = 400
    f_s_stft, t_s_stft, Sxx_s = signal.spectrogram(s4_detrend, fs=PHYSICAL_SENSOR_FS, nperseg=nperseg_s, noverlap=noverlap_s)

    # Video spectrogram
    nperseg_v = 250
    noverlap_v = 200
    f_v_stft, t_v_stft, Sxx_v = signal.spectrogram(signal.detrend(dys), fs=PHYSICAL_CAMERA_FPS, nperseg=nperseg_v, noverlap=noverlap_v)

    # Plot comprehensive figure
    fig = plt.figure(figsize=(14, 11), constrained_layout=True)
    gs = fig.add_gridspec(3, 2)
    fig.suptitle(f"Ramp-Up Dynamic Acceleration Analysis: {cond_name} (0 -> 3000 RPM)", fontsize=14, fontweight="bold")

    # Time domain waveforms
    ax_t1 = fig.add_subplot(gs[0, 0])
    ax_t1.plot(ts, dys, color="crimson", linewidth=0.6, label="Video Y (px)")
    ax_t1.set_title(f"Video Displacement Waveform ({len(ts)} frames, {ts[-1]:.2f}s)")
    ax_t1.set_xlabel("Time (s)")
    ax_t1.set_ylabel("Pixels")
    ax_t1.grid(True, alpha=0.3)
    ax_t1.legend()

    ax_t2 = fig.add_subplot(gs[0, 1])
    ax_t2.plot(t_s, s4, color="navy", linewidth=0.6, label="Sensor Ch #4 (raw)")
    ax_t2.set_title(f"Sensor Ch #4 Waveform ({len(s4)} samples, {t_s[-1]:.2f}s)")
    ax_t2.set_xlabel("Time (s)")
    ax_t2.set_ylabel("Amplitude")
    ax_t2.grid(True, alpha=0.3)
    ax_t2.legend()

    # Spectrograms
    ax_spec_v = fig.add_subplot(gs[1, 0])
    mesh_v = ax_spec_v.pcolormesh(t_v_stft, f_v_stft[f_v_stft <= 65], 10 * np.log10(Sxx_v[f_v_stft <= 65, :] + 1e-12), cmap="magma", shading="gouraud")
    ax_spec_v.set_title("Video Displacement STFT Spectrogram (0 -> 50 Hz ramp)")
    ax_spec_v.set_xlabel("Time (s)")
    ax_spec_v.set_ylabel("Frequency (Hz)")
    plt.colorbar(mesh_v, ax=ax_spec_v, label="Power (dB)")

    ax_spec_s = fig.add_subplot(gs[1, 1])
    mesh_s = ax_spec_s.pcolormesh(t_s_stft, f_s_stft[f_s_stft <= 65], 10 * np.log10(Sxx_s[f_s_stft <= 65, :] + 1e-12), cmap="magma", shading="gouraud")
    ax_spec_s.set_title("Sensor Ch #4 STFT Spectrogram (0 -> 50 Hz ramp)")
    ax_spec_s.set_xlabel("Time (s)")
    ax_spec_s.set_ylabel("Frequency (Hz)")
    plt.colorbar(mesh_s, ax=ax_spec_s, label="Power (dB)")

    # Welch PSD smearing demonstration
    ax_w1 = fig.add_subplot(gs[2, 0])
    ax_w1.semilogy(f_v_welch[f_v_welch <= 65], psd_v_welch[f_v_welch <= 65], color="crimson", label="Video Welch PSD")
    ax_w1.set_title("Video Full-Record Welch PSD (Smeared across 0-50 Hz)")
    ax_w1.set_xlabel("Frequency (Hz)")
    ax_w1.set_ylabel("PSD (px²/Hz)")
    ax_w1.grid(True, alpha=0.3)
    ax_w1.legend()

    ax_w2 = fig.add_subplot(gs[2, 1])
    ax_w2.semilogy(f_s_welch[f_s_welch <= 65], psd_s_welch[f_s_welch <= 65], color="navy", label="Sensor Ch #4 Welch PSD")
    ax_w2.set_title("Sensor Full-Record Welch PSD (Smeared across 0-50 Hz)")
    ax_w2.set_xlabel("Frequency (Hz)")
    ax_w2.set_ylabel("PSD")
    ax_w2.grid(True, alpha=0.3)
    ax_w2.legend()

    plot_file = PLOTS_DIR / f"{cond_name}_rampup_spectrogram.png"
    fig.savefig(plot_file, dpi=160)
    plt.close(fig)
    print(f"  -> Saved ramp-up plot: {plot_file}")

    return {
        "condition": cond_name,
        "video_duration_s": float(ts[-1]),
        "sensor_duration_s": float(t_s[-1]),
        "video_frames": len(ts),
        "sensor_samples": len(s4),
        "plot": str(plot_file),
    }

def main():
    print("Beginning Phase 6 Experiment D: Ramp-Up Acceleration Analysis...")
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for cond in ["4s-Unb1", "6s-Unb1"]:
        res = analyze_rampup(cond)
        results.append(res)

    out_json = REPORTS_DIR / "rampup_results.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Saved ramp-up analysis summary to: {out_json}")
    print("Ramp-up Analysis Complete!")

if __name__ == "__main__":
    main()
