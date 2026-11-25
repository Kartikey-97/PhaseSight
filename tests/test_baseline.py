import copy
import json
from pathlib import Path
import pytest

from phasesight.baseline import (
    AxisBaseline,
    BaselineEvaluation,
    BaselineRecord,
    DEFAULT_FEATURE_EPSILONS,
    FeatureStats,
    build_baseline,
    compute_robust_stats,
    deserialize_baseline,
    evaluate_run_against_baseline,
    serialize_baseline,
)


def _make_sample_run(
    freq: float = 8.50,
    rms: float = 0.232,
    db: float = 27.0,
    harm: float | None = 0.003,
    signal_quality: str = "VALID",
    tx: int = 360,
    ty: int = 110,
    fps: float = 60.0,
) -> dict:
    return {
        "video": "test_video.mp4",
        "fps_used": fps,
        "frames_analysed": 600,
        "target_roi_xywh": {"x": tx, "y": ty, "width": 160, "height": 160},
        "anchor_roi_xywh": {"x": 60, "y": 100, "width": 160, "height": 160},
        "x_axis": {
            "dominant_frequency_hz": freq,
            "rms_displacement_px": rms,
            "peak_to_median_db": db,
            "second_harmonic_ratio": harm,
            "signal_quality": signal_quality,
        },
        "y_axis": {
            "dominant_frequency_hz": 19.8,
            "rms_displacement_px": 0.065,
            "peak_to_median_db": 14.5,
            "second_harmonic_ratio": None,
            "signal_quality": "VALID",
        },
    }


def test_build_baseline_rejects_fewer_than_3_runs():
    run = _make_sample_run()
    with pytest.raises(ValueError, match="at least 3 runs"):
        build_baseline([])
    with pytest.raises(ValueError, match="at least 3 runs"):
        build_baseline([run])
    with pytest.raises(ValueError, match="at least 3 runs"):
        build_baseline([run, run])


def test_build_baseline_valid_3_runs():
    r1 = _make_sample_run(freq=8.49, rms=0.230)
    r2 = _make_sample_run(freq=8.50, rms=0.232)
    r3 = _make_sample_run(freq=8.52, rms=0.235)
    base = build_baseline([r1, r2, r3], asset_id="pump_01")
    assert base.run_count == 3
    assert base.asset_id == "pump_01"
    assert base.x_axis.dominant_frequency_hz.median == pytest.approx(8.50, abs=1e-3)
    assert base.x_axis.rms_displacement_px.median == pytest.approx(0.232, abs=1e-3)


def test_zero_mad_numerical_stability():
    r = _make_sample_run(freq=8.500, rms=0.2320)
    base = build_baseline([r, r, r])
    # Ingesting with MAD=0 and 0.001 Hz jitter produces z ~ 0.05
    current = _make_sample_run(freq=8.501, rms=0.2320)
    res = evaluate_run_against_baseline(current, base, axis="x")
    assert res.status == "Normal"
    freq_dev = res.deviations["x_dominant_frequency_hz"]
    assert abs(freq_dev.z_robust) < 0.2


def test_outlier_resilience_breakdown_point():
    r1 = _make_sample_run(freq=8.50)
    r2 = _make_sample_run(freq=8.51)
    r3 = _make_sample_run(freq=15.00)  # Extreme outlier
    base = build_baseline([r1, r2, r3])
    # Median should be 8.51, unaffected by the 15.00 outlier
    assert base.x_axis.dominant_frequency_hz.median == pytest.approx(8.51, abs=1e-3)
    assert base.x_axis.dominant_frequency_hz.mad == pytest.approx(0.01, abs=1e-3)


def test_confidence_gate_low_signal():
    r = _make_sample_run()
    base = build_baseline([r, r, r])
    bad_run = _make_sample_run(signal_quality="LOW_SIGNAL")
    res = evaluate_run_against_baseline(bad_run, base, axis="x")
    assert res.status == "Low confidence"
    assert res.confidence_passed is False
    assert any("LOW_SIGNAL" in r for r in res.reasons)


def test_confidence_gate_anchor_contaminated():
    r = _make_sample_run()
    base = build_baseline([r, r, r])
    bad_run = _make_sample_run(signal_quality="CONTAMINATED")
    res = evaluate_run_against_baseline(bad_run, base, axis="x")
    assert res.status == "Low confidence"
    assert res.confidence_passed is False
    assert any("CONTAMINATED" in r for r in res.reasons)


def test_confidence_gate_baseline_contaminated():
    bad_r = _make_sample_run(signal_quality="CONTAMINATED")
    bad_r["y_axis"]["signal_quality"] = "CONTAMINATED"
    with pytest.raises(ValueError, match="consistently valid signal quality"):
        build_baseline([bad_r, bad_r, bad_r])


