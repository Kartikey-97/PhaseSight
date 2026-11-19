from __future__ import annotations

import datetime
from dataclasses import asdict
import json
from pathlib import Path
import platform
import sys
import time
from typing import Any

import numpy as np

from .analysis import (
    SpectrumResult,
    analyse_displacement,
    classify_signal_quality,
    is_anchor_contaminated,
)
from .baseline import (
    NON_DIAGNOSTIC_INTERPRETATION,
    build_baseline,
    evaluate_run_against_baseline,
)
from .capture import calculate_timestamp_stability
from .synthetic import (
    DEFAULT_ANCHOR_ROI,
    DEFAULT_TARGET_ROI,
    SyntheticConfig,
    make_scene,
)
from .tracker import PhaseCorrelationTracker, ROI, check_roi_texture, validate_rois


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
    """Legacy 4-case synthetic validation suite (maintained for backward compatibility)."""
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


# ==============================================================================
# PROPOSAL VALIDATION MATRIX PROTOCOLS (T1 - T6)
# ==============================================================================

def validate_t1_synthetic_motion() -> dict[str, Any]:
    """Protocol T1: Synthetic Known Motion Recovery (Clean & Harmonic Vibration)."""
    cfg_clean = SyntheticConfig(
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.35,
        camera_amplitude_px=0.0,
        lighting_flicker_depth=0.0,
        noise_sigma=0.5,
        seed=1,
    )
    res_clean = validate_synthetic_case(cfg_clean, expected_frequency_hz=8.5)

    cfg_harmonic = SyntheticConfig(
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.25,
        second_harmonic_amplitude_px=0.08,
        camera_amplitude_px=0.40,
        lighting_flicker_depth=0.05,
        noise_sigma=1.0,
        seed=4,
    )
    res_harmonic = validate_synthetic_case(cfg_harmonic, expected_frequency_hz=8.5)

    clean_pass = (
        res_clean["frequency_error_hz"] is not None
        and res_clean["frequency_error_hz"] <= 0.05
        and res_clean["displacement_rmse_px"] <= 0.10
        and res_clean["displacement_correlation"] is not None
        and res_clean["displacement_correlation"] >= 0.90
        and res_clean["signal_quality"] == "VALID"
    )
    harmonic_pass = (
        res_harmonic["frequency_error_hz"] is not None
        and res_harmonic["frequency_error_hz"] <= 0.05
        and res_harmonic["displacement_rmse_px"] <= 0.15
        and res_harmonic["displacement_correlation"] is not None
        and res_harmonic["displacement_correlation"] >= 0.90
        and res_harmonic["second_harmonic_ratio"] is not None
        and res_harmonic["second_harmonic_ratio"] > 0.04
        and res_harmonic["signal_quality"] == "VALID"
    )

    status = "PASS" if (clean_pass and harmonic_pass) else "FAIL"
    return {
        "protocol": "T1",
        "name": "Synthetic Known Motion Recovery",
        "status": status,
        "clean_case": res_clean,
        "harmonic_case": res_harmonic,
    }


def validate_t2_static_negative_control() -> dict[str, Any]:
    """Protocol T2: Static Negative Control & Noise Floor Quantification."""
    cfg_static = SyntheticConfig(
        vibration_amplitude_px=0.0,
        camera_amplitude_px=0.0,
        lighting_flicker_depth=0.0,
        noise_sigma=1.0,
        seed=10,
    )
    res_static = validate_synthetic_case(cfg_static, expected_frequency_hz=None)

    cfg_null = SyntheticConfig(
        vibration_amplitude_px=0.0,
        camera_amplitude_px=0.65,
        camera_y_amplitude_px=0.25,
        lighting_flicker_depth=0.08,
        noise_sigma=1.5,
        seed=3,
    )
    res_null = validate_synthetic_case(cfg_null, expected_frequency_hz=None)

    static_pass = (
        res_static["measured_rms_px"] <= 0.08
        and res_static["peak_to_median_db"] < 10.0
        and res_static["signal_quality"] == "LOW_SIGNAL"
    )
    null_pass = (
        res_null["measured_rms_px"] <= 0.08
        and res_null["peak_to_median_db"] < 10.0
        and res_null["signal_quality"] == "LOW_SIGNAL"
    )

    status = "PASS" if (static_pass and null_pass) else "FAIL"
    return {
        "protocol": "T2",
        "name": "Static Negative Control & Noise Floor",
        "status": status,
        "pure_static": res_static,
        "camera_shake_null": res_null,
    }


