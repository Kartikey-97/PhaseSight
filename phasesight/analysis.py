from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import signal


@dataclass(frozen=True)
class SpectrumResult:
    frequencies_hz: np.ndarray
    psd_px2_per_hz: np.ndarray
    dominant_frequency_hz: float
    peak_power: float
    peak_to_median_db: float
    second_harmonic_ratio: float | None
    rms_px: float
    sampling_rate_hz: float
    frequency_resolution_hz: float
    sample_count: int


def classify_signal_quality(
    result: SpectrumResult,
    *,
    min_peak_to_median_db: float = 10.0,
    mean_phase_response: float | None = None,
    min_phase_response: float = 0.15,
) -> str:
    """Return VALID or LOW_SIGNAL using a provisional spectral prominence gate.

    The 10 dB gate is a starting point for bench testing, not a universal
    calibrated threshold. It must be reviewed against real-camera null clips.
    """
    if result.peak_to_median_db < min_peak_to_median_db:
        return "LOW_SIGNAL"
    if mean_phase_response is not None and mean_phase_response < min_phase_response:
        return "LOW_SIGNAL"
    return "VALID"


def is_anchor_contaminated(
    relative_result: SpectrumResult,
    anchor_result: SpectrumResult,
    *,
    frequency_tolerance_hz: float | None = None,
    min_anchor_peak_to_median_db: float = 10.0,
) -> bool:
    """Flag a relative peak also strongly present in the static anchor ROI.

    This is a conservative environmental/shared-motion check. It does not
    prove the cause; the operator should inspect the anchor ROI and recording.
    """
    tolerance = (
        float(frequency_tolerance_hz)
        if frequency_tolerance_hz is not None
        else max(
            relative_result.frequency_resolution_hz,
            anchor_result.frequency_resolution_hz,
        )
    )

    # Condition A: existing global peak check
    same_peak = (
        abs(relative_result.dominant_frequency_hz - anchor_result.dominant_frequency_hz)
        <= tolerance
    )
    if same_peak and anchor_result.peak_to_median_db >= min_anchor_peak_to_median_db:
        return True

    # Condition B: DEF-01 secondary anchor peak check
    freqs = anchor_result.frequencies_hz
    psd = anchor_result.psd_px2_per_hz
    if (
        freqs is not None
        and psd is not None
        and len(freqs) >= 5
        and len(freqs) == len(psd)
    ):
        window_indices = np.flatnonzero(
            np.abs(freqs - relative_result.dominant_frequency_hz) <= tolerance
        )
        if len(window_indices) > 0:
            cand_idx = int(window_indices[np.argmax(psd[window_indices])])
            is_interior = 0 < cand_idx < len(psd) - 1
            if is_interior:
                is_local_peak = (
                    psd[cand_idx] >= psd[cand_idx - 1]
                    and psd[cand_idx] >= psd[cand_idx + 1]
                    and (
                        psd[cand_idx] > psd[cand_idx - 1]
                        or psd[cand_idx] > psd[cand_idx + 1]
                    )
                )
                if is_local_peak:
                    nyquist = (
                        (anchor_result.sampling_rate_hz / 2.0)
                        if anchor_result.sampling_rate_hz > 0
                        else float(freqs[-1])
                    )
                    in_band_mask = (freqs >= 0.5) & (freqs <= 0.95 * nyquist)
                    in_band_indices = np.flatnonzero(in_band_mask)

                    anchor_dom_idx = int(
                        np.argmin(np.abs(freqs - anchor_result.dominant_frequency_hz))
                    )

                    bg_indices = [
                        i
                        for i in in_band_indices
                        if abs(i - cand_idx) > 2 and abs(i - anchor_dom_idx) > 2
                    ]
                    if len(bg_indices) < 3:
                        bg_indices = [
                            i for i in in_band_indices if abs(i - cand_idx) > 2
                        ]

                    bg_median = (
                        float(np.median(psd[bg_indices]))
                        if len(bg_indices) > 0
                        else 0.0
                    )
                    cand_prominence_db = float(
                        10.0
                        * np.log10(
                            max(float(psd[cand_idx]), 1e-30) / max(bg_median, 1e-30)
                        )
                    )
                    if cand_prominence_db >= min_anchor_peak_to_median_db:
                        return True

    return False