@pytest.mark.parametrize(
    "qx,qy,should_pass,failing_axis",
    [
        ("VALID", "VALID", True, None),
        ("VALID", "CONTAMINATED", False, "Y"),
        ("CONTAMINATED", "VALID", False, "X"),
        ("CONTAMINATED", "CONTAMINATED", False, "X"),
        ("VALID", "LOW_SIGNAL", False, "Y"),
        ("LOW_SIGNAL", "VALID", False, "X"),
        ("VALID", "UNKNOWN", False, "Y"),
    ],
)
def test_baseline_admission_matrix(qx, qy, should_pass, failing_axis):
    """Full-vector baseline requires BOTH X and Y axes to be VALID across all runs."""
    r1 = _make_sample_run()
    r2 = _make_sample_run()
    r3 = _make_sample_run()
    for r in (r1, r2, r3):
        r["x_axis"]["signal_quality"] = qx
        r["y_axis"]["signal_quality"] = qy

    if should_pass:
        base = build_baseline([r1, r2, r3], require_valid_axes=["x", "y"])
        assert base.run_count == 3
        assert base.x_axis is not None
        assert base.y_axis is not None
    else:
        expected_status = qx if failing_axis == "X" else qy
        with pytest.raises(ValueError, match=f"{failing_axis}-axis signal quality is '{expected_status}', expected 'VALID'"):
            build_baseline([r1, r2, r3], require_valid_axes=["x", "y"])


def test_review_gate_rms_trigger():
    r = _make_sample_run(rms=0.232)
    base = build_baseline([r, r, r])
    changed = _make_sample_run(rms=0.345)
    res = evaluate_run_against_baseline(changed, base, axis="x")
    assert res.status == "Review"
    assert any("RMS Displacement" in t for t in res.trigger_features)


def test_review_gate_frequency_shift():
    r = _make_sample_run(freq=8.50)
    base = build_baseline([r, r, r])
    changed = _make_sample_run(freq=8.80)
    res = evaluate_run_against_baseline(changed, base, axis="x")
    assert res.status == "Review"
    assert any("Dominant Frequency" in t for t in res.trigger_features)


def test_review_gate_harmonic_emergence():
    r = _make_sample_run(harm=0.003)
    base = build_baseline([r, r, r])
    changed = _make_sample_run(harm=0.051)
    res = evaluate_run_against_baseline(changed, base, axis="x")
    assert res.status == "Review"
    assert any("2x Harmonic Ratio" in t for t in res.trigger_features)


def test_normal_run_within_bounds():
    r = _make_sample_run(freq=8.50, rms=0.232)
    base = build_baseline([r, r, r])
    current = _make_sample_run(freq=8.502, rms=0.233)
    res = evaluate_run_against_baseline(current, base, axis="x")
    assert res.status == "Normal"
    assert res.trigger_features == []


def test_missing_harmonic_both_none():
    r = _make_sample_run(harm=None)
    base = build_baseline([r, r, r])
    current = _make_sample_run(harm=None)
    res = evaluate_run_against_baseline(current, base, axis="x")
    assert "x_second_harmonic_ratio" not in res.deviations
    assert res.status == "Normal"


def test_missing_harmonic_emergence():
    r = _make_sample_run(harm=None)
    base = build_baseline([r, r, r])
    current = _make_sample_run(harm=0.050)
    res = evaluate_run_against_baseline(current, base, axis="x")
    assert res.status == "Review"
    assert "x_second_harmonic_ratio" in res.deviations
    assert res.deviations["x_second_harmonic_ratio"].is_trigger is True


def test_json_roundtrip_serialization(tmp_path):
    r = _make_sample_run()
    base = build_baseline([r, r, r], asset_id="asset_123", notes="Factory line 2")
    json_path = tmp_path / "baseline.json"
    serialize_baseline(base, json_path)
    loaded = deserialize_baseline(json_path)
    assert loaded.baseline_id == base.baseline_id
    assert loaded.asset_id == "asset_123"
    assert loaded.notes == "Factory line 2"
    assert loaded.x_axis.dominant_frequency_hz.median == base.x_axis.dominant_frequency_hz.median


def test_roi_mismatch_rejection():
    r1 = _make_sample_run(tx=360)
    r2 = _make_sample_run(tx=360)
    r3 = _make_sample_run(tx=400)  # Divergent target ROI
    with pytest.raises(ValueError, match="diverges from reference"):
        build_baseline([r1, r2, r3])


def test_real_portable_data_evaluation():
    base_file = Path("data/portable/out_baseline/baseline_summary.json")
    changed_file = Path("data/portable/out_changed/changed_summary.json")
    null_file = Path("data/portable/out_camera_only/camera_only_summary.json")

    base_run = json.loads(base_file.read_text(encoding="utf-8"))
    changed_run = json.loads(changed_file.read_text(encoding="utf-8"))
    null_run = json.loads(null_file.read_text(encoding="utf-8"))

    base = build_baseline([base_run, base_run, base_run], asset_id="portable_motor")
    eval_base = evaluate_run_against_baseline(base_run, base, axis="x")
    assert eval_base.status == "Normal"

    eval_changed = evaluate_run_against_baseline(changed_run, base, axis="x")
    assert eval_changed.status == "Review"
    assert any("RMS" in t for t in eval_changed.trigger_features)

    eval_null = evaluate_run_against_baseline(null_run, base, axis="x")
    assert eval_null.status == "Low confidence"
    assert eval_null.confidence_passed is False
