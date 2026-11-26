from __future__ import annotations

from pathlib import Path
import time
import numpy as np
import pytest

from phasesight.monitoring.replay_adapter import PacedVideoReplayAdapter
from phasesight.monitoring.ring_buffer import BufferSnapshot, RollingMotionBuffer
from phasesight.monitoring.rolling_analysis import (
    RollingAnalysisResult,
    analyze_rolling_window,
    select_adaptive_nperseg,
)
from phasesight.monitoring.session import MonitoringConfig, MonitoringSession
from phasesight.storage import StorageManager
from phasesight.synthetic import DEFAULT_ANCHOR_ROI, DEFAULT_TARGET_ROI, SyntheticConfig, make_scene
from phasesight.tracker import MotionSample, PhaseCorrelationTracker, ROI


def _make_sample(
    t: float,
    rel_dx: float = 0.0,
    rel_dy: float = 0.0,
    anc_dx: float = 0.0,
    anc_dy: float = 0.0,
    valid: bool = True,
    response: float = 0.8,
) -> MotionSample:
    return MotionSample(
        timestamp_s=float(t),
        target_dx_px=float(rel_dx + anc_dx),
        target_dy_px=float(rel_dy + anc_dy),
        anchor_dx_px=float(anc_dx),
        anchor_dy_px=float(anc_dy),
        relative_dx_px=float(rel_dx),
        relative_dy_px=float(rel_dy),
        target_response=float(response),
        anchor_response=float(response),
        valid=bool(valid),
        rejection_reason=None if valid else "rejection_test",
    )


# ---------------------------------------------------------------------------
# 1. Ring Buffer Tests
# ---------------------------------------------------------------------------


def test_ring_buffer_wraparound_ordering_and_clear():
    buf = RollingMotionBuffer(capacity=5)
    assert len(buf) == 0

    # Append 3 samples
    for i in range(1, 4):
        buf.append(_make_sample(t=float(i)))
    assert len(buf) == 3

    snap3 = buf.snapshot()
    assert snap3.count == 3
    assert np.allclose(snap3.timestamps_s, [1.0, 2.0, 3.0])

    # Append 4 more samples (total 7, capacity 5 -> wrap around)
    for i in range(4, 8):
        buf.append(_make_sample(t=float(i)))

    assert len(buf) == 5
    snap5 = buf.snapshot()
    assert snap5.count == 5
    # Must be in chronological order: [3.0, 4.0, 5.0, 6.0, 7.0]
    assert np.allclose(snap5.timestamps_s, [3.0, 4.0, 5.0, 6.0, 7.0])
    assert snap5.total_samples_seen == 7

    # Test max_samples truncation
    snap_subset = buf.snapshot(max_samples=3)
    assert snap_subset.count == 3
    assert np.allclose(snap_subset.timestamps_s, [5.0, 6.0, 7.0])

    # Test clear
    buf.clear()
    assert len(buf) == 0
    snap_empty = buf.snapshot()
    assert snap_empty.count == 0
    assert len(snap_empty.timestamps_s) == 0


# ---------------------------------------------------------------------------
# 2. Rolling Analysis Tests
# ---------------------------------------------------------------------------


def test_analyze_rolling_window_buffering_under_nperseg():
    buf = RollingMotionBuffer(capacity=512)
    fs = 60.0
    for i in range(40):
        t = i / fs
        buf.append(_make_sample(t=t, rel_dx=np.sin(2 * np.pi * 8.5 * t)))

    snapshot = buf.snapshot()
    res = analyze_rolling_window(snapshot, expected_fps=fs)

    assert res.state == "BUFFERING"
    assert res.x_axis.available is False
    assert res.x_axis.dominant_frequency_hz is None
    assert res.frequencies_hz == []
    assert res.x_psd == []


def test_analyze_rolling_window_synthetic_signal_transitions_and_frequency():
    buf = RollingMotionBuffer(capacity=512)
    fs = 60.0
    nperseg = select_adaptive_nperseg(fs)  # 128 for 60 FPS

    # Phase 1: under nperseg (< 128)
    for i in range(100):
        t = i / fs
        buf.append(_make_sample(t=t, rel_dx=0.5 * np.sin(2 * np.pi * 8.5 * t)))

    res1 = analyze_rolling_window(buf.snapshot(), expected_fps=fs)
    assert res1.state == "BUFFERING"
    assert res1.x_axis.available is False

    # Phase 2: between nperseg and 2 * nperseg (150 samples -> WARMING_UP)
    for i in range(100, 150):
        t = i / fs
        buf.append(_make_sample(t=t, rel_dx=0.5 * np.sin(2 * np.pi * 8.5 * t)))

    res2 = analyze_rolling_window(buf.snapshot(), expected_fps=fs)
    assert res2.state == "WARMING_UP"
    assert res2.x_axis.available is True
    assert res2.x_axis.dominant_frequency_hz is not None
    assert abs(res2.x_axis.dominant_frequency_hz - 8.5) < 0.5

    # Phase 3: >= 2 * nperseg (260 samples -> ACTIVE)
    for i in range(150, 260):
        t = i / fs
        buf.append(_make_sample(t=t, rel_dx=0.5 * np.sin(2 * np.pi * 8.5 * t)))

    res3 = analyze_rolling_window(buf.snapshot(), expected_fps=fs)
    assert res3.state == "ACTIVE"
    assert res3.x_axis.available is True
    assert abs(res3.x_axis.dominant_frequency_hz - 8.5) < 0.3


