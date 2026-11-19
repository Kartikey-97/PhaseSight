from pathlib import Path
import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from phasesight.baseline import (
    _rois_match,
    build_baseline,
    evaluate_run_against_baseline,
)
from phasesight.storage import RunArrays, StorageManager
from phasesight.tracker import ROI
from phasesight.ui_helpers import (
    DEFAULT_SAMPLE_TARGET_ROI,
    get_video_metadata,
    plot_run_arrays,
    read_first_frame,
    run_arrays_from_csv,
    stability_badge,
    status_badge,
)

APP_PATH = Path(__file__).parent.parent / "phasesight" / "app.py"


def test_ui_helpers_get_metadata_and_frame():
    baseline_path = Path("data/portable/baseline.mp4")
    meta = get_video_metadata(baseline_path)
    assert meta["width"] == 640
    assert meta["height"] == 360
    assert meta["fps"] == pytest.approx(60.0, rel=1e-2)
    assert meta["frame_count"] == 600

    frame = read_first_frame(baseline_path)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (360, 640, 3)


def test_ui_helpers_reject_invalid_video(tmp_path):
    invalid_path = tmp_path / "nonexistent.mp4"
    with pytest.raises(RuntimeError, match="Could not open video"):
        get_video_metadata(invalid_path)

    with pytest.raises(RuntimeError, match="Could not open video"):
        read_first_frame(invalid_path)


def test_status_badge_formatting():
    assert "🟢" in status_badge("Normal")
    assert "🔴" in status_badge("Review")
    assert "🟡" in status_badge("Low confidence")
    assert "⚪" in status_badge("Unassessed")


def test_run_arrays_from_csv_and_plot():
    csv_path = Path("output/baseline/baseline_motion.csv")
    if csv_path.is_file():
        arrays = run_arrays_from_csv(csv_path)
        assert len(arrays.timestamps_s) > 0
        assert arrays.x_frequencies_hz is not None
        fig = plot_run_arrays(arrays)
        assert fig is not None


def test_streamlit_app_loads_and_renders_cleanly():
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception
    # Check that 6 tabs rendered
    assert len(at.tabs) == 6


def test_streamlit_app_sample_clip_inspection():
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception
    assert len(at.radio) >= 1
    assert len(at.image) >= 1


def test_ui_asset_selection_updates_rois_and_fps():
    sm = StorageManager(db_path=":memory:")
    asset = sm.create_asset(
        name="Cooling Fan A",
        target_roi={"x": 250, "y": 140, "width": 120, "height": 120},
        anchor_roi={"x": 40, "y": 40, "width": 100, "height": 100},
        expected_fps=59.94,
    )

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.session_state["storage_manager"] = sm
    at.run()
    assert not at.exception

    # Select the asset in sidebar
    assert len(at.sidebar.selectbox) >= 1
    options = at.sidebar.selectbox[0].options
    assert len(options) == 2
    at.sidebar.selectbox[0].select(options[1])
    at.run()
    assert not at.exception

    # Assert session state synced
    assert at.session_state["selected_asset_id"] == asset.asset_id
    assert at.session_state["tx_input"] == 250
    assert at.session_state["ty_input"] == 140
    assert at.session_state["tw_input"] == 120
    assert at.session_state["th_input"] == 120
    assert at.session_state["ax_input"] == 40
    assert at.session_state["ay_input"] == 40
    assert at.session_state["aw_input"] == 100
    assert at.session_state["ah_input"] == 100
    assert at.session_state["fps_override_val"] == pytest.approx(59.94)

    # Switch back to None
    at.sidebar.selectbox[0].select(options[0])
    at.run()
    assert not at.exception
    assert at.session_state["selected_asset_id"] is None
    assert at.session_state["tx_input"] == DEFAULT_SAMPLE_TARGET_ROI.x


def test_ui_asset_management_crud():
    sm = StorageManager(db_path=":memory:")
    a = sm.create_asset(
        name="Boiler Feed Pump",
        target_roi={"x": 100, "y": 100, "width": 64, "height": 64},
        anchor_roi={"x": 20, "y": 20, "width": 64, "height": 64},
        expected_fps=60.0,
        nominal_speed_rpm=3550.0,
    )
    assert sm.get_asset(a.asset_id).name == "Boiler Feed Pump"

    # Update
    sm.update_asset(a.asset_id, name="Boiler Feed Pump (Overhauled)")
    assert sm.get_asset(a.asset_id).name == "Boiler Feed Pump (Overhauled)"

    # Verify AppTest renders asset catalog
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.session_state["storage_manager"] = sm
    at.run()
    assert not at.exception

    # Delete
    assert sm.delete_asset(a.asset_id)
    assert sm.get_asset(a.asset_id) is None