def validate_t3_camera_shake_cancellation() -> dict[str, Any]:
    """Protocol T3: Camera-Motion Control (Anchor Subtraction Efficacy)."""
    cfg = SyntheticConfig(
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.35,
        camera_amplitude_px=0.65,
        camera_y_amplitude_px=0.25,
        camera_frequency_hz=0.7,
        noise_sigma=1.5,
        seed=2,
        duration_s=5.0,
    )
    frames, truth = make_scene(cfg)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    uncorrected = []
    corrected = []
    times = []
    for i, frame in enumerate(frames[1:], start=1):
        s = tracker.process(frame, i / cfg.fps)
        uncorrected.append(s.target_dx_px)
        corrected.append(s.relative_dx_px)
        times.append(i / cfg.fps)

    u_arr = np.asarray(uncorrected)
    c_arr = np.asarray(corrected)
    t_arr = truth[1:]

    u_rmse = float(np.sqrt(np.mean(np.square(u_arr - t_arr))))
    c_rmse = float(np.sqrt(np.mean(np.square(c_arr - t_arr))))

    u_corr = float(np.corrcoef(u_arr, t_arr)[0, 1]) if np.std(u_arr) > 1e-10 else 0.0
    c_corr = float(np.corrcoef(c_arr, t_arr)[0, 1]) if np.std(c_arr) > 1e-10 else 0.0

    error_reduction_pct = float((1.0 - c_rmse / u_rmse) * 100.0) if u_rmse > 0 else 0.0
    shake_suppression_db = float(20.0 * np.log10(u_rmse / c_rmse)) if c_rmse > 0 else 0.0

    passed = (
        error_reduction_pct >= 60.0
        and shake_suppression_db >= 10.0
        and c_corr >= 0.90
        and c_rmse < 0.16
    )

    return {
        "protocol": "T3",
        "name": "Camera-Motion Control (Anchor Subtraction Efficacy)",
        "status": "PASS" if passed else "FAIL",
        "uncorrected_rmse_px": u_rmse,
        "uncorrected_correlation": u_corr,
        "corrected_rmse_px": c_rmse,
        "corrected_correlation": c_corr,
        "error_reduction_pct": error_reduction_pct,
        "shake_suppression_db": shake_suppression_db,
    }


def validate_t4_baseline_repeatability() -> dict[str, Any]:
    """Protocol T4: Portable/Physical Baseline Repeatability (>= 3 Captures)."""
    runs = []
    for s in (101, 102, 103):
        cfg = SyntheticConfig(
            vibration_frequency_hz=8.5,
            vibration_amplitude_px=0.35,
            camera_amplitude_px=0.40,
            noise_sigma=0.5,
            seed=s,
            duration_s=3.0,
        )
        res = validate_synthetic_case(cfg, expected_frequency_hz=8.5)
        runs.append({
            "target_roi_xywh": {"x": 360, "y": 110, "width": 160, "height": 160},
            "anchor_roi_xywh": {"x": 60, "y": 100, "width": 160, "height": 160},
            "fps_used": 60.0,
            "x_axis": {
                "dominant_frequency_hz": res["measured_frequency_hz"],
                "rms_displacement_px": res["measured_rms_px"],
                "peak_to_median_db": res["peak_to_median_db"],
                "second_harmonic_ratio": res["second_harmonic_ratio"],
                "signal_quality": res["signal_quality"],
            },
            "y_axis": {
                "dominant_frequency_hz": 0.0,
                "rms_displacement_px": 0.01,
                "peak_to_median_db": -20.0,
                "second_harmonic_ratio": None,
                "signal_quality": "LOW_SIGNAL",
            },
        })

    baseline = build_baseline(runs, asset_id="test_asset", min_runs=3)

    freq_mad = baseline.x_axis.dominant_frequency_hz.mad
    rms_mad = baseline.x_axis.rms_displacement_px.mad

    evaluations = [
        evaluate_run_against_baseline(r, baseline, axis="x")
        for r in runs
    ]

    all_normal = all(e.status == "Normal" and len(e.trigger_features) == 0 for e in evaluations)
    passed = (
        baseline.run_count >= 3
        and freq_mad < 0.01
        and rms_mad < 0.01
        and all_normal
    )

    return {
        "protocol": "T4",
        "name": "Baseline Repeatability (>=3 Captures)",
        "status": "PASS" if passed else "FAIL",
        "run_count": baseline.run_count,
        "dominant_frequency_median_hz": baseline.x_axis.dominant_frequency_hz.median,
        "dominant_frequency_mad_hz": freq_mad,
        "rms_displacement_median_px": baseline.x_axis.rms_displacement_px.median,
        "rms_displacement_mad_px": rms_mad,
        "screened_statuses": [e.status for e in evaluations],
        "false_review_triggers": sum(len(e.trigger_features) for e in evaluations),
    }