def test_analyze_rolling_window_low_tracking_validity():
    buf = RollingMotionBuffer(capacity=512)
    fs = 60.0
    # 200 samples with 40 invalid (80% validity < 85%)
    for i in range(200):
        t = i / fs
        is_valid = i >= 40
        buf.append(_make_sample(t=t, rel_dx=0.5 * np.sin(2 * np.pi * 8.5 * t), valid=is_valid))

    res = analyze_rolling_window(buf.snapshot(), expected_fps=fs)
    assert res.state == "DEGRADED"
    assert res.x_axis.available is False
    assert any("Low tracking validity" in w for w in res.warnings)


def test_analyze_rolling_window_severe_timestamp_gap():
    buf = RollingMotionBuffer(capacity=512)
    fs = 60.0
    t = 0.0
    for i in range(200):
        if i == 100:
            t += 0.5  # inject 500 ms gap
        else:
            t += 1.0 / fs
        buf.append(_make_sample(t=t, rel_dx=0.5 * np.sin(2 * np.pi * 8.5 * t)))

    res = analyze_rolling_window(buf.snapshot(), expected_fps=fs)
    assert res.state == "DEGRADED"
    assert res.x_axis.available is False
    assert res.should_reset_buffer is True


# ---------------------------------------------------------------------------
# 3. MonitoringSession Tests
# ---------------------------------------------------------------------------


def test_monitoring_session_patch_direct_gap_and_persistence():
    storage = StorageManager(db_path=":memory:")
    asset = storage.create_asset(
        name="Turbine 1",
        target_roi=DEFAULT_TARGET_ROI,
        anchor_roi=DEFAULT_ANCHOR_ROI,
        expected_fps=60.0,
    )

    config = MonitoringConfig(
        session_id="test_monitoring_sess_1",
        source_type="mock_stream",
        target_roi=DEFAULT_TARGET_ROI,
        anchor_roi=DEFAULT_ANCHOR_ROI,
        expected_fps=60.0,
        asset_id=asset.asset_id,
        buffer_capacity=512,
    )
    session = MonitoringSession(config)

    # Generate synthetic frames
    synth_cfg = SyntheticConfig(
        duration_s=6.0,
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.4,
        noise_sigma=0.5,
        seed=100,
    )
    frames, _ = make_scene(synth_cfg)

    # Ingest initial 150 frames via patches
    for i in range(150):
        t = i / 60.0
        frame = frames[i]
        sample = session.ingest_patches(
            DEFAULT_TARGET_ROI.crop(frame),
            DEFAULT_ANCHOR_ROI.crop(frame),
            t,
        )
        assert sample is not None

    telemetry = session.get_rolling_telemetry(force=True)
    assert telemetry is not None
    assert telemetry["state"] in ("WARMING_UP", "ACTIVE")
    assert telemetry["x_axis"]["dominant_frequency_hz"] is not None
    assert abs(telemetry["x_axis"]["dominant_frequency_hz"] - 8.5) < 0.5

    # Test recalibration request
    session.request_recalibration()
    # Next frame triggers recalibration and resets buffer
    frame150 = frames[150]
    session.ingest_patches(
        DEFAULT_TARGET_ROI.crop(frame150),
        DEFAULT_ANCHOR_ROI.crop(frame150),
        150 / 60.0,
    )
    assert len(session.rolling_buffer) == 1
    assert session.state == "BUFFERING"

    # Ingest 20 more frames
    for i in range(151, 170):
        session.ingest_patches(
            DEFAULT_TARGET_ROI.crop(frames[i]),
            DEFAULT_ANCHOR_ROI.crop(frames[i]),
            i / 60.0,
        )

    # Inject 500 ms timestamp gap
    gap_time = (170 / 60.0) + 0.500
    session.ingest_patches(
        DEFAULT_TARGET_ROI.crop(frames[170]),
        DEFAULT_ANCHOR_ROI.crop(frames[170]),
        gap_time,
    )
    # Severe gap clears rolling buffer
    assert len(session.rolling_buffer) == 1
    assert any("Severe timestamp gap" in w for w in session.warnings)

    # Drain trace batch
    traces = session.drain_trace_batch()
    assert len(traces) > 0
    assert "timestamp_s" in traces[0]

    # Ingest remaining frames to populate archive buffer
    t_curr = gap_time
    for i in range(171, len(frames)):
        t_curr += 1.0 / 60.0
        session.ingest_patches(
            DEFAULT_TARGET_ROI.crop(frames[i]),
            DEFAULT_ANCHOR_ROI.crop(frames[i]),
            t_curr,
        )

    # Stop and persist to storage
    report = session.stop_and_persist(storage)
    assert report["session_mode"] == "continuous_monitoring"
    assert report["run_id"] is not None

    # Verify run record in storage
    run_rec = storage.get_inspection_run(report["run_id"])
    assert run_rec is not None
    assert run_rec.asset_id == asset.asset_id

    # Verify NPZ arrays persisted
    arrays = storage.load_run_arrays(run_rec.npz_rel_path)
    assert len(arrays.timestamps_s) > 0
    assert len(arrays.relative_dx_px) == len(arrays.timestamps_s)

    storage.close()


