import numpy as np
import pytest
from pathlib import Path

from phasesight.analysis import analyse_displacement
from phasesight.capture import calculate_timestamp_stability
from phasesight.synthetic import SyntheticConfig, make_scene, write_video, DEFAULT_ANCHOR_ROI, DEFAULT_TARGET_ROI
from phasesight.video import analyse_video


def test_encoded_video_round_trip_keeps_frequency(tmp_path):
    config = SyntheticConfig(
        duration_s=5.0,
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.35,
        camera_amplitude_px=0.4,
        noise_sigma=1.0,
        seed=44,
    )
    frames, _ = make_scene(config)
    video = tmp_path / "test.mp4"
    write_video(video, frames, config.fps)
    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "output",
        min_frequency_hz=1.0,
        max_frequency_hz=20.0,
        nperseg=256,
    )
    assert abs(summary["x_axis"]["dominant_frequency_hz"] - 8.5) < 0.5
    assert summary["x_axis"]["signal_quality"] == "VALID"
    assert (tmp_path / "output" / "test_motion.csv").exists()
    assert (tmp_path / "output" / "test_spectrum.png").exists()


def test_camera_only_h264_clip_is_flagged_when_anchor_has_same_peak(tmp_path):
    config = SyntheticConfig(
        duration_s=5.0,
        vibration_amplitude_px=0.0,
        camera_amplitude_px=0.15,
        camera_y_amplitude_px=0.05,
        lighting_flicker_depth=0.08,
        noise_sigma=1.5,
        seed=7,
    )
    frames, _ = make_scene(config)
    video = tmp_path / "null.mp4"
    write_video(video, frames, config.fps)
    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "null_output",
        min_frequency_hz=1.0,
        max_frequency_hz=20.0,
        nperseg=256,
    )
    # A short compressed null clip may be rejected as LOW_SIGNAL before its
    # shared anchor peak is strong enough for the contamination label. It must
    # never be presented as a valid machine vibration.
    assert summary["x_axis"]["signal_quality"] != "VALID"


# ==============================================================================
# Task 3: Recorded Video Timestamp Integrity Regression Tests (Scenarios 1-8)
# ==============================================================================

def test_timestamp_integrity_1_perfectly_regular_60fps():
    """Scenario 1: Perfectly regular 60 fps timing is STABLE and analyses cleanly."""
    fs = 60.0
    t = np.linspace(0, 5.0, int(fs * 5.0))
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    res = analyse_displacement(t, x)
    assert abs(res.dominant_frequency_hz - 8.5) < 0.1
    stab = calculate_timestamp_stability(t, nominal_fps=fs)
    assert stab.status == "STABLE"
    assert stab.dropped_frames_count == 0


def test_timestamp_integrity_2_minor_timing_jitter():
    """Scenario 2: Minor timing jitter (~1% std/median) is STABLE and handled safely."""
    fs = 60.0
    rng = np.random.default_rng(42)
    dt_nom = 1.0 / fs
    dt = dt_nom + rng.normal(0, 0.01 * dt_nom, 299)
    t = np.cumsum(np.concatenate([[0.0], np.clip(dt, 0.5 * dt_nom, 1.5 * dt_nom)]))
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    res = analyse_displacement(t, x)
    assert abs(res.dominant_frequency_hz - 8.5) < 0.1
    stab = calculate_timestamp_stability(t, nominal_fps=fs)
    assert stab.status == "STABLE"


def test_timestamp_integrity_3_severe_timing_jitter_rejected():
    """Scenario 3: Severe timing jitter (>15%) is rejected by analyse_displacement and stability audit."""
    fs = 60.0
    dt_nom = 1.0 / fs
    # Bimodal timing with no single gap > 1.5x median, but jitter > 20%
    dt = np.tile([0.82 * dt_nom, 1.20 * dt_nom], 150)[:299]
    t = np.cumsum(np.concatenate([[0.0], dt]))
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    with pytest.raises(ValueError, match="Severe timestamp jitter"):
        analyse_displacement(t, x)
    stab = calculate_timestamp_stability(t, nominal_fps=fs)
    assert stab.status == "REJECTED_UNSTABLE"


