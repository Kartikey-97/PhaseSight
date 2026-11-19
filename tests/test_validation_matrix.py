from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from phasesight.baseline import NON_DIAGNOSTIC_INTERPRETATION
from phasesight.validation import (
    run_full_validation_matrix,
    run_validation_suite,
    validate_t1_synthetic_motion,
    validate_t2_static_negative_control,
    validate_t3_camera_shake_cancellation,
    validate_t4_baseline_repeatability,
    validate_t5_controlled_change_detection,
    validate_t6_image_quality_stress,
)


def test_t1_synthetic_motion():
    res = validate_t1_synthetic_motion()
    assert res["status"] == "PASS"

    clean = res["clean_case"]
    assert clean["frequency_error_hz"] is not None
    assert clean["frequency_error_hz"] <= 0.05
    assert clean["displacement_rmse_px"] <= 0.10
    assert clean["displacement_correlation"] >= 0.90
    assert clean["signal_quality"] == "VALID"

    harmonic = res["harmonic_case"]
    assert harmonic["frequency_error_hz"] is not None
    assert harmonic["frequency_error_hz"] <= 0.05
    assert harmonic["displacement_rmse_px"] <= 0.15
    assert harmonic["displacement_correlation"] >= 0.90
    assert harmonic["second_harmonic_ratio"] is not None
    assert harmonic["second_harmonic_ratio"] > 0.04
    assert harmonic["signal_quality"] == "VALID"


def test_t2_negative_control():
    res = validate_t2_static_negative_control()
    assert res["status"] == "PASS"

    static = res["pure_static"]
    assert static["measured_rms_px"] <= 0.08
    assert static["peak_to_median_db"] < 10.0
    assert static["signal_quality"] == "LOW_SIGNAL"

    null_case = res["camera_shake_null"]
    assert null_case["measured_rms_px"] <= 0.08
    assert null_case["peak_to_median_db"] < 10.0
    assert null_case["signal_quality"] == "LOW_SIGNAL"


def test_t3_camera_shake_cancellation():
    res = validate_t3_camera_shake_cancellation()
    assert res["status"] == "PASS"
    assert res["uncorrected_rmse_px"] > 0.40
    assert res["corrected_rmse_px"] < 0.16
    assert res["error_reduction_pct"] >= 60.0
    assert res["shake_suppression_db"] >= 10.0
    assert res["corrected_correlation"] >= 0.90
    assert res["corrected_correlation"] - res["uncorrected_correlation"] >= 0.30


def test_t4_baseline_repeatability():
    res = validate_t4_baseline_repeatability()
    assert res["status"] == "PASS"
    assert res["run_count"] >= 3
    assert res["dominant_frequency_mad_hz"] < 0.01
    assert res["rms_displacement_mad_px"] < 0.01
    assert all(st == "Normal" for st in res["screened_statuses"])
    assert res["false_review_triggers"] == 0


def test_t5_change_detection():
    res = validate_t5_controlled_change_detection()
    assert res["status"] == "PASS"
    assert res["evaluation_status"] == "Review"
    assert res["z_rms_displacement"] >= 3.0
    assert res["z_second_harmonic_ratio"] >= 3.0
    assert res["non_diagnostic_interpretation_verified"] is True


def test_t6_image_quality_stress():
    res = validate_t6_image_quality_stress()
    assert res["status"] == "PASS"
    assert res["t6a_low_texture"]["passed"] is True
    assert res["t6a_low_texture"]["std_px"] < 2.0
    assert len(res["t6a_low_texture"]["errors"]) > 0

    assert res["t6b_severe_blur"]["passed"] is True
    assert res["t6b_severe_blur"]["classified_quality"] == "LOW_SIGNAL"

    assert res["t6c_illumination_flicker"]["passed"] is True
    assert res["t6c_illumination_flicker"]["contaminated"] is True

    assert res["t6d_dropped_frames"]["passed"] is True
    assert res["t6d_dropped_frames"]["status"] == "REJECTED_UNSTABLE"


def test_run_full_validation_matrix():
    matrix = run_full_validation_matrix()
    assert matrix["summary"]["overall_status"] == "PASS"
    assert matrix["summary"]["total_protocols"] == 6
    assert matrix["summary"]["passed_protocols"] == 6
    assert set(matrix["protocols"].keys()) == {"T1", "T2", "T3", "T4", "T5", "T6"}


def test_cli_validate_matrix_stdout_and_json(tmp_path):
    json_out = tmp_path / "cli_val.json"
    cmd = [
        sys.executable,
        "-m",
        "phasesight.cli",
        "validate",
        "--json",
        str(json_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "PhaseSight Proposal Validation Matrix" in proc.stdout
    assert "Overall Verdict: ALL 6 PROPOSAL VALIDATION PROTOCOLS PASSED" in proc.stdout
    assert json_out.is_file()

    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["summary"]["overall_status"] == "PASS"
    assert data["summary"]["passed_protocols"] == 6


def test_cli_validate_single_test(tmp_path):
    json_out = tmp_path / "t3.json"
    cmd = [
        sys.executable,
        "-m",
        "phasesight.cli",
        "validate",
        "--test",
        "T3",
        "--json",
        str(json_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "[PASS] Protocol T3: Camera-Motion Control" in proc.stdout
    assert json_out.is_file()
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["protocol"] == "T3"
    assert data["status"] == "PASS"


def test_cli_validate_legacy_flag(tmp_path):
    json_out = tmp_path / "legacy.json"
    cmd = [
        sys.executable,
        "-m",
        "phasesight.cli",
        "validate",
        "--legacy",
        "--json",
        str(json_out),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert "clean target vibration" in proc.stdout
    assert json_out.is_file()
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    assert len(data) == 4