# ---------------------------------------------------------------------------
# 4. PacedVideoReplayAdapter Tests
# ---------------------------------------------------------------------------


def test_paced_video_replay_adapter_baseline_mp4():
    video_path = Path("data/portable/baseline.mp4")
    if not video_path.is_file():
        pytest.skip("baseline.mp4 not found")

    target_roi = ROI(x=360, y=110, width=160, height=160)
    anchor_roi = ROI(x=60, y=100, width=160, height=160)

    config = MonitoringConfig(
        session_id="baseline_replay_test",
        source_type="video_replay",
        target_roi=target_roi,
        anchor_roi=anchor_roi,
        expected_fps=60.0,
        buffer_capacity=512,
    )
    session = MonitoringSession(config)

    # Run replay adapter fast (playback_rate=20.0 for speed)
    adapter = PacedVideoReplayAdapter(
        video_path,
        session,
        playback_rate=20.0,
    )

    adapter.start()
    assert adapter.is_running

    # Wait until buffer has filled enough to reach ACTIVE or EOF reached
    timeout = 15.0
    start_t = time.perf_counter()
    reached_active = False

    while (time.perf_counter() - start_t) < timeout:
        telem = session.get_rolling_telemetry(force=True)
        if telem and telem["state"] == "ACTIVE":
            reached_active = True
            break
        if adapter.eof_reached:
            break
        time.sleep(0.05)

    adapter.stop()
    assert not adapter.is_running

    # Check JPEG preview
    jpeg = adapter.get_latest_frame_jpeg(quality=70)
    assert jpeg is not None
    assert len(jpeg) > 100

    assert reached_active is True
    telem = session.get_rolling_telemetry(force=True)
    assert telem is not None
    assert telem["state"] == "ACTIVE"
    dom_freq = telem["x_axis"]["dominant_frequency_hz"]
    assert dom_freq is not None
    assert abs(dom_freq - 8.5) < 0.5


def test_paced_video_replay_adapter_rotor_dataset():
    rotor_path = Path("data/rotor_dataset/Raw videos/1000rpm-Unb1.avi")
    if not rotor_path.is_file():
        pytest.skip("1000rpm-Unb1.avi not found")

    target_roi = ROI(x=850, y=460, width=64, height=64)
    anchor_roi = ROI(x=600, y=560, width=64, height=64)

    config = MonitoringConfig(
        session_id="rotor_replay_test",
        source_type="video_replay",
        target_roi=target_roi,
        anchor_roi=anchor_roi,
        expected_fps=500.0,
        timebase_source="explicit_fps_override",
        buffer_capacity=512,
        nperseg_override=256,
    )
    session = MonitoringSession(config)

    adapter = PacedVideoReplayAdapter(
        rotor_path,
        session,
        fps_override=500.0,
        playback_rate=10.0,
        loop=True,
    )

    adapter.start()
    timeout = 15.0
    start_t = time.perf_counter()
    reached_active = False

    while (time.perf_counter() - start_t) < timeout:
        telem = session.get_rolling_telemetry(force=True)
        if telem and telem["state"] == "ACTIVE":
            reached_active = True
            break
        if adapter.eof_reached:
            break
        time.sleep(0.05)

    adapter.stop()

    assert reached_active is True
    telem = session.get_rolling_telemetry(force=True)
    assert telem is not None
    assert telem["state"] == "ACTIVE"
    assert telem["timing_status"] == "ASSUMED_UNIFORM"

    dom_freq = telem["x_axis"]["dominant_frequency_hz"]
    assert dom_freq is not None
    # 1000 RPM is 16.67 Hz -> verify frequency near 16.5 Hz (±1.0 Hz)
    assert abs(dom_freq - 16.5) < 1.0