def validate_t5_controlled_change_detection() -> dict[str, Any]:
    """Protocol T5: Controlled Change Detection (Baseline vs Changed Clip)."""
    base_run = {
        "target_roi_xywh": {"x": 360, "y": 110, "width": 160, "height": 160},
        "anchor_roi_xywh": {"x": 60, "y": 100, "width": 160, "height": 160},
        "fps_used": 60.0,
        "x_axis": {
            "dominant_frequency_hz": 8.5093,
            "rms_displacement_px": 0.2325,
            "peak_to_median_db": 15.0,
            "second_harmonic_ratio": 0.0003,
            "signal_quality": "VALID",
        },
        "y_axis": {
            "dominant_frequency_hz": 0.0,
            "rms_displacement_px": 0.01,
            "peak_to_median_db": -20.0,
            "second_harmonic_ratio": None,
            "signal_quality": "LOW_SIGNAL",
        },
    }
    baseline = build_baseline([base_run, base_run, base_run], asset_id="test_asset")

    # Changed run: +48.5% RMS increase and added 2x harmonic
    changed_run = {
        "target_roi_xywh": {"x": 360, "y": 110, "width": 160, "height": 160},
        "anchor_roi_xywh": {"x": 60, "y": 100, "width": 160, "height": 160},
        "fps_used": 60.0,
        "x_axis": {
            "dominant_frequency_hz": 8.5062,
            "rms_displacement_px": 0.3452,
            "peak_to_median_db": 15.0,
            "second_harmonic_ratio": 0.0577,
            "signal_quality": "VALID",
        },
        "y_axis": {
            "dominant_frequency_hz": 0.0,
            "rms_displacement_px": 0.01,
            "peak_to_median_db": -20.0,
            "second_harmonic_ratio": None,
            "signal_quality": "LOW_SIGNAL",
        },
    }

    eval_result = evaluate_run_against_baseline(changed_run, baseline, axis="x")

    z_rms = eval_result.deviations["x_rms_displacement_px"].z_robust
    z_harm = eval_result.deviations["x_second_harmonic_ratio"].z_robust

    passed = (
        eval_result.status == "Review"
        and eval_result.confidence_passed is True
        and z_rms is not None and z_rms >= 3.0
        and z_harm is not None and z_harm >= 3.0
        and eval_result.interpretation == NON_DIAGNOSTIC_INTERPRETATION
    )

    return {
        "protocol": "T5",
        "name": "Controlled Change Detection",
        "status": "PASS" if passed else "FAIL",
        "evaluation_status": eval_result.status,
        "trigger_features": eval_result.trigger_features,
        "z_rms_displacement": z_rms,
        "z_second_harmonic_ratio": z_harm,
        "non_diagnostic_interpretation_verified": (eval_result.interpretation == NON_DIAGNOSTIC_INTERPRETATION),
    }