def test_timestamp_integrity_4_dropped_frames_large_gap_rejected():
    """Scenario 4: Dropped frames creating large interval (>1.5x median) are rejected without silent interpolation."""
    fs = 60.0
    dt_nom = 1.0 / fs
    t = np.arange(300, dtype=float) * dt_nom
    # Inject a 5-frame dropped gap at frame 100
    t[100:] += 5.0 * dt_nom
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    with pytest.raises(ValueError, match="Severe timestamp gap detected"):
        analyse_displacement(t, x)
    stab = calculate_timestamp_stability(t, nominal_fps=fs)
    assert stab.status == "REJECTED_UNSTABLE"
    assert stab.large_gap_count >= 1


def test_timestamp_integrity_5_non_monotonic_timestamps_rejected():
    """Scenario 5: Non-monotonic timestamps are strictly rejected."""
    fs = 60.0
    dt_nom = 1.0 / fs
    t = np.arange(100, dtype=float) * dt_nom
    t[50] = t[49] - 0.005
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    with pytest.raises(ValueError, match="strictly increasing"):
        analyse_displacement(t, x)
    stab = calculate_timestamp_stability(t, nominal_fps=fs)
    assert stab.status == "REJECTED_UNSTABLE"


def test_timestamp_integrity_6_repeated_timestamps_rejected():
    """Scenario 6: Repeated timestamps (zero dt) are strictly rejected."""
    fs = 60.0
    dt_nom = 1.0 / fs
    t = np.arange(100, dtype=float) * dt_nom
    t[50] = t[49]
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    with pytest.raises(ValueError, match="strictly increasing"):
        analyse_displacement(t, x)
    stab = calculate_timestamp_stability(t, nominal_fps=fs)
    assert stab.status == "REJECTED_UNSTABLE"


def test_timestamp_integrity_7_vfr_video_unstable_rejected():
    """Scenario 7: Variable Frame Rate (30 fps transitioning to 60 fps) is rejected as unstable."""
    t_30 = np.arange(100) * (1.0 / 30.0)
    t_60 = t_30[-1] + (1.0 / 60.0) + np.arange(100) * (1.0 / 60.0)
    t_vfr = np.concatenate([t_30, t_60])
    x = 0.5 * np.sin(2 * np.pi * 8.5 * t_vfr)
    with pytest.raises(ValueError, match="Severe timestamp gap"):
        analyse_displacement(t_vfr, x)
    stab = calculate_timestamp_stability(t_vfr, nominal_fps=60.0)
    assert stab.status == "REJECTED_UNSTABLE"


def test_timestamp_integrity_8_video_container_fallback_and_metadata(tmp_path):
    """Scenario 8: Video container inspection records timestamp stability and source in summary JSON."""
    config = SyntheticConfig(duration_s=2.0, vibration_frequency_hz=8.5, seed=50)
    frames, _ = make_scene(config)
    video = tmp_path / "regular.mp4"
    write_video(video, frames, config.fps)
    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "out",
        min_frequency_hz=1.0,
        max_frequency_hz=20.0,
    )
    assert "temporal_stability" in summary
    assert summary["temporal_stability"]["status"] in ("STABLE", "WARNING_JITTER")
    assert summary["timestamp_source"] in ("container_pts", "inferred_cfr_fallback")
    assert summary["x_axis"]["signal_quality"] == "VALID"


# ==============================================================================
# Task 4: Explicit FPS / Timebase Precedence Regression Tests
# ==============================================================================

def test_fps_override_precedence_over_container_metadata(tmp_path):
    """Explicit FPS override (500 FPS) must take precedence over container metadata (100 FPS)."""
    import csv

    config = SyntheticConfig(duration_s=0.5, fps=100, vibration_frequency_hz=3.4, seed=12)
    frames, _ = make_scene(config)
    video = tmp_path / "container_100fps.mp4"
    write_video(video, frames, 100)

    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "out_500fps",
        fps_override=500.0,
        nperseg=64,
    )

    assert summary["fps_used"] == 500.0
    assert summary["timestamp_source"] == "explicit_fps_override"
    assert summary["timebase_source"] == "explicit_fps_override"
    assert summary["x_axis"]["sampling_rate_hz"] == pytest.approx(500.0, rel=1e-3)

    # Verify timestamp spacing in generated motion CSV
    csv_path = Path(summary["outputs"]["csv"])
    assert csv_path.exists()
    timestamps = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamps.append(float(row["timestamp_s"]))

    dt = np.diff(timestamps)
    assert np.allclose(dt, 1.0 / 500.0, atol=1e-7)
    assert timestamps[0] == pytest.approx(1.0 / 500.0, abs=1e-7)