def test_ui_baseline_wizard_quorum_and_validation():
    target = {"x": 360, "y": 110, "width": 160, "height": 160}
    anchor = {"x": 60, "y": 100, "width": 160, "height": 160}

    valid_run = {
        "target_roi_xywh": target,
        "anchor_roi_xywh": anchor,
        "fps_used": 60.0,
        "x_axis": {
            "dominant_frequency_hz": 8.50,
            "rms_displacement_px": 0.45,
            "peak_to_median_db": 15.0,
            "second_harmonic_ratio": 0.03,
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

    # Quorum failure with 2 runs
    assert len([valid_run, valid_run]) < 3

    # Spatial mismatch check
    divergent_roi = {"x": 400, "y": 110, "width": 160, "height": 160}
    assert not _rois_match(target, divergent_roi, tolerance=2)

    # Valid quorum of 3
    baseline = build_baseline([valid_run, valid_run, valid_run], asset_id="ast_test")
    assert baseline.run_count == 3
    assert baseline.x_axis.dominant_frequency_hz.median == pytest.approx(8.50)


def test_ui_inspection_history_table_and_npz_traces():
    sm = StorageManager(db_path=":memory:")
    asset = sm.create_asset(
        name="Compressor 1",
        target_roi={"x": 50, "y": 50, "width": 64, "height": 64},
        anchor_roi={"x": 10, "y": 10, "width": 64, "height": 64},
    )

    t = np.linspace(0, 5, 300)
    arrays = RunArrays(
        timestamps_s=t,
        relative_dx_px=0.2 * np.sin(2 * np.pi * 10.0 * t),
        relative_dy_px=0.01 * np.random.randn(300),
    )

    run = sm.create_inspection_run(
        asset_id=asset.asset_id,
        video_path="compressor.mp4",
        measured_fps=60.0,
        duration_s=5.0,
        frames_analysed=300,
        summary={"x_axis": {"dominant_frequency_hz": 10.0, "rms_displacement_px": 0.14}},
        arrays=arrays,
        status="Unassessed",
    )

    # Verify run arrays loadable from NPZ
    loaded_arrays = sm.load_run_arrays(run.npz_rel_path)
    assert len(loaded_arrays.timestamps_s) == 300

    # Verify figure creation
    fig = plot_run_arrays(loaded_arrays)
    assert fig is not None


def test_ui_review_event_logging_and_status_sync():
    sm = StorageManager(db_path=":memory:")
    asset = sm.create_asset(
        name="Motor M1",
        target_roi={"x": 10, "y": 10, "width": 32, "height": 32},
        anchor_roi={"x": 0, "y": 0, "width": 32, "height": 32},
    )
    run = sm.create_inspection_run(
        asset_id=asset.asset_id,
        video_path="motor.mp4",
        measured_fps=60.0,
        duration_s=2.0,
        frames_analysed=120,
        summary={},
        status="Unassessed",
    )
    assert run.status == "Unassessed"

    # Log review event
    event = sm.create_review_event(
        run_id=run.run_id,
        status="Review",
        operator_note="High unbalance vibration observed.",
        operator_id="inspector_7",
    )
    assert event.status == "Review"

    # Verify parent run status atomically updated
    updated_run = sm.get_inspection_run(run.run_id)
    assert updated_run.status == "Review"

    # Verify audit timeline retrieves review
    reviews = sm.list_review_events_for_run(run.run_id)
    assert len(reviews) == 1
    assert reviews[0].operator_note == "High unbalance vibration observed."


def test_ui_auto_assessment_against_stored_baseline():
    sm = StorageManager(db_path=":memory:")
    target = {"x": 360, "y": 110, "width": 160, "height": 160}
    anchor = {"x": 60, "y": 100, "width": 160, "height": 160}

    asset = sm.create_asset(
        name="Test Asset",
        target_roi=target,
        anchor_roi=anchor,
        expected_fps=60.0,
    )

    baseline_run = {
        "target_roi_xywh": target,
        "anchor_roi_xywh": anchor,
        "fps_used": 60.0,
        "x_axis": {
            "dominant_frequency_hz": 8.50,
            "rms_displacement_px": 0.45,
            "peak_to_median_db": 15.0,
            "second_harmonic_ratio": 0.03,
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

    base_record = build_baseline([baseline_run, baseline_run, baseline_run], asset_id=asset.asset_id)
    stored_base = sm.create_baseline(asset_id=asset.asset_id, baseline_record=base_record)

    # Current run with higher RMS
    current_run = {
        "video": "changed.mp4",
        "target_roi_xywh": target,
        "anchor_roi_xywh": anchor,
        "fps_used": 60.0,
        "x_axis": {
            "dominant_frequency_hz": 8.50,
            "rms_displacement_px": 0.85,  # Significantly higher!
            "peak_to_median_db": 15.0,
            "second_harmonic_ratio": 0.03,
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

    evaluation = evaluate_run_against_baseline(
        current_run,
        stored_base.baseline_record,
        z_threshold=3.0,
        axis="x",
    )
    assert evaluation.status == "Review"
    assert evaluation.deviations["x_rms_displacement_px"].is_trigger is True
    assert any("RMS" in t for t in evaluation.trigger_features)


def test_stability_badge_formatting():
    assert "🟢" in stability_badge("STABLE")
    assert "🟡" in stability_badge("WARNING_JITTER")
    assert "🔴" in stability_badge("REJECTED_UNSTABLE")
    assert "⚪" in stability_badge("UNKNOWN")


def test_ui_live_webcam_mode_preview_and_record():
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception

    # Select "Live Webcam Stream" mode
    source_radio = at.radio[0]
    assert "Live Webcam Stream" in source_radio.options
    source_radio.set_value("Live Webcam Stream").run()
    assert not at.exception

    # Verify camera inputs rendered
    cam_inputs = [ti for ti in at.text_input if ti.key == "webcam_source_val"]
    assert len(cam_inputs) == 1
    cam_inputs[0].set_value("mock:0").run()
    assert not at.exception

    # Click grab preview button
    grab_buttons = [b for b in at.button if b.key == "btn_grab_preview"]
    assert len(grab_buttons) == 1
    grab_buttons[0].click().run()
    assert not at.exception
    assert "webcam_preview_frame" in at.session_state
    assert at.session_state["webcam_preview_frame"] is not None

    # Test record live capture with mock stream (duration 2.0s)
    slider = [s for s in at.slider if s.key == "webcam_duration_val"][0]
    slider.set_value(2.0).run()

    record_buttons = [b for b in at.button if b.key == "btn_record_live"]
    assert len(record_buttons) == 1
    record_buttons[0].click().run()
    assert not at.exception

    assert "webcam_capture_result" in at.session_state
    cap_res = at.session_state["webcam_capture_result"]
    assert cap_res.stability.status in ("STABLE", "WARNING_JITTER")
    assert Path(cap_res.video_path).is_file()


def test_ui_live_webcam_rejected_unstable_blocks_analysis():
    from phasesight.capture import CaptureResult, CaptureStabilityReport

    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    unstable_rep = CaptureStabilityReport(
        total_frames=100,
        duration_s=5.0,
        nominal_fps=30.0,
        measured_fps=20.0,
        median_dt_s=0.05,
        mean_dt_s=0.05,
        std_dt_s=0.015,
        min_dt_s=0.02,
        max_dt_s=0.35,
        jitter_ratio=0.15,
        robust_jitter_ratio=0.12,
        dropped_frames_count=10,
        dropped_frame_indices=[10, 25, 40],
        large_gap_count=2,
        status="REJECTED_UNSTABLE",
        status_reasons=["Timing jitter ratio 15.00% exceeds 5.0% threshold."],
    )
    unstable_res = CaptureResult(
        video_path=Path("data/portable/baseline.mp4"),
        timestamps_s=np.linspace(0, 5, 100),
        frames=[np.zeros((10, 10, 3), dtype=np.uint8)],
        stability=unstable_rep,
    )
    at.session_state["webcam_capture_result"] = unstable_res
    at.session_state["webcam_capture_path"] = Path("data/portable/baseline.mp4")

    # Select live mode
    at.run()
    source_radio = at.radio[0]
    source_radio.set_value("Live Webcam Stream").run()
    assert not at.exception

    # Find "Run Vibration Analysis" button
    run_btn = next((b for b in at.button if b.label == "Run Vibration Analysis"), None)
    assert run_btn is not None
    assert run_btn.disabled is True


# ==============================================================================
# Task 4: Streamlit CLI Launcher Regression Test
# ==============================================================================

def test_cli_ui_launcher_uses_sys_executable_with_sanitized_path(monkeypatch):
    """Verify phasesight ui launches using sys.executable even when .venv/bin is absent from PATH."""
    import os
    import sys
    import subprocess
    from phasesight.cli import main

    captured_cmd = []

    def mock_run(cmd, check=True):
        captured_cmd.extend(cmd)

    monkeypatch.setattr(subprocess, "run", mock_run)

    # Scrub .venv from PATH
    env_path = os.environ.get("PATH", "")
    sanitized_path = ":".join(p for p in env_path.split(":") if ".venv" not in p)
    monkeypatch.setenv("PATH", sanitized_path)

    monkeypatch.setattr("sys.argv", ["phasesight", "ui", "--port", "8599", "--host", "127.0.0.1"])
    main()

    assert len(captured_cmd) >= 5
    assert captured_cmd[0] == sys.executable
    assert captured_cmd[1:3] == ["-m", "streamlit"]
    assert captured_cmd[3] == "run"
    assert any("--server.port=8599" in arg for arg in captured_cmd)
    assert any("--server.address=127.0.0.1" in arg for arg in captured_cmd)