def analyse_displacement(
    timestamps_s: np.ndarray,
    displacement_px: np.ndarray,
    *,
    min_frequency_hz: float = 0.5,
    max_frequency_hz: float | None = None,
    nperseg: int = 256,
    min_harmonic_prominence_db: float = 10.0,
    max_tolerated_gap_ratio: float = 1.5,
    max_tolerated_jitter: float = 0.15,
) -> SpectrumResult:
    """Estimate dominant frequency and displacement RMS from a video trace.

    The function accepts timestamped data, checks sample timing, and resamples
    small timestamp irregularities onto a uniform grid before Welch analysis.
    It rejects severe timing jitter or large missing intervals (>1.5x median dt)
    to prevent unvalidated interpolation from creating false vibration peaks.
    It never reports mm/s: the output remains in image pixels.
    """
    t = np.asarray(timestamps_s, dtype=np.float64)
    x = np.asarray(displacement_px, dtype=np.float64)
    if t.ndim != 1 or x.ndim != 1 or len(t) != len(x):
        raise ValueError("timestamps_s and displacement_px must be 1D arrays of equal length")
    if len(t) < 32:
        raise ValueError("At least 32 samples are required for spectral analysis")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(x)):
        raise ValueError("Input arrays contain NaN or infinite values")
    dt = np.diff(t)
    if np.any(dt <= 0):
        raise ValueError("timestamps_s must be strictly increasing")

    median_dt = float(np.median(dt))
    fs = 1.0 / median_dt
    if not np.isfinite(fs) or fs <= 0:
        raise ValueError("Could not estimate a valid sampling rate")

    max_gap_ratio = float(np.max(dt) / median_dt) if median_dt > 0 else 0.0
    jitter_fraction = float(np.std(dt) / median_dt) if median_dt > 0 else 0.0

    if max_gap_ratio > max_tolerated_gap_ratio:
        raise ValueError(
            f"Severe timestamp gap detected: max frame interval {float(np.max(dt)):.4f}s is {max_gap_ratio:.1f}x "
            f"the median interval {median_dt:.4f}s (> {max_tolerated_gap_ratio:.1f}x threshold). "
            "Cannot interpolate unvalidated missing intervals for vibration analysis."
        )
    if jitter_fraction > max_tolerated_jitter:
        raise ValueError(
            f"Severe timestamp jitter detected: jitter ratio {jitter_fraction:.2%} exceeds "
            f"stability threshold {max_tolerated_jitter:.2%}. Resampling would distort spectral estimation."
        )

    # Welch assumes uniformly sampled data. Resample only when minor timestamp
    # jitter is present; the report exposes the inferred sampling rate.
    uniform_t = np.linspace(t[0], t[-1], len(t), dtype=np.float64)
    if jitter_fraction > 0.002 or not np.allclose(dt, median_dt, rtol=2e-3, atol=1e-9):
        x = np.interp(uniform_t, t, x)
        t = uniform_t
        fs = (len(t) - 1) / (t[-1] - t[0])

    x = signal.detrend(x, type="linear")
    rms = float(np.sqrt(np.mean(np.square(x))))
    segment_length = int(min(max(32, nperseg), len(x)))
    if segment_length < 32:
        raise ValueError("Not enough samples for Welch analysis")
    frequencies, psd = signal.welch(
        x,
        fs=fs,
        window="hann",
        nperseg=segment_length,
        noverlap=segment_length // 2,
        detrend="constant",
        scaling="density",
        average="median",
    )

    nyquist = fs / 2.0
    upper = min(max_frequency_hz if max_frequency_hz is not None else nyquist * 0.9, nyquist * 0.95)
    if min_frequency_hz < 0 or upper <= min_frequency_hz:
        raise ValueError("Frequency band must satisfy 0 <= min_frequency_hz < max_frequency_hz < Nyquist")
    band = (frequencies >= min_frequency_hz) & (frequencies <= upper)
    if not np.any(band):
        raise ValueError("No Welch frequency bins fall inside the requested analysis band")
    band_indices = np.flatnonzero(band)
    peak_index = int(band_indices[np.argmax(psd[band])])
    peak_frequency = float(frequencies[peak_index])
    background_bins = band_indices[np.abs(band_indices - peak_index) > 2]
    background_median = float(np.median(psd[background_bins])) if len(background_bins) else 0.0
    peak_to_median_db = float(10.0 * np.log10(max(float(psd[peak_index]), 1e-30) / max(background_median, 1e-30)))

    # Three-bin parabolic interpolation improves peak localization but does
    # not create additional physical frequency resolution.
    if 0 < peak_index < len(psd) - 1:
        y0, y1, y2 = np.log(np.maximum(psd[peak_index - 1 : peak_index + 2], np.finfo(float).tiny))
        denominator = y0 - 2.0 * y1 + y2
        if abs(denominator) > 1e-12:
            offset = float(np.clip(0.5 * (y0 - y2) / denominator, -1.0, 1.0))
            peak_frequency += offset * (frequencies[1] - frequencies[0])

    second_harmonic_ratio = None
    second_harmonic_hz = 2.0 * peak_frequency
    if second_harmonic_hz < upper:
        half_width = max(1.5 * (frequencies[1] - frequencies[0]), 0.15)
        fundamental_band = np.abs(frequencies - peak_frequency) <= half_width
        harmonic_band = np.abs(frequencies - second_harmonic_hz) <= half_width
        harmonic_indices = np.flatnonzero(harmonic_band)

        if len(harmonic_indices) > 0:
            cand_idx = int(harmonic_indices[np.argmax(psd[harmonic_indices])])
            cand_power = float(psd[cand_idx])

            # Require strict local maximum within spectrum to reject monotonic sidelobes
            is_local_max = bool(
                0 < cand_idx < len(psd) - 1
                and psd[cand_idx] > psd[cand_idx - 1]
                and psd[cand_idx] > psd[cand_idx + 1]
            )

            # Measure local background around 2x harmonic (+- 3.0 Hz excluding cand peak & fundamental)
            local_mask = (frequencies >= max(min_frequency_hz, second_harmonic_hz - 3.0)) & (
                frequencies <= min(upper, second_harmonic_hz + 3.0)
            )
            local_indices = np.flatnonzero(local_mask)
            local_bg_indices = [
                i for i in local_indices
                if abs(i - cand_idx) > 2 and abs(i - peak_index) > 3
            ]
            if len(local_bg_indices) >= 3:
                local_bg = float(np.median(psd[local_bg_indices]))
            else:
                bg_indices = band_indices[np.abs(band_indices - peak_index) > 2]
                local_bg = float(np.median(psd[bg_indices])) if len(bg_indices) else 1e-30

            harmonic_prominence_db = float(
                10.0 * np.log10(max(cand_power, 1e-30) / max(local_bg, 1e-30))
            )

            if is_local_max and harmonic_prominence_db >= min_harmonic_prominence_db:
                fundamental_power = float(np.sum(psd[fundamental_band]))
                harmonic_power = float(np.sum(psd[harmonic_band]))
                if fundamental_power > 1e-20:
                    second_harmonic_ratio = harmonic_power / fundamental_power

    return SpectrumResult(
        frequencies_hz=frequencies,
        psd_px2_per_hz=psd,
        dominant_frequency_hz=peak_frequency,
        peak_power=float(psd[peak_index]),
        peak_to_median_db=peak_to_median_db,
        second_harmonic_ratio=second_harmonic_ratio,
        rms_px=rms,
        sampling_rate_hz=float(fs),
        frequency_resolution_hz=float(fs / segment_length),
        sample_count=len(x),
    )


