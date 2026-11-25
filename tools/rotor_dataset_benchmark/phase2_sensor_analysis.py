#!/usr/bin/env python3
"""
Phase 2: Sensor Reference Analysis
Performs independent spectral and time-domain analysis of eddy current sensor data.
Analyzes 1000rpm-Unb1.csv and extended dataset CSVs.
Computes RMS, Welch PSD, 1x/2x/3x harmonics, spectral prominence, noise floor,
and inspects saturation/clipping.
Generates reference plots and JSON summaries.
"""

from __future__ import annotations

import json
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

DATASET_ROOT = Path("data/rotor_dataset")
SENSOR_DIR = DATASET_ROOT / "Sensor data"
REPORTS_DIR = Path("reports/rotor_dataset_benchmark")
PLOTS_DIR = REPORTS_DIR / "plots"

NOMINAL_FREQS = {
    "1000rpm": 16.6667,
    "2000rpm": 33.3333,
    "3000rpm": 50.0000,
}

def analyze_sensor_file(file_path: Path, nominal_rpm: int | None = None) -> dict:
    data = np.loadtxt(file_path, delimiter=",")
    n_samples, n_channels = data.shape
    fs = 1000.0  # 1000 Hz from README.md
    duration_s = n_samples / fs
    t = np.arange(n_samples) / fs

    file_stem = file_path.stem
    speed_key = None
    for k in NOMINAL_FREQS:
        if k in file_stem:
            speed_key = k
            break

    nom_f0 = NOMINAL_FREQS[speed_key] if speed_key else (nominal_rpm / 60.0 if nominal_rpm else None)

    channel_results = []
    # Plot configuration
    fig, axes = plt.subplots(4, 2, figsize=(14, 12), constrained_layout=True)
    fig.suptitle(f"Sensor Reference Analysis: {file_path.name} (fs={fs:.0f} Hz, N={n_samples})", fontsize=14, fontweight="bold")

    for ch_idx in range(n_channels):
        raw = data[:, ch_idx]
        static_offset = float(np.mean(raw))
        zero_mean = raw - static_offset
        detrended = signal.detrend(zero_mean)
        rms_val = float(np.sqrt(np.mean(detrended**2)))
        ptp_val = float(np.ptp(raw))
        min_val = float(np.min(raw))
        max_val = float(np.max(raw))

        # Check clipping / saturation
        is_clipped = False
        clip_reason = []
        # Check if min or max repeated exactly or asymmetry is extreme
        min_hits = int(np.sum(np.isclose(raw, min_val, atol=1e-5)))
        max_hits = int(np.sum(np.isclose(raw, max_val, atol=1e-5)))
        if min_hits > 5:
            is_clipped = True
            clip_reason.append(f"Min value clipped ({min_hits} identical samples at {min_val:.4f})")
        if max_hits > 5:
            is_clipped = True
            clip_reason.append(f"Max value clipped ({max_hits} identical samples at {max_val:.4f})")
        # Extreme asymmetry check
        if abs(min_val) > 3.0 * abs(max_val) or abs(max_val) > 3.0 * abs(min_val):
            if ptp_val > 0.5:
                is_clipped = True
                clip_reason.append(f"Severe waveform asymmetry (min={min_val:.3f}, max={max_val:.3f})")

        # Spectral analysis with Welch
        # Choose nperseg based on duration
        nperseg = min(4000, n_samples)
        freqs, psd = signal.welch(detrended, fs=fs, nperseg=nperseg, noverlap=nperseg // 2)
        freq_resolution = fs / nperseg

        # High-resolution FFT peak search
        fft_vals = np.abs(np.fft.rfft(detrended))
        fft_freqs = np.fft.rfftfreq(n_samples, 1.0 / fs)
        fft_res = fs / n_samples

        # Search range for fundamental 1x
        if nom_f0:
            search_low = nom_f0 * 0.85
            search_high = nom_f0 * 1.15
        else:
            search_low = 10.0
            search_high = 60.0

        mask_1x = (freqs >= search_low) & (freqs <= search_high)
        if np.any(mask_1x):
            idx_sub = np.argmax(psd[mask_1x])
            f_1x = float(freqs[mask_1x][idx_sub])
            psd_1x = float(psd[mask_1x][idx_sub])
        else:
            idx_sub = np.argmax(psd[1:]) + 1
            f_1x = float(freqs[idx_sub])
            psd_1x = float(psd[idx_sub])

        # Refined FFT peak
        mask_fft = (fft_freqs >= search_low) & (fft_freqs <= search_high)
        if np.any(mask_fft):
            f_1x_fft = float(fft_freqs[mask_fft][np.argmax(fft_vals[mask_fft])])
        else:
            f_1x_fft = f_1x

        # Noise floor calculation (median of PSD excluding DC and harmonics)
        # 1x, 2x, 3x harmonic masks
        harmonic_mask = np.zeros_like(freqs, dtype=bool)
        for h_mult in [1, 2, 3]:
            h_f = h_mult * f_1x
            harmonic_mask |= (freqs >= h_f - 1.5) & (freqs <= h_f + 1.5)
        harmonic_mask |= (freqs < 1.0)  # exclude near-DC

        noise_floor_psd = float(np.median(psd[~harmonic_mask])) if np.any(~harmonic_mask) else 1e-12
        prominence_db = float(10.0 * np.log10(psd_1x / max(noise_floor_psd, 1e-12)))

        # 2x harmonic
        f_2x_nom = 2.0 * f_1x
        mask_2x = (freqs >= f_2x_nom - 1.5) & (freqs <= f_2x_nom + 1.5)
        if np.any(mask_2x):
            idx_2x = np.argmax(psd[mask_2x])
            f_2x = float(freqs[mask_2x][idx_2x])
            psd_2x = float(psd[mask_2x][idx_2x])
            ratio_2x = float(np.sqrt(psd_2x / max(psd_1x, 1e-12)))
            db_2x = float(10.0 * np.log10(psd_2x / max(noise_floor_psd, 1e-12)))
        else:
            f_2x = None
            psd_2x = None
            ratio_2x = None
            db_2x = None

        # 3x harmonic
        f_3x_nom = 3.0 * f_1x
        mask_3x = (freqs >= f_3x_nom - 1.5) & (freqs <= f_3x_nom + 1.5)
        if np.any(mask_3x):
            idx_3x = np.argmax(psd[mask_3x])
            f_3x = float(freqs[mask_3x][idx_3x])
            psd_3x = float(psd[mask_3x][idx_3x])
            ratio_3x = float(np.sqrt(psd_3x / max(psd_1x, 1e-12)))
            db_3x = float(10.0 * np.log10(psd_3x / max(noise_floor_psd, 1e-12)))
        else:
            f_3x = None
            psd_3x = None
            ratio_3x = None
            db_3x = None

        # Time domain plot (first 0.5s)
        ax_t = axes[ch_idx, 0]
        t_plot_mask = t <= 0.5
        ax_t.plot(t[t_plot_mask], raw[t_plot_mask], linewidth=0.8, color="C0", label="Signal")
        ax_t.set_title(f"Channel #{ch_idx+1}: Time Domain (First 0.5s, RMS={rms_val:.4f})", fontsize=10)
        ax_t.set_xlabel("Time (s)", fontsize=9)
        ax_t.set_ylabel("Amplitude (raw units)", fontsize=9)
        ax_t.grid(True, alpha=0.3)
        if is_clipped:
            ax_t.text(0.02, 0.85, "SATURATED / CLIPPED", transform=ax_t.transAxes, color="red", fontweight="bold")

        # Frequency domain plot
        ax_f = axes[ch_idx, 1]
        freq_plot_mask = freqs <= 150.0
        ax_f.semilogy(freqs[freq_plot_mask], psd[freq_plot_mask], color="C1", linewidth=0.9, label="PSD")
        ax_f.axvline(f_1x, color="red", linestyle="--", linewidth=1.2, label=f"1x: {f_1x_fft:.3f} Hz ({prominence_db:.1f} dB)")
        if f_2x:
            ax_f.axvline(f_2x, color="purple", linestyle=":", linewidth=1.0, label=f"2x: {f_2x:.2f} Hz")
        if f_3x:
            ax_f.axvline(f_3x, color="green", linestyle=":", linewidth=1.0, label=f"3x: {f_3x:.2f} Hz")
        ax_f.set_title(f"Channel #{ch_idx+1}: Welch PSD (Δf={freq_resolution:.3f} Hz)", fontsize=10)
        ax_f.set_xlabel("Frequency (Hz)", fontsize=9)
        ax_f.set_ylabel("PSD", fontsize=9)
        ax_f.grid(True, alpha=0.3)
        ax_f.legend(loc="upper right", fontsize=8)

        channel_results.append({
            "channel": ch_idx + 1,
            "static_offset": static_offset,
            "rms_displacement": rms_val,
            "peak_to_peak": ptp_val,
            "min_val": min_val,
            "max_val": max_val,
            "is_clipped_or_saturated": is_clipped,
            "clipping_reasons": clip_reason,
            "fundamental_1x_welch_hz": f_1x,
            "fundamental_1x_fft_hz": f_1x_fft,
            "fundamental_psd": psd_1x,
            "noise_floor_psd": noise_floor_psd,
            "prominence_1x_db": prominence_db,
            "harmonic_2x_hz": f_2x,
            "harmonic_2x_ratio": ratio_2x,
            "prominence_2x_db": db_2x,
            "harmonic_3x_hz": f_3x,
            "harmonic_3x_ratio": ratio_3x,
            "prominence_3x_db": db_3x,
            "welch_frequency_resolution_hz": freq_resolution,
            "fft_frequency_resolution_hz": fft_res,
        })

    PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_file = PLOTS_DIR / f"{file_stem}_sensor_psd.png"
    fig.savefig(plot_file, dpi=160)
    plt.close(fig)

    return {
        "file": file_path.name,
        "nominal_rpm": nominal_rpm or (int(speed_key.replace("rpm", "")) if speed_key else None),
        "nominal_frequency_hz": nom_f0,
        "samples": n_samples,
        "sampling_rate_hz": fs,
        "duration_s": duration_s,
        "plot_path": str(plot_file),
        "channels": channel_results,
    }


def main():
    print("Beginning Phase 2: Sensor Reference Analysis...")
    PLOTS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Primary benchmark file: 1000rpm-Unb1.csv
    primary_csv = SENSOR_DIR / "1000rpm-Unb1.csv"
    print(f"Analyzing primary benchmark: {primary_csv.name}...")
    primary_res = analyze_sensor_file(primary_csv, nominal_rpm=1000)

    # Print summary for primary file
    print(f"\n================ 1000rpm-Unb1.csv SENSOR REFERENCE ================")
    print(f"Nominal RPM:       1000 RPM (Nominal Fundamental: 16.667 Hz)")
    print(f"Sampling Rate:     1000 Hz, Duration: {primary_res['duration_s']:.2f} s ({primary_res['samples']} samples)")
    print(f"Welch Resolution:  Δf = {primary_res['channels'][0]['welch_frequency_resolution_hz']:.4f} Hz")
    print(f"FFT Resolution:    Δf = {primary_res['channels'][0]['fft_frequency_resolution_hz']:.4f} Hz")
    print("-------------------------------------------------------------------")
    for ch in primary_res["channels"]:
        print(
            f"Ch #{ch['channel']}: 1x={ch['fundamental_1x_fft_hz']:.3f} Hz | "
            f"Prom={ch['prominence_1x_db']:.1f} dB | "
            f"RMS={ch['rms_displacement']:.5f} | "
            f"2x={ch['harmonic_2x_hz'] if ch['harmonic_2x_hz'] else 'N/A'} | "
            f"3x={ch['harmonic_3x_hz'] if ch['harmonic_3x_hz'] else 'N/A'} | "
            f"Clipped={ch['is_clipped_or_saturated']}"
        )
    print("===================================================================\n")

    # 2. Analyze all remaining CSVs in the dataset
    all_sensor_results = [primary_res]
    for csv_path in sorted(SENSOR_DIR.glob("*.csv")):
        if csv_path.name == "1000rpm-Unb1.csv":
            continue
        print(f"Analyzing {csv_path.name}...")
        res = analyze_sensor_file(csv_path)
        all_sensor_results.append(res)

    out_json = REPORTS_DIR / "sensor_reference_analysis.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(all_sensor_results, f, indent=2)
    print(f"\nSaved all sensor reference analyses to: {out_json}")
    print("Phase 2 Sensor Reference Analysis Complete!")


if __name__ == "__main__":
    main()
