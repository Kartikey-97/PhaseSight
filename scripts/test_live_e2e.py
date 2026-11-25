#!/usr/bin/env python3
"""
Comprehensive Live E2E Verification Script:
Tests all core workflows against live Uvicorn (port 8000) + Next.js (port 3000):
1. portable_baseline continuous replay -> reaches ACTIVE (~8.5 Hz X) -> POST /recalibrate -> re-reaches ACTIVE -> POST /stop with measured_fps > 0 (~60 FPS).
2. Mendeley rotor_1000rpm_unb1 continuous replay (fps_override=500.0, playback_rate=0.25, loop=True) -> reaches ACTIVE -> recovers X frequency ~16.5 Hz with timing_status == "ASSUMED_UNIFORM".
3. Batch analysis on portable_baseline (calibrates Asset baseline) -> evaluates portable_changed against baseline -> confirms status == "Review" with elevated RMS z-score.
4. Clean shutdown of servers and isolated temp storage cleanup.
"""

import asyncio
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import websockets


async def run_comprehensive_e2e():
    temp_dir = tempfile.mkdtemp(prefix="phasesight_e2e_")
    print(f"Using isolated temporary storage root: {temp_dir}")

    backend_env = {
        **os.environ,
        "PHASESIGHT_STORAGE_ROOT": temp_dir,
        "MPLCONFIGDIR": "/tmp",
    }
    frontend_env = {
        **os.environ,
        "NEXT_PUBLIC_API_BASE": "http://127.0.0.1:8000",
        "NEXT_PUBLIC_WS_BASE": "ws://127.0.0.1:8000",
    }

    print("\n=== [1/6] Launching FastAPI backend (port 8000) & Next.js frontend (port 3000) ===")
    backend_proc = subprocess.Popen(
        [
            ".venv/bin/python",
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        env=backend_env,
    )
    frontend_proc = subprocess.Popen(
        ["npm", "run", "start", "--", "--hostname", "127.0.0.1", "--port", "3000"],
        cwd="frontend",
        env=frontend_env,
    )

    try:
        # 1. Health check backend
        print("Waiting for backend on http://127.0.0.1:8000/api/v1/health...")
        backend_ready = False
        for _ in range(30):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=2) as resp:
                    if resp.status == 200:
                        data = json.loads(resp.read().decode())
                        print("Backend Online:", data["status"], data["versions"])
                        backend_ready = True
                        break
            except Exception:
                continue
        if not backend_ready:
            raise RuntimeError("Backend failed to start on port 8000")

        # 2. Health check frontend
        print("Waiting for Next.js frontend on http://127.0.0.1:3000...")
        frontend_ready = False
        for _ in range(40):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:3000", timeout=2) as resp:
                    if resp.status == 200:
                        print("Frontend Online: HTTP 200 OK")
                        frontend_ready = True
                        break
            except Exception:
                continue
        if not frontend_ready:
            raise RuntimeError("Frontend failed to start on port 3000")

        # ======================================================================
        # WORKFLOW 1: portable_baseline continuous replay + recalibration
        # ======================================================================
        print("\n=== [2/6] Workflow 1: portable_baseline replay + recalibrate + persist ===")
        req1 = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/sessions",
            data=json.dumps({
                "source_type": "video_replay",
                "preset_id": "portable_baseline",
                "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
                "playback_rate": 2.0,
                "loop": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req1) as resp:
            sdata1 = json.loads(resp.read().decode())
            sid1 = sdata1["session_id"]
            print(f"Session 1 started: {sid1}")

        # Connect WebSocket and wait for ACTIVE
        ws_url1 = f"ws://127.0.0.1:8000/ws/v1/sessions/{sid1}/telemetry"
        async with websockets.connect(ws_url1) as ws:
            start_t = time.time()
            first_active = False
            while time.time() - start_t < 25:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                mtype = msg.get("type") or msg.get("message_type")
                if mtype == "rolling_update":
                    state = msg.get("state")
                    if state == "ACTIVE":
                        first_active = True
                        x_ax = msg.get("x_axis") or msg.get("x_metrics", {})
                        freq1 = x_ax.get("dominant_frequency_hz", 0.0)
                        print(f"  Reached ACTIVE: X Peak = {freq1:.2f} Hz (expected ~8.51 Hz)")
                        assert 7.5 <= freq1 <= 9.5, f"Expected ~8.5 Hz, got {freq1}"
                        break

            assert first_active, "Session 1 did not reach ACTIVE"

            # Test POST /recalibrate
            print("  Triggering POST /recalibrate...")
            recal_req = urllib.request.Request(
                f"http://127.0.0.1:8000/api/v1/sessions/{sid1}/recalibrate",
                data=b"",
                method="POST",
            )
            with urllib.request.urlopen(recal_req) as resp:
                recal_res = json.loads(resp.read().decode())
                print(f"  Recalibration requested: {recal_res.get('status', 'ok')}")

            # Verify buffer resets and re-reaches ACTIVE
            recal_active = False
            start_t = time.time()
            while time.time() - start_t < 25:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                mtype = msg.get("type") or msg.get("message_type")
                if mtype == "rolling_update":
                    state = msg.get("state")
                    if state == "ACTIVE":
                        recal_active = True
                        x_ax = msg.get("x_axis") or msg.get("x_metrics", {})
                        freq_recal = x_ax.get("dominant_frequency_hz", 0.0)
                        print(f"  Re-reached ACTIVE after recalibration: X Peak = {freq_recal:.2f} Hz")
                        break

            assert recal_active, "Session 1 did not re-reach ACTIVE after recalibration"

        # Stop session 1
        stop_req1 = urllib.request.Request(
            f"http://127.0.0.1:8000/api/v1/sessions/{sid1}/stop",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(stop_req1) as resp:
            stop_res1 = json.loads(resp.read().decode())
            rep1 = stop_res1.get("report") or stop_res1
            run_id1 = stop_res1.get("run_id")
            fps1 = rep1.get("measured_fps", 0.0)
            frames1 = rep1.get("frames_analysed", 0)
            print(f"  Session 1 stopped: run_id={run_id1}, measured_fps={fps1:.1f}, frames={frames1}")
            assert fps1 > 0.0, f"Expected measured_fps > 0, got {fps1}"
            assert frames1 > 200, f"Expected frames > 200, got {frames1}"

        # ======================================================================
        # WORKFLOW 2: Mendeley rotor_1000rpm_unb1 replay (500 FPS) -> ~16.5 Hz
        # ======================================================================
        print("\n=== [3/6] Workflow 2: Mendeley 1000 RPM continuous replay (500 FPS) ===")
        req2 = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/sessions",
            data=json.dumps({
                "source_type": "video_replay",
                "preset_id": "rotor_1000rpm_unb1",
                "target_roi": {"x": 850, "y": 460, "width": 64, "height": 64},
                "anchor_roi": {"x": 600, "y": 560, "width": 64, "height": 64},
                "fps_override": 500.0,
                "playback_rate": 0.25,
                "loop": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req2) as resp:
            sdata2 = json.loads(resp.read().decode())
            sid2 = sdata2["session_id"]
            print(f"Session 2 started: {sid2}")

        ws_url2 = f"ws://127.0.0.1:8000/ws/v1/sessions/{sid2}/telemetry"
        async with websockets.connect(ws_url2) as ws:
            start_t = time.time()
            rotor_active = False
            rotor_freq = 0.0
            timing_status = ""
            while time.time() - start_t < 30:
                raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                msg = json.loads(raw)
                mtype = msg.get("type") or msg.get("message_type")
                if mtype == "rolling_update":
                    state = msg.get("state")
                    if state == "ACTIVE":
                        rotor_active = True
                        x_ax = msg.get("x_axis") or msg.get("x_metrics", {})
                        rotor_freq = x_ax.get("dominant_frequency_hz", 0.0)
                        timing_status = msg.get("timing_status", "")
                        print(f"  Rotor ACTIVE: X Peak = {rotor_freq:.2f} Hz, timing_status = {timing_status}")
                        break

            assert rotor_active, "Rotor session did not reach ACTIVE"
            assert 15.0 <= rotor_freq <= 18.0, f"Expected ~16.5 Hz, got {rotor_freq}"
            assert timing_status == "ASSUMED_UNIFORM", f"Expected ASSUMED_UNIFORM, got {timing_status}"

        # Stop session 2
        stop_req2 = urllib.request.Request(
            f"http://127.0.0.1:8000/api/v1/sessions/{sid2}/stop",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(stop_req2) as resp:
            stop_res2 = json.loads(resp.read().decode())
            rep2 = stop_res2.get("report") or stop_res2
            fps2 = rep2.get("measured_fps", 0.0)
            print(f"  Session 2 stopped: run_id={stop_res2.get('run_id')}, measured_fps={fps2:.1f}")
            assert fps2 == 500.0, f"Expected measured_fps == 500.0, got {fps2}"

        # ======================================================================
        # WORKFLOW 3: Batch Analysis -> Asset & Baseline -> Review Detection
        # ======================================================================
        print("\n=== [4/6] Workflow 3: Batch analysis, Baseline building & Review evaluation ===")
        # Create an asset for calibration
        asset_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/assets",
            data=json.dumps({
                "name": "E2E Pump Unit",
                "nominal_rpm": 510,
                "expected_fps": 60.0,
                "default_target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                "default_anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(asset_req) as resp:
            asset_data = json.loads(resp.read().decode())
            asset_id = asset_data["asset_id"]
            print(f"Asset created: {asset_id} ({asset_data['name']})")

        # Run 3 batch analyses on portable_baseline to establish calibration distribution
        baseline_run_ids = []
        for i in range(3):
            b_req = urllib.request.Request(
                "http://127.0.0.1:8000/api/v1/runs/analyze",
                data=json.dumps({
                    "preset_id": "portable_baseline",
                    "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                    "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
                    "asset_id": asset_id,
                    "nperseg": 256,
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(b_req) as resp:
                res_b = json.loads(resp.read().decode())
                baseline_run_ids.append(res_b["run_id"])
                print(f"  Calibration run {i+1}/3 completed: {res_b['run_id']}")

        # Build statistical baseline
        print(f"  Building baseline with runs: {baseline_run_ids}")
        build_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/baselines/build",
            data=json.dumps({
                "asset_id": asset_id,
                "run_ids": baseline_run_ids,
                "require_valid_axes": ["x"],
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(build_req) as resp:
            base_res = json.loads(resp.read().decode())
            base_id = base_res["baseline_id"]
            x_med = base_res["x_baseline"]["dominant_frequency_hz_median"]
            x_rms_med = base_res["x_baseline"]["rms_displacement_px_median"]
            print(f"  Baseline built: ID={base_id}, X Freq Median={x_med:.2f} Hz, X RMS Median={x_rms_med:.4f} px")

        # Analyze portable_changed against the baseline
        print("  Analyzing portable_changed against active baseline...")
        changed_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/runs/analyze",
            data=json.dumps({
                "preset_id": "portable_changed",
                "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
                "asset_id": asset_id,
                "nperseg": 256,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(changed_req) as resp:
            changed_res = json.loads(resp.read().decode())
            assess = changed_res.get("baseline_assessment") or {}
            status = assess.get("status") or assess.get("overall_status")
            dev_zs = [
                abs(v.get("z_robust", 0.0))
                for v in assess.get("deviations", {}).values()
                if v and v.get("z_robust") is not None
            ]
            max_z = assess.get("max_z_score") or (max(dev_zs) if dev_zs else 0.0)
            print(f"  portable_changed evaluation: status={status}, max_z_score={max_z:.2f}")
            assert status == "Review", f"Expected status 'Review', got {status}"
            assert max_z > 3.0, f"Expected elevated z-score > 3.0, got {max_z}"

        # ======================================================================
        # WORKFLOW 4: Live Baseline Assessment over WebSocket Telemetry
        # ======================================================================
        print("\n=== [5/7] Workflow 4: Live baseline assessment on portable_changed over WebSocket ===")
        live_base_req = urllib.request.Request(
            "http://127.0.0.1:8000/api/v1/sessions",
            data=json.dumps({
                "source_type": "video_replay",
                "preset_id": "portable_changed",
                "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
                "asset_id": asset_id,
                "playback_rate": 2.0,
                "loop": True,
            }).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(live_base_req) as resp:
            sdata_live = json.loads(resp.read().decode())
            sid_live = sdata_live["session_id"]
            print(f"  Live session on portable_changed started: {sid_live}")

        ws_url_live = f"ws://127.0.0.1:8000/ws/v1/sessions/{sid_live}/telemetry"
        found_live_review = False
        async with websockets.connect(ws_url_live) as ws_live:
            start_t = time.time()
            while time.time() - start_t < 25:
                raw = await asyncio.wait_for(ws_live.recv(), timeout=5.0)
                msg = json.loads(raw)
                mtype = msg.get("type") or msg.get("message_type")
                if mtype == "rolling_update":
                    base_assess = msg.get("baseline_assessment")
                    if base_assess:
                        b_status = base_assess.get("status") or base_assess.get("overall_status")
                        print(f"  Live rolling baseline assessment received: status={b_status}, state={msg.get('state')}")
                        if b_status == "Review" or b_status == "REVIEW":
                            found_live_review = True
                            break

        assert found_live_review, "Live session on portable_changed did not emit baseline_assessment.status == 'Review'"

        # Stop session
        stop_live_req = urllib.request.Request(
            f"http://127.0.0.1:8000/api/v1/sessions/{sid_live}/stop",
            data=b"",
            method="POST",
        )
        with urllib.request.urlopen(stop_live_req) as resp:
            stop_res_live = json.loads(resp.read().decode())
            print(f"  Live session on portable_changed stopped: {stop_res_live.get('run_id')}")

        print("\n=== [6/7] Verifying runs list endpoint ===")
        with urllib.request.urlopen(f"http://127.0.0.1:8000/api/v1/runs?asset_id={asset_id}") as resp:
            runs_list = json.loads(resp.read().decode())
            print(f"  Asset {asset_id} has {len(runs_list)} registered runs.")
            assert len(runs_list) >= 4, f"Expected >= 4 runs for asset, got {len(runs_list)}"

        print("\n=== [7/7] ALL 4 CORE WORKFLOWS VERIFIED SUCCESSFULLY ===")

    finally:
        print("\nShutting down test servers...")
        try:
            backend_proc.terminate()
            backend_proc.wait(timeout=3)
        except Exception:
            backend_proc.kill()
        try:
            frontend_proc.terminate()
            frontend_proc.wait(timeout=3)
        except Exception:
            frontend_proc.kill()

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Cleaned up isolated temporary storage: {temp_dir}")
        print("Shutdown and cleanup complete.")


if __name__ == "__main__":
    asyncio.run(run_comprehensive_e2e())