@dataclass(frozen=True)
class ComparisonResult:
    baseline_rms_px: float
    current_rms_px: float
    rms_change_percent: float
    baseline_frequency_hz: float
    current_frequency_hz: float
    frequency_change_hz: float
    status: str


def compare_to_baseline(
    baseline: SpectrumResult,
    current: SpectrumResult,
    *,
    warning_rms_change_percent: float = 25.0,
    alert_rms_change_percent: float = 50.0,
    frequency_tolerance_hz: float | None = None,
) -> ComparisonResult:
    """Compare two captures. Status means change, not a diagnosed fault."""
    if baseline.sampling_rate_hz <= 0 or current.sampling_rate_hz <= 0:
        raise ValueError("Sampling rates must be positive")
    if baseline.rms_px <= 1e-9:
        raise ValueError("Baseline RMS is too close to zero for a stable percentage comparison")

    change = 100.0 * (current.rms_px - baseline.rms_px) / baseline.rms_px
    abs_change = abs(change)
    tolerance = frequency_tolerance_hz or max(
        baseline.frequency_resolution_hz, current.frequency_resolution_hz
    )
    frequency_delta = abs(current.dominant_frequency_hz - baseline.dominant_frequency_hz)

    if abs_change >= alert_rms_change_percent or frequency_delta > 2.0 * tolerance:
        status = "ALERT_CHANGE"
    elif abs_change >= warning_rms_change_percent or frequency_delta > tolerance:
        status = "WARNING_CHANGE"
    else:
        status = "NO_MAJOR_CHANGE"

    return ComparisonResult(
        baseline_rms_px=baseline.rms_px,
        current_rms_px=current.rms_px,
        rms_change_percent=change,
        baseline_frequency_hz=baseline.dominant_frequency_hz,
        current_frequency_hz=current.dominant_frequency_hz,
        frequency_change_hz=frequency_delta,
        status=status,
    )


