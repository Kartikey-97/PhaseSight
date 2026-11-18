from __future__ import annotations

from dataclasses import asdict

import numpy as np

from .analysis import analyse_displacement, classify_signal_quality
from .synthetic import (
    DEFAULT_ANCHOR_ROI,
    DEFAULT_TARGET_ROI,
    SyntheticConfig,
    make_scene,
)
from .tracker import PhaseCorrelationTracker


def validate_synthetic_case(config: SyntheticConfig, *, expected_frequency_hz: float | None) -> dict:
    frames, truth = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    measured = []
    response = []
    times = []
    for i, frame in enumerate(frames[1:], start=1):
        sample = tracker.process(frame, i / config.fps)
        measured.append(sample.relative_dx_px)
        response.append(min(sample.target_response, sample.anchor_response))
        times.append(i / config.fps)

    measured_array = np.asarray(measured)
    truth_array = truth[1:]
    error = measured_array - truth_array
    rmse = float(np.sqrt(np.mean(np.square(error))))
    corr = (
        float(np.corrcoef(measured_array, truth_array)[0, 1])
        if np.std(measured_array) > 1e-10 and np.std(truth_array) > 1e-10
        else None
    )
    spec = analyse_displacement(
        np.asarray(times),
        measured_array,
        min_frequency_hz=1.0,
        max_frequency_hz=min(20.0, config.fps * 0.45),
        nperseg=min(256, len(measured_array)),
    )
    freq_error = None if expected_frequency_hz is None else abs(spec.dominant_frequency_hz - expected_frequency_hz)

    return {
        "case": "synthetic",
        "fps": config.fps,
        "duration_s": config.duration_s,
        "expected_frequency_hz": expected_frequency_hz,
        "measured_frequency_hz": spec.dominant_frequency_hz,
        "frequency_error_hz": freq_error,
        "displacement_rmse_px": rmse,
        "displacement_correlation": corr,
        "measured_rms_px": spec.rms_px,
        "peak_to_median_db": spec.peak_to_median_db,
        "second_harmonic_ratio": spec.second_harmonic_ratio,
        "signal_quality": classify_signal_quality(spec, mean_phase_response=float(np.mean(response))),
        "mean_phase_response": float(np.mean(response)),
        "max_frequency_hz": config.fps / 2.0,
        "status": "PASS" if (
            (expected_frequency_hz is None or (freq_error is not None and freq_error <= max(0.5, spec.frequency_resolution_hz)))
            and (expected_frequency_hz is None or (corr is not None and corr >= 0.80))
            and (expected_frequency_hz is None or classify_signal_quality(spec, mean_phase_response=float(np.mean(response))) == "VALID")
        ) else "REVIEW",
    }


def run_validation_suite() -> list[dict]:
    cases = [
        (
            "clean target vibration",
            SyntheticConfig(
                vibration_frequency_hz=8.5,
                vibration_amplitude_px=0.35,
                camera_amplitude_px=0.0,
                lighting_flicker_depth=0.0,
                noise_sigma=0.5,
                seed=1,
            ),
            8.5,
        ),
        (
            "camera shake + target vibration",
            SyntheticConfig(
                vibration_frequency_hz=8.5,
                vibration_amplitude_px=0.35,
                camera_amplitude_px=0.65,
                camera_y_amplitude_px=0.25,
                lighting_flicker_depth=0.08,
                noise_sigma=1.5,
                seed=2,
            ),
            8.5,
        ),
        (
            "camera shake only (null control)",
            SyntheticConfig(
                vibration_frequency_hz=8.5,
                vibration_amplitude_px=0.0,
                camera_amplitude_px=0.65,
                camera_y_amplitude_px=0.25,
                lighting_flicker_depth=0.08,
                noise_sigma=1.5,
                seed=3,
            ),
            None,
        ),
        (
            "target vibration + 2x harmonic",
            SyntheticConfig(
                vibration_frequency_hz=8.5,
                vibration_amplitude_px=0.25,
                second_harmonic_amplitude_px=0.08,
                camera_amplitude_px=0.4,
                lighting_flicker_depth=0.05,
                noise_sigma=1.5,
                seed=4,
            ),
            8.5,
        ),
    ]
    results = []
    for name, config, expected in cases:
        result = validate_synthetic_case(config, expected_frequency_hz=expected)
        result["name"] = name
        # Null-control criterion is different: residual RMS should stay small.
        if expected is None:
            result["status"] = "PASS" if (
                result["measured_rms_px"] < 0.10 and result["signal_quality"] == "LOW_SIGNAL"
            ) else "REVIEW"
        results.append(result)
    return results