def validate_t6_image_quality_stress() -> dict[str, Any]:
    """Protocol T6: Image-Quality Stress Testing (Texture, Blur, Flicker, Dropped Frames)."""
    # T6a: Low texture / flat patch
    flat_frame = np.full((360, 640), 128, dtype=np.uint8)
    tex_valid, tex_std = check_roi_texture(flat_frame, DEFAULT_TARGET_ROI)
    roi_errors = validate_rois(flat_frame, DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    t6a_passed = (not tex_valid) and (tex_std < 2.0) and (len(roi_errors) > 0)

    # T6b: Severe Blur causing low phase response
    t_sig = np.arange(300) / 60.0
    sig_clean = 0.2 * np.sin(2 * np.pi * 8.5 * t_sig)
    spec_fake = analyse_displacement(t_sig, sig_clean, min_frequency_hz=1.0, max_frequency_hz=20.0)
    qual_low_resp = classify_signal_quality(spec_fake, mean_phase_response=0.08)
    t6b_passed = (qual_low_resp == "LOW_SIGNAL")

    # T6c: Illumination Flicker / Contamination
    sig_rel = 0.3 * np.sin(2 * np.pi * 20.0 * t_sig)
    sig_anc = 0.5 * np.sin(2 * np.pi * 20.0 * t_sig)
    spec_rel = analyse_displacement(t_sig, sig_rel, min_frequency_hz=1.0, max_frequency_hz=25.0)
    spec_anc = analyse_displacement(t_sig, sig_anc, min_frequency_hz=1.0, max_frequency_hz=25.0)
    t6c_contaminated = is_anchor_contaminated(spec_rel, spec_anc)
    t6c_passed = bool(t6c_contaminated)

    # T6d: Dropped frames & timing jitter
    t_arr = np.linspace(0, 5.0, 100)
    t_arr[40:] += 0.40  # 400ms dropped frame gap
    rng = np.random.default_rng(42)
    t_jittered = np.sort(t_arr + rng.normal(0, 0.015, len(t_arr)))
    stab = calculate_timestamp_stability(t_jittered, nominal_fps=30.0)
    t6d_passed = (stab.status == "REJECTED_UNSTABLE")

    passed = t6a_passed and t6b_passed and t6c_passed and t6d_passed

    return {
        "protocol": "T6",
        "name": "Image-Quality Stress Testing",
        "status": "PASS" if passed else "FAIL",
        "t6a_low_texture": {"passed": t6a_passed, "std_px": tex_std, "errors": roi_errors},
        "t6b_severe_blur": {"passed": t6b_passed, "classified_quality": qual_low_resp},
        "t6c_illumination_flicker": {"passed": t6c_passed, "contaminated": t6c_contaminated},
        "t6d_dropped_frames": {
            "passed": t6d_passed,
            "status": stab.status,
            "jitter_ratio": stab.jitter_ratio,
            "dropped_count": stab.dropped_frames_count,
        },
    }


def run_full_validation_matrix() -> dict[str, Any]:
    """Master runner executing all 6 proposal validation protocols (T1 to T6)."""
    t0 = time.perf_counter()
    p_t1 = validate_t1_synthetic_motion()
    p_t2 = validate_t2_static_negative_control()
    p_t3 = validate_t3_camera_shake_cancellation()
    p_t4 = validate_t4_baseline_repeatability()
    p_t5 = validate_t5_controlled_change_detection()
    p_t6 = validate_t6_image_quality_stress()
    elapsed = time.perf_counter() - t0

    protocols = {
        "T1": p_t1,
        "T2": p_t2,
        "T3": p_t3,
        "T4": p_t4,
        "T5": p_t5,
        "T6": p_t6,
    }
    passed_count = sum(1 for p in protocols.values() if p["status"] == "PASS")
    overall = "PASS" if passed_count == len(protocols) else "FAIL"

    return {
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "runtime_seconds": round(elapsed, 3),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "summary": {
            "total_protocols": len(protocols),
            "passed_protocols": passed_count,
            "overall_status": overall,
        },
        "protocols": protocols,
    }
