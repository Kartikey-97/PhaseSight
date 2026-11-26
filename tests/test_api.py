"""Comprehensive integration tests for PhaseSight FastAPI backend."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import time
from typing import Generator

import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend.deps import get_manager, get_storage
from backend.main import app
from backend.manager import MonitoringManager
from phasesight.storage import StorageManager
from phasesight.synthetic import DEFAULT_ANCHOR_ROI, DEFAULT_TARGET_ROI, SyntheticConfig, make_scene


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Isolated FastAPI test client with in-memory SQLite and temporary disk storage."""
    temp_storage = StorageManager(db_path=":memory:", storage_root=tmp_path)
    temp_manager = MonitoringManager(uploads_dir=tmp_path / "uploads")

    app.dependency_overrides[get_storage] = lambda: temp_storage
    app.dependency_overrides[get_manager] = lambda: temp_manager

    with TestClient(app) as test_client:
        yield test_client

    temp_manager.shutdown()
    temp_storage.close()
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Health Endpoint
# ---------------------------------------------------------------------------


def test_health_endpoint(client: TestClient):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "numpy" in data["versions"]
    assert "scipy" in data["versions"]
    assert "cv2" in data["versions"]
    assert "fastapi" in data["versions"]
    assert data["storage_ready"] is True
    assert data["active_session_id"] is None


# ---------------------------------------------------------------------------
# 2. Asset CRUD Endpoints
# ---------------------------------------------------------------------------


def test_asset_crud(client: TestClient):
    # 1. Create asset
    create_payload = {
        "name": "Compressor C101",
        "description": "Primary feed compressor",
        "nominal_speed_rpm": 1800.0,
        "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
        "expected_fps": 60.0,
        "asset_id": "ast_comp_101",
    }
    resp = client.post("/api/v1/assets", json=create_payload)
    assert resp.status_code == 201
    created = resp.json()
    assert created["asset_id"] == "ast_comp_101"
    assert created["name"] == "Compressor C101"

    # 2. List assets
    resp_list = client.get("/api/v1/assets")
    assert resp_list.status_code == 200
    assets = resp_list.json()
    assert len(assets) == 1
    assert assets[0]["asset_id"] == "ast_comp_101"

    # 3. Get single asset
    resp_get = client.get("/api/v1/assets/ast_comp_101")
    assert resp_get.status_code == 200
    assert resp_get.json()["asset_id"] == "ast_comp_101"

    # 4. Delete asset
    resp_del = client.delete("/api/v1/assets/ast_comp_101")
    assert resp_del.status_code == 200
    assert resp_del.json()["status"] == "deleted"

    # 5. Verify 404
    resp_get_deleted = client.get("/api/v1/assets/ast_comp_101")
    assert resp_get_deleted.status_code == 404


# ---------------------------------------------------------------------------
# 3. Video Presets, Preview, and ROI Validation
# ---------------------------------------------------------------------------


def test_video_presets_preview_and_check_rois(client: TestClient):
    # 1. List presets
    resp_presets = client.get("/api/v1/videos/presets")
    assert resp_presets.status_code == 200
    presets = resp_presets.json()
    assert len(presets) >= 4
    preset_ids = [p["preset_id"] for p in presets]
    assert "portable_baseline" in preset_ids

    # 2. Preview portable_baseline
    resp_prev = client.post(
        "/api/v1/videos/preview", data={"preset_id": "portable_baseline"}
    )
    assert resp_prev.status_code == 200
    prev_data = resp_prev.json()
    assert prev_data["width"] > 0
    assert prev_data["height"] > 0
    assert len(prev_data["preview_png_base64"]) > 100
    assert prev_data["default_target_roi"] == {
        "x": 360,
        "y": 110,
        "width": 160,
        "height": 160,
    }

    # 3. Check ROIs (valid)
    check_payload = {
        "preset_id": "portable_baseline",
        "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
    }
    resp_check = client.post("/api/v1/videos/check-rois", json=check_payload)
    assert resp_check.status_code == 200
    check_data = resp_check.json()
    assert check_data["valid"] is True
    assert check_data["target_texture_std"] > 2.0
    assert check_data["anchor_texture_std"] > 2.0
    assert check_data["errors"] == []

    # 4. Check ROIs (invalid overlap)
    invalid_check = {
        "preset_id": "portable_baseline",
        "target_roi": {"x": 100, "y": 100, "width": 100, "height": 100},
        "anchor_roi": {"x": 100, "y": 100, "width": 100, "height": 100},
    }
    resp_inv = client.post("/api/v1/videos/check-rois", json=invalid_check)
    assert resp_inv.status_code == 200
    assert resp_inv.json()["valid"] is False
    assert len(resp_inv.json()["errors"]) > 0