def compare_inspection_summaries(
    baseline: dict,
    current: dict,
    *,
    axis: str = "x",
    warning_rms_change_percent: float = 25.0,
    alert_rms_change_percent: float = 50.0,
    noise_floor_summary: dict | None = None,
    noise_floor_multiple: float = 3.0,
    baseline_label: str = "baseline",
    current_label: str = "current",
) -> dict:
    """Compare two video inspection summary dictionaries.

    Returns a report dictionary containing the comparison status and metrics.
    A change flag (WARNING_CHANGE / ALERT_CHANGE) is a screening result indicating
    measured signal change relative to baseline, not a diagnosed mechanical fault.
    """
    axis_key = f"{axis.lower()}_axis"
    if axis_key not in baseline or axis_key not in current:
        raise ValueError(f"Summary dictionaries must contain '{axis_key}'")

    base_axis = baseline[axis_key]
    curr_axis = current[axis_key]

    noise_floor_rms = None
    noise_floor_ok = True
    if noise_floor_summary is not None:
        if axis_key not in noise_floor_summary:
            raise ValueError(f"Noise floor summary must contain '{axis_key}'")
        noise_floor_rms = float(noise_floor_summary[axis_key]["rms_displacement_px"])
        required_rms = noise_floor_multiple * noise_floor_rms
        noise_floor_ok = (
            base_axis["rms_displacement_px"] >= required_rms
            and curr_axis["rms_displacement_px"] >= required_rms
        )

    if (
        base_axis.get("signal_quality") != "VALID"
        or curr_axis.get("signal_quality") != "VALID"
        or not noise_floor_ok
    ):
        status = "INSUFFICIENT_SIGNAL"
        rms_change = None
        frequency_change = None
    elif base_axis["rms_displacement_px"] <= 1e-9:
        status = "INVALID_BASELINE"
        rms_change = None
        frequency_change = None
    else:
        rms_change = 100.0 * (
            curr_axis["rms_displacement_px"] - base_axis["rms_displacement_px"]
        ) / base_axis["rms_displacement_px"]
        frequency_change = abs(
            curr_axis["dominant_frequency_hz"] - base_axis["dominant_frequency_hz"]
        )
        tolerance = max(
            base_axis.get("frequency_resolution_hz", 0.0),
            curr_axis.get("frequency_resolution_hz", 0.0),
        )
        if abs(rms_change) >= alert_rms_change_percent or frequency_change > 2.0 * tolerance:
            status = "ALERT_CHANGE"
        elif abs(rms_change) >= warning_rms_change_percent or frequency_change > tolerance:
            status = "WARNING_CHANGE"
        else:
            status = "NO_MAJOR_CHANGE"

    return {
        "baseline": baseline_label,
        "current": current_label,
        "axis": axis.lower(),
        "baseline_rms_px": float(base_axis["rms_displacement_px"]),
        "current_rms_px": float(curr_axis["rms_displacement_px"]),
        "baseline_frequency_hz": float(base_axis["dominant_frequency_hz"]),
        "current_frequency_hz": float(curr_axis["dominant_frequency_hz"]),
        "rms_change_percent": rms_change,
        "frequency_change_hz": frequency_change,
        "noise_floor_rms_px": noise_floor_rms,
        "noise_floor_multiple": noise_floor_multiple if noise_floor_summary is not None else None,
        "status": status,
        "interpretation": "A change flag is a screening result, not a diagnosis of a specific fault.",
    }