# ---------------------------------------------------------------------------
# 5. Live Stream Timing Resilience & Drop Gating Tests
# ---------------------------------------------------------------------------


def test_rolling_stream_isolated_single_frame_drops_resilience():
    """Verify that a 30 FPS stream with isolated single-frame drops (2.0x dt, ~1% drops)
    stays ACTIVE with WARNING_JITTER and accurately recovers a 5.0 Hz injected tone within ±0.5 Hz.
    """
    buf = RollingMotionBuffer(capacity=512)
    fps = 30.0
    dt_nom = 1.0 / fps

    t_cur = 0.0
    for i in range(192):
        if i == 50 or i == 120:
            t_cur += 2.0 * dt_nom  # Isolated single-frame drop
        else:
            t_cur += dt_nom
        sig = 0.5 * np.sin(2.0 * np.pi * 5.0 * t_cur)
        buf.append(_make_sample(t=t_cur, rel_dx=sig, response=0.9))

    snap = buf.snapshot()
    res = analyze_rolling_window(snap, expected_fps=fps)

    assert res.state == "ACTIVE"
    assert res.timing_status == "WARNING_JITTER"
    assert res.dropped_frames == 2
    assert res.should_reset_buffer is False
    assert res.x_axis.available is True
    assert res.x_axis.dominant_frequency_hz is not None
    assert abs(res.x_axis.dominant_frequency_hz - 5.0) < 0.5


def test_rolling_stream_burst_stall_triggers_hard_degraded():
    """Verify that a burst stall (> 2.5x dt) or excessive dropped frames (>8-10%)
    strictly triggers DEGRADED / REJECTED_UNSTABLE with available=False.
    """
    fps = 30.0
    dt_nom = 1.0 / fps

    # Case 1: Burst stall (> 2.5x dt)
    buf_stall = RollingMotionBuffer(capacity=512)
    t_cur = 0.0
    for i in range(192):
        if i == 50:
            t_cur += 3.5 * dt_nom  # Burst stall (large_gap_count > 0)
        else:
            t_cur += dt_nom
        buf_stall.append(_make_sample(t=t_cur, rel_dx=0.5, response=0.9))

    snap_stall = buf_stall.snapshot()
    res_stall = analyze_rolling_window(snap_stall, expected_fps=fps)

    assert res_stall.state == "DEGRADED"
    assert res_stall.timing_status == "REJECTED_UNSTABLE"
    assert res_stall.x_axis.available is False
    assert res_stall.should_reset_buffer is True

    # Case 2: Excessive drops (> 10% dropped frames)
    buf_drops = RollingMotionBuffer(capacity=512)
    t_cur = 0.0
    for i in range(192):
        if i % 8 == 0 and i > 0 and i < 170:  # 21 single-frame drops (~11% drops)
            t_cur += 2.0 * dt_nom
        else:
            t_cur += dt_nom
        buf_drops.append(_make_sample(t=t_cur, rel_dx=0.5, response=0.9))

    snap_drops = buf_drops.snapshot()
    res_drops = analyze_rolling_window(snap_drops, expected_fps=fps)

    assert res_drops.state == "DEGRADED"
    assert res_drops.timing_status == "REJECTED_UNSTABLE"
    assert res_drops.x_axis.available is False


def test_browser_media_time_tolerates_151x_interval_without_degraded():
    """Verify non-override streams tolerate a minor 1.51x frame interval without triggering Welch DEGRADED."""
    buf = RollingMotionBuffer(capacity=512)
    fps = 30.0
    dt_nom = 1.0 / fps

    t_cur = 0.0
    for i in range(192):
        if i == 80:
            t_cur += 1.51 * dt_nom
        else:
            t_cur += dt_nom
        sig = 0.5 * np.sin(2.0 * np.pi * 5.0 * t_cur)
        buf.append(_make_sample(t=t_cur, rel_dx=sig, response=0.9))

    snap = buf.snapshot()
    res = analyze_rolling_window(
        snap, expected_fps=fps, timebase_source="browser_media_time"
    )

    assert res.state == "ACTIVE"
    assert res.timebase_source == "browser_media_time"
    assert res.timing_status in ("STABLE", "WARNING_JITTER")
    assert res.x_axis.available is True
    assert res.x_axis.dominant_frequency_hz is not None
    assert abs(res.x_axis.dominant_frequency_hz - 5.0) < 0.5