# ---------------------------------------------------------------------------
# 4. Batch Analysis Endpoint (`portable_baseline`)
# ---------------------------------------------------------------------------


def test_runs_analyze_portable_baseline(client: TestClient):
    payload = {
        "preset_id": "portable_baseline",
        "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
        "asset_id": "ast_portable_rig",
        "nperseg": 256,
    }
    resp = client.post("/api/v1/runs/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()

    assert data["run_id"] is not None
    assert data["asset_id"] == "ast_portable_rig"
    summary = data["summary"]
    assert abs(summary["x_axis"]["dominant_frequency_hz"] - 8.5) < 0.2
    assert summary["x_axis"]["signal_quality"] == "VALID"
    assert "arrays" in data
    assert len(data["arrays"]["timestamps_s"]) > 0

    # Verify run persisted to GET /api/v1/runs
    resp_list = client.get("/api/v1/runs?asset_id=ast_portable_rig")
    assert resp_list.status_code == 200
    runs = resp_list.json()
    assert len(runs) == 1
    assert runs[0]["run_id"] == data["run_id"]

    # Verify run details with arrays
    resp_detail = client.get(f"/api/v1/runs/{data['run_id']}")
    assert resp_detail.status_code == 200
    detail = resp_detail.json()
    assert detail["run_id"] == data["run_id"]
    assert "arrays" in detail
    assert len(detail["arrays"]["timestamps_s"]) == len(
        detail["arrays"]["relative_dx_px"]
    )


# ---------------------------------------------------------------------------
# 5. Batch Analysis Endpoint on Mendeley Rotor Dataset
# ---------------------------------------------------------------------------


def test_runs_analyze_rotor_dataset(client: TestClient):
    rotor_file = Path("data/rotor_dataset/Raw videos/1000rpm-Unb1.avi")
    if not rotor_file.is_file():
        pytest.skip("Mendeley 1000rpm-Unb1.avi not present")

    payload = {
        "preset_id": "rotor_1000rpm_unb1",
        "target_roi": {"x": 850, "y": 460, "width": 64, "height": 64},
        "anchor_roi": {"x": 600, "y": 560, "width": 64, "height": 64},
        "fps_override": 500.0,
        "nperseg": 256,
        "asset_id": "ast_rotor_1000",
    }
    resp = client.post("/api/v1/runs/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    summary = data["summary"]

    # 1000 RPM fundamental is 16.67 Hz (recovering ~16.5 Hz on X)
    x_freq = summary["x_axis"]["dominant_frequency_hz"]
    assert abs(x_freq - 16.5) < 1.0

    # Y axis has strong 2X harmonic around 33.2 Hz
    y_freq = summary["y_axis"]["dominant_frequency_hz"]
    assert abs(y_freq - 33.2) < 1.5


# ---------------------------------------------------------------------------
# 6. Continuous Video Replay Session Lifecycle & WebSockets
# ---------------------------------------------------------------------------


def test_video_replay_session_lifecycle(client: TestClient):
    start_payload = {
        "session_id": "live_replay_sess",
        "source_type": "video_replay",
        "preset_id": "portable_baseline",
        "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
        "playback_rate": 20.0,
        "loop": True,
    }
    resp_start = client.post("/api/v1/sessions", json=start_payload)
    assert resp_start.status_code == 201
    assert resp_start.json()["session_id"] == "live_replay_sess"

    # Conflict check: concurrent second session must return 409
    resp_conflict = client.post("/api/v1/sessions", json=start_payload)
    assert resp_conflict.status_code == 409

    # Connect WebSocket telemetry
    with client.websocket_connect(
        "/ws/v1/sessions/live_replay_sess/telemetry"
    ) as ws:
        # Read messages until we see ACTIVE or timeout
        start_t = time.perf_counter()
        reached_active = False
        while (time.perf_counter() - start_t) < 10.0:
            msg = ws.receive_json()
            if msg.get("state") == "ACTIVE":
                reached_active = True
                assert (
                    abs(msg["x_axis"]["dominant_frequency_hz"] - 8.5) < 0.5
                )
                break

        assert reached_active is True

    # Frame JPEG preview endpoint
    resp_frame = client.get("/api/v1/sessions/live_replay_sess/frame.jpg")
    assert resp_frame.status_code == 200
    assert resp_frame.headers["content-type"] == "image/jpeg"
    assert resp_frame.content.startswith(b"\xff\xd8")

    # Stop session
    resp_stop = client.post("/api/v1/sessions/live_replay_sess/stop")
    assert resp_stop.status_code == 200
    stop_data = resp_stop.json()
    assert stop_data["session_id"] == "live_replay_sess"
    assert stop_data["run_id"] is not None
    assert stop_data["state"] == "PERSISTED"


# ---------------------------------------------------------------------------
# 7. Browser Webcam Binary Ingest WebSocket & NaN-Safe Serialization
# ---------------------------------------------------------------------------


def test_browser_webcam_binary_ingest_lifecycle(client: TestClient):
    target_roi = DEFAULT_TARGET_ROI  # 70x70
    anchor_roi = DEFAULT_ANCHOR_ROI  # 70x70

    start_payload = {
        "session_id": "webcam_sess_1",
        "source_type": "browser_webcam",
        "target_roi": {
            "x": target_roi.x,
            "y": target_roi.y,
            "width": target_roi.width,
            "height": target_roi.height,
        },
        "anchor_roi": {
            "x": anchor_roi.x,
            "y": anchor_roi.y,
            "width": anchor_roi.width,
            "height": anchor_roi.height,
        },
        "expected_fps": 60.0,
        "buffer_capacity": 512,
    }
    resp_start = client.post("/api/v1/sessions", json=start_payload)
    assert resp_start.status_code == 201

    # Generate synthetic frames (60 FPS, 8.5 Hz)
    synth_cfg = SyntheticConfig(
        duration_s=5.0,
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.4,
        noise_sigma=0.5,
        seed=200,
    )
    frames, _ = make_scene(synth_cfg)

    # Stream 260 binary packets into ingest WebSocket
    header_fmt = "<dIHHHHI"
    with client.websocket_connect("/ws/v1/sessions/webcam_sess_1/ingest") as ws:
        for i in range(260):
            t_s = i / 60.0
            frame = frames[i]

            # Ingest 1 flat frame at index 50 to test NaN/inf handling
            if i == 50:
                t_patch = np.zeros(
                    (target_roi.height, target_roi.width), dtype=np.uint8
                )
                a_patch = np.zeros(
                    (anchor_roi.height, anchor_roi.width), dtype=np.uint8
                )
            else:
                t_patch = (
                    target_roi.crop(frame).astype(np.uint8)
                    if frame.ndim == 2
                    else target_roi.crop(frame)[:, :, 0].astype(np.uint8)
                )
                a_patch = (
                    anchor_roi.crop(frame).astype(np.uint8)
                    if frame.ndim == 2
                    else anchor_roi.crop(frame)[:, :, 0].astype(np.uint8)
                )

            header = struct.pack(
                header_fmt,
                float(t_s),
                i,
                target_roi.width,
                target_roi.height,
                anchor_roi.width,
                anchor_roi.height,
                0,
            )
            packet = header + t_patch.tobytes() + a_patch.tobytes()
            ws.send_bytes(packet)

    # Now verify telemetry WebSocket connects and reports ACTIVE without serialization crash
    with client.websocket_connect(
        "/ws/v1/sessions/webcam_sess_1/telemetry"
    ) as ws_telem:
        msg = ws_telem.receive_json()
        assert msg["type"] == "snapshot"
        assert msg["state"] == "ACTIVE"
        assert abs(msg["x_axis"]["dominant_frequency_hz"] - 8.5) < 0.5
        # Verify valid_ratio accounts for the 1 flat frame
        assert msg["valid_ratio"] < 1.0

    # Stop session cleanly
    resp_stop = client.post("/api/v1/sessions/webcam_sess_1/stop")
    assert resp_stop.status_code == 200
    assert resp_stop.json()["state"] == "PERSISTED"


# ---------------------------------------------------------------------------
# 8. Baseline Quorum and Strict Validity Enforcement
# ---------------------------------------------------------------------------


def test_baseline_build_valid_axes_enforcement(
    client: TestClient, tmp_path: Path
):
    storage = StorageManager(db_path=":memory:", storage_root=tmp_path)
    app.dependency_overrides[get_storage] = lambda: storage

    asset = storage.create_asset(
        name="Turbine T1",
        target_roi={"x": 100, "y": 100, "width": 64, "height": 64},
        anchor_roi={"x": 200, "y": 100, "width": 64, "height": 64},
        expected_fps=60.0,
        asset_id="ast_turbine_1",
    )

    # Create 3 runs: X axis is VALID, Y axis is LOW_SIGNAL
    run_ids = []
    for idx in range(3):
        summary = {
            "video": f"run_{idx + 1}.mp4",
            "fps_used": 60.0,
            "target_roi_xywh": {"x": 100, "y": 100, "width": 64, "height": 64},
            "anchor_roi_xywh": {"x": 200, "y": 100, "width": 64, "height": 64},
            "x_axis": {
                "dominant_frequency_hz": 12.0,
                "rms_displacement_px": 0.25,
                "peak_to_median_db": 22.0,
                "second_harmonic_ratio": None,
                "signal_quality": "VALID",
            },
            "y_axis": {
                "dominant_frequency_hz": 5.0,
                "rms_displacement_px": 0.05,
                "peak_to_median_db": 6.0,  # < 10 dB -> LOW_SIGNAL
                "second_harmonic_ratio": None,
                "signal_quality": "LOW_SIGNAL",
            },
        }
        rec = storage.create_inspection_run(
            asset_id="ast_turbine_1",
            video_path=f"run_{idx + 1}.mp4",
            measured_fps=60.0,
            duration_s=10.0,
            frames_analysed=600,
            summary=summary,
            status="Unassessed",
        )
        run_ids.append(rec.run_id)

    # 1. Strict require_valid_axes=["x", "y"] must fail with HTTP 422
    fail_payload = {
        "asset_id": "ast_turbine_1",
        "run_ids": run_ids,
        "require_valid_axes": ["x", "y"],
        "notes": "Strict two-axis baseline",
    }
    resp_fail = client.post("/api/v1/baselines/build", json=fail_payload)
    assert resp_fail.status_code == 422
    assert "Y-axis signal quality is 'LOW_SIGNAL'" in resp_fail.json()["detail"]

    # 2. Relaxed require_valid_axes=["x"] must succeed with HTTP 201
    success_payload = {
        "asset_id": "ast_turbine_1",
        "run_ids": run_ids,
        "require_valid_axes": ["x"],
        "notes": "X-axis only baseline",
    }
    resp_ok = client.post("/api/v1/baselines/build", json=success_payload)
    assert resp_ok.status_code == 201
    baseline_data = resp_ok.json()
    assert baseline_data["asset_id"] == "ast_turbine_1"
    assert baseline_data["run_count"] == 3
    assert (
        baseline_data["baseline_record"]["x_axis"]["dominant_frequency_hz"][
            "median"
        ]
        == 12.0
    )


# ---------------------------------------------------------------------------
# 11. Custom Video Upload & Analysis Flow (upload_id only)
# ---------------------------------------------------------------------------


def test_custom_video_upload_flow(client: TestClient):
    """Test full multipart video upload to preview, ROI check, and offline batch analysis using upload_id only."""
    video_path = Path("data/portable/baseline.mp4")
    assert video_path.is_file(), f"Test video not found: {video_path}"
    video_bytes = video_path.read_bytes()

    # 1. Upload multipart .mp4 file to /api/v1/videos/preview
    files = {"file": ("test_upload.mp4", video_bytes, "video/mp4")}
    resp_prev = client.post("/api/v1/videos/preview", files=files)
    assert resp_prev.status_code == 200
    prev_data = resp_prev.json()
    upload_id = prev_data["upload_id"]
    assert upload_id is not None
    assert upload_id.startswith("upl_")
    assert prev_data["preset_id"] is None
    assert prev_data["frame_width"] > 0
    assert prev_data["frame_height"] > 0
    assert prev_data["preview_png_base64"]

    # 2. Check ROIs using upload_id (no preset_id)
    target_roi = {"x": 360, "y": 110, "width": 160, "height": 160}
    anchor_roi = {"x": 60, "y": 100, "width": 160, "height": 160}
    check_payload = {
        "upload_id": upload_id,
        "preset_id": None,
        "target_roi": target_roi,
        "anchor_roi": anchor_roi,
    }
    resp_check = client.post("/api/v1/videos/check-rois", json=check_payload)
    assert resp_check.status_code == 200
    check_data = resp_check.json()
    assert check_data["valid"] is True
    assert check_data["target_texture_std"] >= 2.0
    assert check_data["anchor_texture_std"] >= 2.0

    # 3. Execute offline batch analysis with upload_id (no preset_id)
    analyze_payload = {
        "upload_id": upload_id,
        "preset_id": None,
        "target_roi": target_roi,
        "anchor_roi": anchor_roi,
        "asset_id": "ast_comp_101",
        "fps_override": 60.0,
        "nperseg": 256,
    }
    resp_analyze = client.post("/api/v1/runs/analyze", json=analyze_payload)
    assert resp_analyze.status_code == 200
    res_data = resp_analyze.json()
    assert res_data["run_id"].startswith("run_")
    summary = res_data["summary"]
    assert summary["frames_analysed"] == 600
    # Portable baseline has ~8.5 Hz dominant frequency on X axis
    x_dom = summary["x_axis"]["dominant_frequency_hz"]
    assert 8.0 <= x_dom <= 9.0
    assert summary["x_axis"]["signal_quality"] == "VALID"


def test_browser_webcam_ignores_fps_override(client: TestClient):
    """Ensure browser_webcam enforces timebase_source='browser_media_time' and ignores stale fps_override."""
    payload = {
        "source_type": "browser_webcam",
        "target_roi": {"x": 100, "y": 100, "width": 64, "height": 64},
        "anchor_roi": {"x": 20, "y": 20, "width": 64, "height": 64},
        "fps_override": 500.0,
        "expected_fps": 30.0,
    }
    resp = client.post("/api/v1/sessions", json=payload)
    assert resp.status_code == 201
    sess_id = resp.json()["session_id"]

    manager = app.dependency_overrides[get_manager]()
    session = manager.get_session(sess_id)
    assert session is not None
    assert session.config.timebase_source == "browser_media_time"
    assert session.config.expected_fps == 30.0

    telem_resp = client.get(f"/api/v1/sessions/{sess_id}")
    assert telem_resp.status_code == 200
    telem = telem_resp.json()
    assert telem["timebase_source"] == "browser_media_time"
    assert telem["measured_fps"] == 30.0

    stop_resp = client.post(f"/api/v1/sessions/{sess_id}/stop")
    assert stop_resp.status_code == 200

