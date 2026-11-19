"""Tests for live webcam acquisition, timing stability, and mock streams."""

from pathlib import Path
import threading
import time

import cv2
import numpy as np
import pytest

from phasesight.capture import (
    CaptureResult,
    CaptureStabilityReport,
    MockVideoCapture,
    calculate_timestamp_stability,
    capture_live_clip,
    evaluate_timing_stability,
    grab_preview_frame,
    open_capture_source,
)


def test_stability_report_stable():
    """Uniformly sampled timestamps produce STABLE status and zero dropped frames."""
    t = np.linspace(0, 2.0, 61)  # exactly 30 FPS, dt = 1/30
    report = calculate_timestamp_stability(t, nominal_fps=30.0)

    assert report.status == "STABLE"
    assert report.total_frames == 61
    assert report.measured_fps == pytest.approx(30.0, rel=1e-3)
    assert report.jitter_ratio < 0.01
    assert report.robust_jitter_ratio < 0.01
    assert report.dropped_frames_count == 0
    assert report.large_gap_count == 0
    assert len(report.status_reasons) == 0


def test_stability_report_too_few_frames():
    """Captures with fewer than 32 frames are rejected for spectral analysis."""
    t = np.linspace(0, 0.5, 16)
    report = calculate_timestamp_stability(t, nominal_fps=30.0)

    assert report.status == "REJECTED_UNSTABLE"
    assert any("Too few frames" in r for r in report.status_reasons)


def test_stability_report_non_monotonic():
    """Non-monotonic timestamps trigger immediate rejection."""
    t = np.linspace(0, 2.0, 60)
    t[15] = t[14]  # non-increasing dt = 0
    report = calculate_timestamp_stability(t, nominal_fps=30.0)

    assert report.status == "REJECTED_UNSTABLE"
    assert any("Non-monotonic" in r for r in report.status_reasons)


def test_timing_stability_warning_jitter():
    """Jitter between 5% and 15% triggers WARNING_JITTER status."""
    rng = np.random.default_rng(42)
    dt_base = 1.0 / 30.0
    # Add Gaussian jitter with std = 8% of dt_base
    dt_jittered = dt_base + rng.normal(0, 0.08 * dt_base, 60)
    dt_jittered = np.clip(dt_jittered, dt_base * 0.7, dt_base * 1.3)
    t = np.insert(np.cumsum(dt_jittered), 0, 0.0)

    report = calculate_timestamp_stability(t, nominal_fps=30.0)
    assert report.status == "WARNING_JITTER"
    assert 0.05 <= report.jitter_ratio < 0.15
    assert any("Moderate timestamp jitter" in r for r in report.status_reasons)


def test_timing_stability_rejected_jitter():
    """Jitter >= 15% triggers REJECTED_UNSTABLE status."""
    rng = np.random.default_rng(42)
    dt_base = 1.0 / 30.0
    # Add Gaussian jitter with std = 20% of dt_base
    dt_jittered = dt_base + rng.normal(0, 0.20 * dt_base, 60)
    dt_jittered = np.clip(dt_jittered, dt_base * 0.4, dt_base * 2.0)
    t = np.insert(np.cumsum(dt_jittered), 0, 0.0)

    report = calculate_timestamp_stability(t, nominal_fps=30.0)
    assert report.status == "REJECTED_UNSTABLE"
    assert report.jitter_ratio >= 0.15
    assert any("Severe timestamp jitter" in r for r in report.status_reasons)


def test_timing_stability_single_and_multiple_drops():
    """1-3 dropped frames yield WARNING_JITTER; >3 drops yield REJECTED_UNSTABLE."""
    dt_base = 1.0 / 30.0

    # 1. Two dropped frame gaps (each 2x dt_base = 1 missing frame each, total 2 drops)
    dt_list_2 = [dt_base] * 60
    dt_list_2[10] = dt_base * 2.0  # 1 dropped frame
    dt_list_2[30] = dt_base * 2.0  # 1 dropped frame
    t_2 = np.insert(np.cumsum(dt_list_2), 0, 0.0)
    rep_2 = calculate_timestamp_stability(t_2, nominal_fps=30.0)
    assert rep_2.dropped_frames_count == 2
    assert rep_2.status == "WARNING_JITTER"

    # 2. Five dropped frames (total drops = 5 > 3 tolerated)
    dt_list_5 = [dt_base] * 60
    dt_list_5[10] = dt_base * 2.0
    dt_list_5[20] = dt_base * 2.0
    dt_list_5[30] = dt_base * 2.0
    dt_list_5[40] = dt_base * 2.0
    dt_list_5[50] = dt_base * 2.0
    t_5 = np.insert(np.cumsum(dt_list_5), 0, 0.0)
    rep_5 = calculate_timestamp_stability(t_5, nominal_fps=30.0)
    assert rep_5.dropped_frames_count == 5
    assert rep_5.status == "REJECTED_UNSTABLE"
    assert any("Excessive dropped frames" in r for r in rep_5.status_reasons)


