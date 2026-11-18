import numpy as np
import pytest

from phasesight.analysis import (
    analyse_displacement,
    classify_signal_quality,
    compare_inspection_summaries,
    compare_to_baseline,
)


def _signal_result(amplitude: float, frequency: float = 8.5, seed: int = 11):
    fs = 60.0
    t = np.arange(int(fs * 10)) / fs
    rng = np.random.default_rng(seed)
    x = amplitude * np.sin(2 * np.pi * frequency * t) + rng.normal(0, 0.005, len(t))
    return analyse_displacement(t, x, min_frequency_hz=1, max_frequency_hz=20, nperseg=256)


def test_welch_finds_known_frequency():
    result = _signal_result(0.35)
    assert abs(result.dominant_frequency_hz - 8.5) < 0.15
    assert classify_signal_quality(result) == "VALID"


def test_low_signal_is_not_misrepresented_as_a_valid_peak():
    fs = 60.0
    t = np.arange(600) / fs
    x = np.random.default_rng(5).normal(0, 0.01, len(t))
    result = analyse_displacement(t, x, min_frequency_hz=1, max_frequency_hz=20)
    assert classify_signal_quality(result) == "LOW_SIGNAL"


def test_harmonic_ratio_increases_when_second_harmonic_is_present():
    fs = 60.0
    t = np.arange(600) / fs
    fundamental = 0.25 * np.sin(2 * np.pi * 8.5 * t)
    clean = analyse_displacement(t, fundamental, min_frequency_hz=1, max_frequency_hz=20)
    with_harmonic = fundamental + 0.08 * np.sin(2 * np.pi * 17.0 * t + 0.25)
    changed = analyse_displacement(t, with_harmonic, min_frequency_hz=1, max_frequency_hz=20)
    assert changed.second_harmonic_ratio is not None
    assert changed.second_harmonic_ratio > clean.second_harmonic_ratio * 10


def test_compare_to_baseline_flags_large_rms_change():
    baseline = _signal_result(0.20, seed=1)
    current = _signal_result(0.40, seed=1)
    comparison = compare_to_baseline(baseline, current)
    assert comparison.status == "ALERT_CHANGE"
    assert comparison.rms_change_percent > 50


def test_bad_timestamps_are_rejected():
    t = np.arange(100) / 60.0
    t[50] = t[49]
    with pytest.raises(ValueError, match="strictly increasing"):
        analyse_displacement(t, np.sin(2 * np.pi * 8 * t))


def test_frequency_above_nyquist_aliases_into_band():
    fs = 60.0
    t = np.arange(600) / fs
    # A 35 Hz sinusoid sampled at 60 FPS aliases to 25 Hz.
    x = np.sin(2 * np.pi * 35.0 * t)
    result = analyse_displacement(t, x, min_frequency_hz=1, max_frequency_hz=28)
    assert abs(result.dominant_frequency_hz - 25.0) < 0.2


def test_matching_peak_in_static_anchor_is_marked_as_contamination():
    from phasesight.analysis import is_anchor_contaminated

    fs = 60.0
    t = np.arange(600) / fs
    target = np.sin(2 * np.pi * 8.5 * t) + 0.25 * np.sin(2 * np.pi * 20.0 * t)
    anchor = 0.5 * np.sin(2 * np.pi * 20.0 * t)
    relative = analyse_displacement(t, target, min_frequency_hz=1, max_frequency_hz=24)
    anchor_result = analyse_displacement(t, anchor, min_frequency_hz=1, max_frequency_hz=24)
    # The relative peak is 8.5 Hz, so a 20 Hz peak in the anchor does not contaminate it.
    assert not is_anchor_contaminated(relative, anchor_result)

    relative_20 = analyse_displacement(t, np.sin(2 * np.pi * 20.0 * t), min_frequency_hz=1, max_frequency_hz=24)
    assert is_anchor_contaminated(relative_20, anchor_result)


def test_compare_inspection_summaries_detects_changes():
    baseline = {
        "x_axis": {
            "dominant_frequency_hz": 8.50,
            "rms_displacement_px": 0.20,
            "signal_quality": "VALID",
            "frequency_resolution_hz": 0.23,
        }
    }
    current_warn = {
        "x_axis": {
            "dominant_frequency_hz": 8.51,
            "rms_displacement_px": 0.27,  # +35% change -> WARNING_CHANGE
            "signal_quality": "VALID",
            "frequency_resolution_hz": 0.23,
        }
    }
    report_warn = compare_inspection_summaries(baseline, current_warn, axis="x")
    assert report_warn["status"] == "WARNING_CHANGE"
    assert report_warn["rms_change_percent"] == pytest.approx(35.0)

    current_alert = {
        "x_axis": {
            "dominant_frequency_hz": 8.51,
            "rms_displacement_px": 0.35,  # +75% change -> ALERT_CHANGE
            "signal_quality": "VALID",
            "frequency_resolution_hz": 0.23,
        }
    }
    report_alert = compare_inspection_summaries(baseline, current_alert, axis="x")
    assert report_alert["status"] == "ALERT_CHANGE"


def test_compare_inspection_summaries_rejects_non_valid_signals():
    baseline = {
        "x_axis": {
            "dominant_frequency_hz": 8.50,
            "rms_displacement_px": 0.20,
            "signal_quality": "VALID",
            "frequency_resolution_hz": 0.23,
        }
    }
    current_bad = {
        "x_axis": {
            "dominant_frequency_hz": 20.0,
            "rms_displacement_px": 0.08,
            "signal_quality": "CONTAMINATED",
            "frequency_resolution_hz": 0.23,
        }
    }
    report = compare_inspection_summaries(baseline, current_bad, axis="x")
    assert report["status"] == "INSUFFICIENT_SIGNAL"
    assert report["rms_change_percent"] is None


def test_compare_inspection_summaries_enforces_noise_floor():
    baseline = {
        "x_axis": {
            "dominant_frequency_hz": 8.50,
            "rms_displacement_px": 0.20,
            "signal_quality": "VALID",
            "frequency_resolution_hz": 0.23,
        }
    }
    current = {
        "x_axis": {
            "dominant_frequency_hz": 8.51,
            "rms_displacement_px": 0.22,
            "signal_quality": "VALID",
            "frequency_resolution_hz": 0.23,
        }
    }
    # Noise floor RMS of 0.10 with multiple 3 requires RMS >= 0.30
    noise_floor = {
        "x_axis": {
            "dominant_frequency_hz": 12.0,
            "rms_displacement_px": 0.10,
        }
    }
    report = compare_inspection_summaries(
        baseline, current, axis="x", noise_floor_summary=noise_floor, noise_floor_multiple=3.0
    )
    assert report["status"] == "INSUFFICIENT_SIGNAL"