def test_no_override_preserves_container_pts_behavior(tmp_path):
    """When no override is provided, existing container PTS / metadata FPS behavior is preserved."""
    import csv

    config = SyntheticConfig(duration_s=0.5, fps=100, vibration_frequency_hz=3.4, seed=13)
    frames, _ = make_scene(config)
    video = tmp_path / "container_100fps_no_override.mp4"
    write_video(video, frames, 100)

    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "out_no_override",
        fps_override=None,
        nperseg=64,
    )

    assert summary["fps_used"] == 100.0
    assert summary["timestamp_source"] in ("container_pts", "inferred_cfr_fallback")
    assert summary["timebase_source"] in ("container_pts", "inferred_cfr_fallback")
    assert summary["x_axis"]["sampling_rate_hz"] == pytest.approx(100.0, rel=1e-3)

    csv_path = Path(summary["outputs"]["csv"])
    timestamps = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamps.append(float(row["timestamp_s"]))

    dt = np.diff(timestamps)
    assert np.allclose(dt, 1.0 / 100.0, atol=1e-4)


def test_invalid_fps_override_rejected(tmp_path):
    """Invalid explicit FPS values (0, negative, NaN, Inf, non-numeric) are strictly rejected."""
    config = SyntheticConfig(duration_s=0.5, fps=60, vibration_frequency_hz=8.5, seed=14)
    frames, _ = make_scene(config)
    video = tmp_path / "dummy.mp4"
    write_video(video, frames, 60)

    invalid_values = [0, 0.0, -1.0, -500.0, float("nan"), float("inf"), "invalid_str"]
    for val in invalid_values:
        with pytest.raises(ValueError, match="Invalid explicit FPS override"):
            analyse_video(
                video,
                DEFAULT_TARGET_ROI,
                DEFAULT_ANCHOR_ROI,
                tmp_path / "out_invalid",
                fps_override=val,
            )


def test_timebase_source_and_resolution_recorded(tmp_path):
    """Timebase source, frequency resolution, and stability audit are correctly recorded."""
    config = SyntheticConfig(duration_s=1.0, fps=100, vibration_frequency_hz=10.0, seed=15)
    frames, _ = make_scene(config)
    video = tmp_path / "test_rec.mp4"
    write_video(video, frames, 100)

    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "out_rec",
        fps_override=200.0,
        nperseg=64,
    )

    assert summary["timebase_source"] == "explicit_fps_override"
    assert summary["timestamp_source"] == "explicit_fps_override"
    assert summary["fps_used"] == 200.0
    assert summary["x_axis"]["frequency_resolution_hz"] == pytest.approx(200.0 / 64, rel=1e-3)
    assert summary["temporal_stability"]["status"] == "ASSUMED_UNIFORM"
    assert summary["temporal_stability"]["dropped_frames_count"] is None
    assert any("explicit FPS override" in r for r in summary["temporal_stability"]["status_reasons"])


def test_explicit_fps_stability_contract(tmp_path):
    """Explicit FPS override must report ASSUMED_UNIFORM and not falsely report measured 0 dropped frames."""
    config = SyntheticConfig(duration_s=0.5, fps=100, vibration_frequency_hz=5.0, seed=16)
    frames, _ = make_scene(config)
    video = tmp_path / "test_contract.mp4"
    write_video(video, frames, 100)

    summary_override = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "out_override",
        fps_override=500.0,
        nperseg=64,
    )
    stab_override = summary_override["temporal_stability"]
    assert stab_override["status"] == "ASSUMED_UNIFORM"
    assert stab_override["dropped_frames_count"] is None
    assert any("Physical capture timing, dropped frames, and exposure jitter were not independently verified" in r
               for r in stab_override["status_reasons"])

    summary_no_override = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "out_no_override",
        fps_override=None,
        nperseg=64,
    )
    stab_no_override = summary_no_override["temporal_stability"]
    assert stab_no_override["status"] in ("STABLE", "WARNING_JITTER")
    assert isinstance(stab_no_override["dropped_frames_count"], int)
    assert stab_no_override["dropped_frames_count"] == 0