def test_timing_stability_severe_stalls():
    """Inter-frame gap exceeding 2.5x median dt flags large gap and REJECTED_UNSTABLE."""
    dt_base = 1.0 / 30.0
    dt_list = [dt_base] * 60
    dt_list[25] = dt_base * 3.0  # Severe pause / stall
    t = np.insert(np.cumsum(dt_list), 0, 0.0)

    report = calculate_timestamp_stability(t, nominal_fps=30.0)
    assert report.large_gap_count >= 1
    assert report.status == "REJECTED_UNSTABLE"
    assert any("Severe acquisition stalls" in r for r in report.status_reasons)


def test_mock_video_capture_duck_typing():
    """MockVideoCapture behaves as an OpenCV VideoCapture."""
    mock = MockVideoCapture(fps=30.0, num_synthetic_frames=50, width=640, height=360)
    assert mock.isOpened()
    assert mock.get(cv2.CAP_PROP_FRAME_WIDTH) == 640
    assert mock.get(cv2.CAP_PROP_FRAME_HEIGHT) == 360
    assert mock.get(cv2.CAP_PROP_FPS) == 30.0
    assert mock.get(cv2.CAP_PROP_FRAME_COUNT) == 50

    # Read frames
    ok, frame = mock.read()
    assert ok is True
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (360, 640, 3)

    mock.release()
    assert not mock.isOpened()
    ok_after, frame_after = mock.read()
    assert ok_after is False


def test_mock_video_capture_with_drop_simulation():
    """MockVideoCapture skips frames specified in drop_indices."""
    mock = MockVideoCapture(
        fps=30.0, num_synthetic_frames=20, drop_indices={3, 7}
    )
    frames_read = 0
    while True:
        ok, frame = mock.read()
        if not ok:
            break
        frames_read += 1
    mock.release()
    assert frames_read == 18  # 20 - 2 dropped


def test_open_capture_source_and_grab_preview():
    """open_capture_source and grab_preview_frame operate cleanly on mock sources."""
    cap = open_capture_source("mock:0", fps=30.0)
    assert isinstance(cap, MockVideoCapture)
    cap.release()

    preview = grab_preview_frame("mock:0")
    assert isinstance(preview, np.ndarray)
    assert preview.ndim == 3
    assert preview.shape[2] == 3


def test_capture_live_clip_mock_and_save(tmp_path: Path):
    """capture_live_clip acquires frames, computes stability, and writes MP4."""
    out_mp4 = tmp_path / "webcam_test.mp4"
    result = capture_live_clip(
        source="mock:0",
        duration_s=1.5,
        target_fps=30.0,
        output_path=out_mp4,
    )

    assert isinstance(result, CaptureResult)
    assert len(result.frames) >= 35
    assert len(result.timestamps_s) == len(result.frames)
    assert result.video_path == out_mp4
    assert out_mp4.is_file()
    assert out_mp4.stat().st_size > 0
    assert result.stability.status in ("STABLE", "WARNING_JITTER")


def test_capture_live_clip_cancellation():
    """capture_live_clip terminates cleanly when stop_event is set."""
    stop_event = threading.Event()

    def cancel_timer():
        time.sleep(0.15)
        stop_event.set()

    t = threading.Thread(target=cancel_timer)
    t.start()

    t_start = time.perf_counter()
    result = capture_live_clip(
        source="mock:0",
        duration_s=10.0,  # requested 10s
        stop_event=stop_event,
    )
    t_elapsed = time.perf_counter() - t_start
    t.join()

    # Capture should stop well before 10.0 seconds
    assert t_elapsed < 2.0
    assert len(result.frames) > 0


def test_cli_capture_subcommand_mock(tmp_path: Path):
    """Test phasesight capture CLI command with mock:0 source and JSON export."""
    from phasesight.cli import _build_parser, main
    import sys

    out_mp4 = tmp_path / "cli_capture.mp4"
    out_json = tmp_path / "cli_report.json"

    test_args = [
        "phasesight",
        "capture",
        "mock:0",
        "--duration",
        "1.5",
        "--fps",
        "30.0",
        "--out",
        str(out_mp4),
        "--json",
        str(out_json),
    ]

    original_argv = sys.argv
    try:
        sys.argv = test_args
        main()
    finally:
        sys.argv = original_argv

    assert out_mp4.is_file()
    assert out_mp4.stat().st_size > 0
    assert out_json.is_file()
