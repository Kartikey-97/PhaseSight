#!/usr/bin/env python3
"""
Real Browser E2E UI & getUserMedia Verification via Playwright (Headless Chromium):
1. Starts FastAPI (port 8000) + Next.js (port 3000) with isolated temp PHASESIGHT_STORAGE_ROOT.
2. Launches Chromium with --use-fake-ui-for-media-stream and --use-fake-device-for-media-stream.
3. Tests Live Monitor Mode A (Webcam getUserMedia, binary ingest WS, Stop & Save Report).
4. Tests Live Monitor Mode B (Video Replay rotor_1000rpm_unb1, waits for ACTIVE 16.5 Hz, screenshots).
5. Tests Batch Inspect (Run Offline Analysis, spectrum/trace charts, screenshots).
6. Tests Assets & History (Persisted runs table, run inspector drawer, screenshots).
7. Asserts 0 uncaught page errors and 0 HTTP 500 API responses.
"""

import asyncio
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
import cv2
from playwright.async_api import async_playwright


def convert_to_y4m(video_path: str, output_y4m: str, max_frames: int = 1500) -> str:
    """Converts a video file into a raw YUV4MPEG2 (.y4m) stream for Chromium fake video capture."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(round(cap.get(cv2.CAP_PROP_FPS))) or 60

    with open(output_y4m, "wb") as f:
        header = f"YUV4MPEG2 W{width} H{height} F{fps}:1 Ip A1:1 C420\n".encode("ascii")
        f.write(header)
        count = 0
        while count < max_frames:
            ret, frame = cap.read()
            if not ret:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame = cap.read()
                if not ret:
                    break
            i420 = cv2.cvtColor(frame, cv2.COLOR_BGR2YUV_I420)
            f.write(b"FRAME\n")
            f.write(i420.tobytes())
            count += 1
    cap.release()
    abs_path = os.path.abspath(output_y4m)
    print(f"Generated fake webcam stream {abs_path} ({count} frames @ {fps} FPS, {width}x{height})")
    return abs_path


async def run_browser_verification():
    temp_dir = tempfile.mkdtemp(prefix="phasesight_browser_")
    screenshots_dir = Path("reports/e2e_screenshots")
    screenshots_dir.mkdir(parents=True, exist_ok=True)
    print(f"Isolated temporary storage: {temp_dir}")
    print(f"Screenshots destination: {screenshots_dir}")

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

    print("\n=== [1/6] Launching FastAPI backend & Next.js frontend ===")
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
        # Wait for backend
        print("Waiting for backend on http://127.0.0.1:8000/api/v1/health...")
        for _ in range(30):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/api/v1/health", timeout=2) as resp:
                    if resp.status == 200:
                        print("Backend Ready.")
                        break
            except Exception:
                continue

        # Wait for frontend
        print("Waiting for Next.js frontend on http://127.0.0.1:3000...")
        for _ in range(40):
            time.sleep(0.5)
            try:
                with urllib.request.urlopen("http://127.0.0.1:3000", timeout=2) as resp:
                    if resp.status == 200:
                        print("Frontend Ready.")
                        break
            except Exception:
                continue

        page_errors: list[str] = []
        console_errors: list[str] = []
        http_500_errors: list[str] = []

        y4m_path = "tmp_baseline.y4m"
        fake_y4m_path = convert_to_y4m("data/portable/baseline.mp4", y4m_path, max_frames=1500)

        print("\n=== [2/6] Launching Chromium with textured fake camera device flags ===")
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--use-fake-device-for-media-stream",
                    f"--use-file-for-fake-video-capture={fake_y4m_path}",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1440, "height": 900},
                permissions=["camera"],
            )
            page = await context.new_page()

            # Error handlers
            page.on(
                "pageerror",
                lambda err: (
                    page_errors.append(str(err)),
                    print(f"  [BROWSER PAGEERROR] {err}\n  Stack: {getattr(err, 'stack', 'no stack')}"),
                ),
            )
            page.on(
                "console",
                lambda msg: (
                    console_errors.append(msg.text) if msg.type == "error" else None,
                    print(f"  [BROWSER {msg.type.upper()}] {msg.text}")
                    if msg.type in ("error", "warn")
                    else None,
                ),
            )

            def handle_response(resp):
                if resp.status >= 500:
                    http_500_errors.append(f"{resp.request.method} {resp.url} -> {resp.status}")

            page.on("response", handle_response)

            print("Navigating to http://127.0.0.1:3000...")
            await page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded")
            await page.wait_for_selector('[data-testid="mode-browser-camera"]', timeout=15000)

            # Assert Tailwind CSS compilation & active styles
            header_display = await page.evaluate(
                "() => window.getComputedStyle(document.querySelector('header')).display"
            )
            print(f"  Computed header display style: '{header_display}'")
            assert (
                header_display == "flex"
            ), f"Expected header display 'flex', got '{header_display}' (Tailwind CSS not applying)"

            # ==============================================================
            # TEST A: Live Monitor - Browser Camera Mode A
            # ==============================================================
            print("\n=== [3/6] Testing Mode A: Browser Webcam (getUserMedia + binary ingest) ===")
            await page.locator('[data-testid="mode-browser-camera"]').click()
            await asyncio.sleep(0.5)

            # 1. Click Enable Camera
            print("  Enabling camera stream...")
            await page.click('button:has-text("Enable Camera")')

            # Assert visible webcam video element is rendering with real dimensions
            await page.wait_for_selector("video", timeout=10000)
            video_rendered = await page.evaluate("""() => {
                const v = document.querySelector('video');
                return !!(v && v.videoWidth > 0 && v.offsetWidth > 200 && v.offsetHeight > 150);
            }""")
            print(f"  Webcam video element visible and sized: {video_rendered}")
            assert video_rendered, "Webcam <video> is not rendered or sized properly in the viewport"

            # 2. Set Target ROI to x=360, y=110, w=96, h=96 and Anchor ROI to x=60, y=100, w=96, h=96
            print("  Setting Target ROI (360,110,96,96) and Anchor ROI (60,100,96,96)...")
            await page.wait_for_selector('[data-testid="target-roi-x"]', timeout=10000)
            await page.fill('[data-testid="target-roi-x"]', "360")
            await page.fill('[data-testid="target-roi-y"]', "110")
            await page.fill('[data-testid="target-roi-w"]', "96")
            await page.fill('[data-testid="target-roi-h"]', "96")
            await page.fill('[data-testid="anchor-roi-x"]', "60")
            await page.fill('[data-testid="anchor-roi-y"]', "100")
            await page.fill('[data-testid="anchor-roi-w"]', "96")
            await page.fill('[data-testid="anchor-roi-h"]', "96")

            # 3. Wait for live JS texture readouts and explicitly assert target_std >= 2.0 AND anchor_std >= 2.0
            print("  Waiting for live JS texture readouts on webcam canvas...")
            target_std_val = 0.0
            anchor_std_val = 0.0
            for _ in range(40):
                await asyncio.sleep(0.5)
                tgt_el = await page.query_selector('span:has-text("Tgt σ=")')
                anc_el = await page.query_selector('span:has-text("Anc σ=")')
                if tgt_el and anc_el:
                    tgt_text = await tgt_el.inner_text()
                    anc_text = await anc_el.inner_text()
                    m_tgt = re.search(r"Tgt\s*σ=([\d.]+)", tgt_text)
                    m_anc = re.search(r"Anc\s*σ=([\d.]+)", anc_text)
                    if m_tgt and m_anc:
                        target_std_val = float(m_tgt.group(1))
                        anchor_std_val = float(m_anc.group(1))
                        if target_std_val >= 2.0 and anchor_std_val >= 2.0:
                            break

            print(f"  Live Camera Texture: Tgt σ={target_std_val:.1f} | Anc σ={anchor_std_val:.1f}")
            assert target_std_val >= 2.0, f"Expected target_std >= 2.0, got {target_std_val:.1f}"
            assert anchor_std_val >= 2.0, f"Expected anchor_std >= 2.0, got {anchor_std_val:.1f}"

            # 4. Click Start Continuous Monitoring, wait until state reaches ACTIVE with 7.5 - 9.5 Hz
            print("  Starting continuous monitoring with webcam binary stream...")
            start_btn = page.locator('[data-testid="btn-start-session"]')
            await start_btn.click()

            print("  Waiting for Live Monitor state ACTIVE and ~8.5 Hz dominant frequency (up to 25s)...")
            found_active = False
            state_text = ""
            dom_freq_val = 0.0
            timing_status_text = ""
            dropped_frames_text = ""

            for sec in range(50):
                await asyncio.sleep(0.5)
                state_el = await page.query_selector('span:has-text("ENGINE STATE:")')
                state_text = await state_el.inner_text() if state_el else ""
                sample_el = await page.query_selector('span:has-text("Seq #")')
                sample_text = await sample_el.inner_text() if sample_el else ""
                dom_el = await page.query_selector('[data-testid="live-x-dominant-freq"]')
                dom_text = await dom_el.inner_text() if dom_el else ""

                timing_el = await page.query_selector('[data-testid="live-timing-status-value"]')
                timing_status_text = await timing_el.inner_text() if timing_el else ""
                drop_el = await page.query_selector('[data-testid="live-dropped-frames-value"]')
                dropped_frames_text = await drop_el.inner_text() if drop_el else ""

                m_freq = re.search(r"([\d.]+)\s*Hz", dom_text)
                if m_freq:
                    dom_freq_val = float(m_freq.group(1))

                if sec % 2 == 0:
                    print(f"    [t={sec*0.5:.1f}s] {state_text} | Freq: {dom_text} | Timing: {timing_status_text} | Drops: {dropped_frames_text} | {sample_text}")

                if "ACTIVE" in state_text and 7.5 <= dom_freq_val <= 9.5:
                    found_active = True
                    break

            if not found_active:
                body_text = await page.evaluate("() => document.body.innerText")
                print("DEBUG BODY TEXT:\n", body_text[:1000])

            print(f"  Mode A Live Verification: State='{state_text}', TIMING STATUS='{timing_status_text}', DROPPED FRAMES={dropped_frames_text}, X-axis Frequency={dom_freq_val:.2f} Hz")
            assert "ACTIVE" in state_text, f"Expected ENGINE STATE: ACTIVE, got '{state_text}'"
            assert 7.5 <= dom_freq_val <= 9.5, f"Expected X-axis frequency between 7.5 Hz and 9.5 Hz, got {dom_freq_val:.2f} Hz"

            await asyncio.sleep(1.0)

            # Capture screenshot 00_webcam_live_active.png (strictly in ACTIVE state)
            await page.evaluate("() => window.scrollTo(0, 0)")
            shot0 = str(screenshots_dir / "00_webcam_live_active.png")
            await page.screenshot(path=shot0)
            print(f"  Saved screenshot: {shot0}")

            # Allow frames to stream
            await asyncio.sleep(3.5)

            # 5. Click Stop & Save Report, parse SessionReportModal text, assert frames_analysed >= 32 AND measured_fps > 10.0
            print("  Stopping webcam session & opening report modal...")
            await page.wait_for_selector('[data-testid="btn-stop-session"]', timeout=10000)
            await page.locator('[data-testid="btn-stop-session"]').click()
            await page.wait_for_selector('h2:has-text("INSPECTION RUN REPORT")', timeout=10000)
            await asyncio.sleep(0.5)

            modal_text = await page.inner_text('div:has-text("INSPECTION RUN REPORT")')
            m_frames = re.search(r"FRAMES ANALYSED\s*([\d,]+)", modal_text)
            m_fps = re.search(r"MEASURED FPS\s*([\d.]+)\s*Hz", modal_text)
            frames_analysed = int(m_frames.group(1).replace(",", "")) if m_frames else 0
            measured_fps = float(m_fps.group(1)) if m_fps else 0.0
            print(f"  SessionReportModal parsed values: frames_analysed={frames_analysed}, measured_fps={measured_fps:.1f} Hz")
            assert frames_analysed >= 32, f"Expected frames_analysed >= 32, got {frames_analysed}"
            assert measured_fps > 10.0, f"Expected measured_fps > 10.0, got {measured_fps:.1f}"

            print("  Webcam session report modal assertions passed cleanly.")
            await page.click('button:has-text("Close Report")')
            await asyncio.sleep(0.5)

            # ==============================================================
            # TEST B: Live Monitor - Video Replay Mode B (Mendeley 500 FPS)
            # ==============================================================
            print("\n=== [4/6] Testing Mode B: Video Replay rotor_1000rpm_unb1 (500 FPS) ===")
            await page.locator('[data-testid="mode-video-replay"]').click()
            await asyncio.sleep(0.5)

            # Select rotor_1000rpm_unb1
            print("  Selecting rotor_1000rpm_unb1 dataset preset...")
            await page.select_option('[data-testid="select-video-preset"]', value="rotor_1000rpm_unb1")
            await asyncio.sleep(1.0)

            # Assert preview image is rendered with natural dimensions
            preview_rendered = await page.evaluate("""() => {
                const img = document.querySelector('img[alt="Preview Frame 0"]');
                return !!(img && img.naturalWidth > 0 && img.offsetWidth > 200 && img.offsetHeight > 150);
            }""")
            print(f"  Replay preview frame 0 image rendered and sized: {preview_rendered}")
            assert preview_rendered, "Replay preview frame 0 <img> is not rendered or sized properly"

            # Verify FPS override banner displayed
            banner_present = await page.is_visible('div:has-text("500.0 (Nyquist = 250 Hz)")')
            print(f"  500 FPS explanation banner visible: {banner_present}")

            # Set replay playback rate to 0.25x (125 FPS replay) for fast buffer acquisition
            await page.evaluate("""() => {
                const slider = document.querySelector('input[type="range"]');
                if (slider) {
                    slider.value = "0.25";
                    slider.dispatchEvent(new Event('input', { bubbles: true }));
                    slider.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""")
            await asyncio.sleep(0.5)

            # Start continuous monitoring
            print("  Starting continuous monitoring replay...")
            await page.click('button:has-text("Start Continuous Monitoring")')

            # Explicitly wait until buffer reaches 512/512 AND engine state becomes ACTIVE with ~16.5 Hz spectral peak
            print("  Waiting for engine state ACTIVE (512 / 512 samples) and ~16.5 Hz spectral peak...")
            found_active = False
            state_text = ""
            dom_text = ""
            for sec in range(50):
                await asyncio.sleep(0.5)
                state_el = await page.query_selector('span:has-text("ENGINE STATE:")')
                state_text = await state_el.inner_text() if state_el else ""
                sample_el = await page.query_selector('span:has-text("Spectral Window Buffer")')
                sample_text = await sample_el.inner_text() if sample_el else ""
                dom_el = await page.query_selector('[data-testid="live-x-dominant-freq"]')
                dom_text = await dom_el.inner_text() if dom_el else ""

                if sec % 2 == 0:
                    print(f"    [t={sec*0.5:.1f}s] {state_text} | {dom_text} | {sample_text}")

                if "ACTIVE" in state_text and ("16." in dom_text or "17." in dom_text):
                    found_active = True
                    break

            assert found_active, f"Mode B did not reach ACTIVE with ~16.5 Hz peak. Last: {state_text}, {dom_text}"
            await asyncio.sleep(1.0)

            # Capture active monitor full page screenshot
            await page.evaluate("() => window.scrollTo(0, 0)")
            shot1 = str(screenshots_dir / "01_live_monitor_active.png")
            await page.screenshot(path=shot1, full_page=True)
            print(f"  Saved screenshot: {shot1}")

            # Stop and capture report modal screenshot (viewport centered)
            print("  Stopping replay session...")
            await page.wait_for_selector('[data-testid="btn-stop-session"]', timeout=10000)
            await page.locator('[data-testid="btn-stop-session"]').click()
            await page.wait_for_selector('h2:has-text("INSPECTION RUN REPORT")', timeout=10000)
            await asyncio.sleep(0.5)

            await page.evaluate("() => window.scrollTo(0, 0)")
            shot2 = str(screenshots_dir / "02_session_report_modal.png")
            await page.screenshot(path=shot2)
            print(f"  Saved screenshot: {shot2}")

            modal_text = await page.inner_text('div:has-text("INSPECTION RUN REPORT")')
            m_frames = re.search(r"FRAMES ANALYSED\s*([\d,]+)", modal_text)
            m_fps = re.search(r"MEASURED FPS\s*([\d.]+)\s*Hz", modal_text)
            frames_analysed = int(m_frames.group(1).replace(",", "")) if m_frames else 0
            measured_fps = float(m_fps.group(1)) if m_fps else 0.0
            print(f"  Mode B Report Modal: frames_analysed={frames_analysed}, measured_fps={measured_fps:.1f} Hz")
            assert frames_analysed >= 512, f"Expected frames_analysed >= 512, got {frames_analysed}"
            assert measured_fps == 500.0, f"Expected measured_fps == 500.0, got {measured_fps:.1f}"
            assert "explicit_fps_override" in modal_text, "Expected TIMEBASE SOURCE: explicit_fps_override"
            assert "N/A (Synthesized)" in modal_text or "ASSUMED_UNIFORM" in modal_text, "Expected Jitter: N/A (Synthesized)"
            assert "VALID" in modal_text, "Expected X-axis status VALID"
            await page.click('button:has-text("Close Report")')
            await asyncio.sleep(0.5)

            # ==============================================================
            # TEST C: Batch Inspect View
            # ==============================================================
            print("\n=== [5/6] Testing Batch Inspect View ===")
            await page.click('button:has-text("Batch Inspect")')
            await page.wait_for_selector('h2:has-text("OFFLINE VIDEO BATCH & BENCHMARK INSPECTOR")', timeout=5000)
            await asyncio.sleep(1.0)

            # Assert batch preview image is rendered with natural dimensions
            batch_preview_rendered = await page.evaluate("""() => {
                const img = document.querySelector('img[alt="Preview Frame 0"]');
                return !!(img && img.naturalWidth > 0 && img.offsetWidth > 200 && img.offsetHeight > 150);
            }""")
            print(f"  Batch inspect preview frame 0 image rendered and sized: {batch_preview_rendered}")
            assert batch_preview_rendered, "Batch inspect preview frame 0 <img> is not rendered or sized properly"

            # Select portable_baseline and run offline inspection
            print("  Executing offline video analysis on portable_baseline...")
            await page.click('button:has-text("Run Offline Inspection Analysis")')
            await page.wait_for_selector('span:has-text("INSPECTION SUMMARY")', timeout=20000)
            await asyncio.sleep(1.0)

            await page.evaluate("() => window.scrollTo(0, 0)")
            shot3 = str(screenshots_dir / "03_batch_inspect.png")
            await page.screenshot(path=shot3, full_page=True)
            print(f"  Saved screenshot: {shot3}")

            # ==============================================================
            # TEST D: Assets & History View
            # ==============================================================
            print("\n=== [6/6] Testing Assets & History View & Inspector ===")
            await page.click('button:has-text("Assets & History")')
            await page.wait_for_selector('h2:has-text("MACHINE ASSETS & STATISTICAL BASELINES")', timeout=5000)
            await asyncio.sleep(1.0)

            # Verify runs table contains non-blank Mode and formatted Hz values
            await page.wait_for_selector('[data-testid="run-row"]', timeout=8000)
            first_mode = await page.evaluate("""() => {
                const row = document.querySelector('tr[data-testid="run-row"]');
                if (!row) return "";
                const cells = Array.from(row.querySelectorAll('td'));
                return cells[1] ? cells[1].innerText.trim() : "";
            }""")
            print(f"  History table first row mode badge: '{first_mode}'")
            assert first_mode in ("LIVE", "BATCH"), f"Expected Mode to be 'LIVE' or 'BATCH', got '{first_mode}'"

            table_has_hz = await page.evaluate("""() => {
                const rows = Array.from(document.querySelectorAll('tr[data-testid="run-row"]'));
                if (rows.length === 0) return false;
                return rows.some(r => /\\d+\\.\\d{2}\\s*Hz/.test(r.innerText));
            }""")
            print(f"  History table contains formatted Hz values: {table_has_hz}")
            assert table_has_hz, "History table does not contain formatted Hz values"

            # Click first row in history table to open inspector
            print("  Opening run inspector drawer from history table...")
            first_row = page.locator('[data-testid="run-row"]').first
            await first_row.click()
            await page.wait_for_selector('span:has-text("INSPECTOR: RUN")', timeout=8000)
            await asyncio.sleep(1.0)

            await page.evaluate("() => window.scrollTo(0, 0)")
            shot4 = str(screenshots_dir / "04_assets_history.png")
            await page.screenshot(path=shot4, full_page=True)
            print(f"  Saved screenshot: {shot4}")

            # ==============================================================
            # TEST E: Optical Target Calibration Page (/target) & iOS Theater Mode
            # ==============================================================
            print("\n=== [7/8] Testing Optical Bench Test Target (/target) & iOS Fullscreen ===")
            await page.goto("http://127.0.0.1:3000/target")
            await page.wait_for_selector('h1:has-text("PHASESIGHT OPTICAL BENCH TEST TARGET")', timeout=8000)
            await asyncio.sleep(0.5)

            initial_badge = (await page.locator('[data-testid="target-freq-badge"]').inner_text()).strip()
            print(f"  Initial /target badge: '{initial_badge}'")
            assert initial_badge == "4.00 Hz", f"Expected initial badge '4.00 Hz', got '{initial_badge}'"

            # Verify dark-ground anti-overexposure pattern contrast & no pure white clipping at Med 70%
            pattern_stats = await page.evaluate("""() => {
                const c = document.querySelector('[data-testid="anchor-speckle-canvas"]');
                if (!c) return null;
                const data = c.getContext("2d").getImageData(20, 20, 280, 280).data;
                let sum = 0, sumSq = 0, maxLum = 0, minLum = 255;
                const n = data.length / 4;
                for (let i = 0; i < data.length; i += 4) {
                    const lum = 0.299 * data[i] + 0.587 * data[i+1] + 0.114 * data[i+2];
                    sum += lum;
                    sumSq += lum * lum;
                    if (lum > maxLum) maxLum = lum;
                    if (lum < minLum) minLum = lum;
                }
                const mean = sum / n;
                const std = Math.sqrt(Math.max(0, sumSq / n - mean * mean));
                return { mean, std, minLum, maxLum };
            }""")
            print(f"  /target anti-overexposure pattern stats (Med 70%): {pattern_stats}")
            assert pattern_stats is not None, "Anchor canvas missing"
            assert pattern_stats["std"] >= 30.0, f"Expected pattern std >= 30, got {pattern_stats['std']}"
            assert pattern_stats["maxLum"] < 210, f"Expected anti-overexposure maxLum < 210, got {pattern_stats['maxLum']}"

            shot5 = str(screenshots_dir / "05_optical_target.png")
            await page.screenshot(path=shot5, full_page=True)
            print(f"  Saved screenshot: {shot5}")

            # Click 7.5 Hz & 20 px & verify live state + real canvas translation over 250ms
            await page.locator('button:has-text("7.5 Hz")').click()
            await page.locator('button:has-text("20 px")').click()
            await asyncio.sleep(0.1)
            updated_badge = (await page.locator('[data-testid="target-freq-badge"]').inner_text()).strip()
            updated_label = (await page.locator('[data-testid="vibrating-target-label"]').inner_text()).strip()
            updated_summary = (await page.locator('[data-testid="target-motion-summary"]').inner_text()).strip()
            print(f"  After 7.5 Hz + 20 px click -> badge='{updated_badge}', label='{updated_label}', summary='{updated_summary}'")
            assert updated_badge == "7.50 Hz", f"Expected badge '7.50 Hz', got '{updated_badge}'"
            assert "7.5 Hz" in updated_label, f"Expected '7.5 Hz' in label, got '{updated_label}'"
            assert "±20 px" in updated_summary, f"Expected '±20 px' in summary, got '{updated_summary}'"

            # Sample canvas pixel buffer before & after 250ms to verify physical translation (and static anchor)
            snap_t0 = await page.evaluate("""() => {
                const tgt = document.querySelector('[data-testid="target-speckle-canvas"]');
                const anc = document.querySelector('[data-testid="anchor-speckle-canvas"]');
                return {
                    tgt: Array.from(tgt.getContext("2d").getImageData(40, 40, 200, 100).data),
                    anc: Array.from(anc.getContext("2d").getImageData(40, 40, 200, 100).data),
                };
            }""")
            await asyncio.sleep(0.25)
            snap_t1 = await page.evaluate("""() => {
                const tgt = document.querySelector('[data-testid="target-speckle-canvas"]');
                const anc = document.querySelector('[data-testid="anchor-speckle-canvas"]');
                return {
                    tgt: Array.from(tgt.getContext("2d").getImageData(40, 40, 200, 100).data),
                    anc: Array.from(anc.getContext("2d").getImageData(40, 40, 200, 100).data),
                };
            }""")
            tgt_diff = sum(abs(a - b) for a, b in zip(snap_t0["tgt"], snap_t1["tgt"]))
            anc_diff = sum(abs(a - b) for a, b in zip(snap_t0["anc"], snap_t1["anc"]))
            print(f"  Canvas motion over 250ms: target_abs_diff={tgt_diff}, anchor_abs_diff={anc_diff}")
            assert tgt_diff > 5000, f"Expected vibrating target canvas to translate over 250ms, got diff={tgt_diff}"
            assert anc_diff == 0, f"Expected static anchor canvas diff == 0, got {anc_diff}"

            # Test Brightness toggle & Axis toggle responsiveness
            await page.locator('[data-testid="btn-brightness-low"]').click()
            assert await page.locator('[data-testid="btn-brightness-low"]').get_attribute("aria-pressed") == "true"
            await page.locator('[data-testid="btn-axis-vertical"]').click()
            axis_txt = await page.locator('[data-testid="target-motion-summary"]').inner_text()
            assert "vertical" in axis_txt, f"Expected 'vertical' axis summary, got '{axis_txt}'"
            await page.locator('[data-testid="btn-axis-horizontal"]').click()
            await page.locator('[data-testid="btn-brightness-med"]').click()

            # Verify mobile landscape (844x390) with native requestFullscreen rejected (iOS Safari simulation)
            await page.set_viewport_size({"width": 844, "height": 390})
            await page.evaluate("""() => {
                document.documentElement.requestFullscreen = () =>
                    Promise.reject(new Error("requestFullscreen unavailable on iOS Safari"));
            }""")
            await page.locator('[data-testid="btn-fullscreen-target"]').click()
            await page.wait_for_selector('[data-testid="target-fullscreen-overlay"]', timeout=5000)
            await asyncio.sleep(0.3)

            fs_check = await page.evaluate("""() => {
                const overlay = document.querySelector('[data-testid="target-fullscreen-overlay"]');
                const anc = document.querySelector('[data-testid="anchor-panel-box"]');
                const tgt = document.querySelector('[data-testid="target-panel-box"]');
                const ctrl = document.querySelector('[data-testid="fullscreen-bottom-controls"]');
                if (!overlay || !anc || !tgt || !ctrl) return null;
                const oRect = overlay.getBoundingClientRect();
                const aRect = anc.getBoundingClientRect();
                const tRect = tgt.getBoundingClientRect();
                const cRect = ctrl.getBoundingClientRect();
                const cs = window.getComputedStyle(overlay);
                return {
                    position: cs.position,
                    overlayW: oRect.width,
                    overlayH: oRect.height,
                    anchorSizeDiff: Math.abs(aRect.width - aRect.height),
                    targetSizeDiff: Math.abs(tRect.width - tRect.height),
                    anchorW: aRect.width,
                    targetW: tRect.width,
                    sideBySide: tRect.left > aRect.left + aRect.width * 0.5,
                    fitsInViewport: cRect.bottom <= 391 && aRect.bottom <= cRect.top + 4,
                };
            }""")
            print(f"  iOS Safari Mobile Landscape Fullscreen telemetry: {fs_check}")
            assert fs_check is not None, "Fullscreen overlay DOM nodes missing"
            assert fs_check["position"] == "fixed", f"Expected fixed position, got {fs_check['position']}"
            assert fs_check["overlayW"] >= 840 and fs_check["overlayH"] >= 385, "Overlay did not fill 844x390"
            assert fs_check["sideBySide"], "Target & Anchor panels were not laid out side-by-side"
            assert fs_check["anchorSizeDiff"] <= 2.5 and fs_check["targetSizeDiff"] <= 2.5, "Panels were not square"
            assert fs_check["fitsInViewport"], "Bottom controls or panels overflowed 390px landscape height"

            await page.locator('[data-testid="btn-exit-fullscreen"]').click()
            await page.wait_for_selector('h1:has-text("PHASESIGHT OPTICAL BENCH TEST TARGET")', timeout=5000)
            await page.set_viewport_size({"width": 1440, "height": 900})

            # ==============================================================
            # TEST F: Live Baseline REVIEW + Raw Shake + History Spectrum Overlay
            # ==============================================================
            print("\n=== [8/8] Testing Live Baseline REVIEW, Raw Shake & History Overlay ===")
            # Create demo_bench asset, run 3 baseline calibrations & build baseline via API
            asset_req = urllib.request.Request(
                "http://127.0.0.1:8000/api/v1/assets",
                data=json.dumps({
                    "asset_id": "demo_bench",
                    "name": "Demo Bench Unit",
                    "nominal_rpm": 510.0,
                    "expected_fps": 60.0,
                    "default_target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                    "default_anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(asset_req, timeout=10) as resp:
                assert resp.status in (200, 201)

            cal_run_ids = []
            for idx in range(3):
                run_req = urllib.request.Request(
                    "http://127.0.0.1:8000/api/v1/runs/analyze",
                    data=json.dumps({
                        "preset_id": "portable_baseline",
                        "target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
                        "anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
                        "asset_id": "demo_bench",
                        "nperseg": 256,
                    }).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(run_req, timeout=30) as resp:
                    cal_run_ids.append(json.loads(resp.read().decode())["run_id"])
            print(f"  Created demo_bench & 3 calibration runs: {cal_run_ids}")

            bsl_req = urllib.request.Request(
                "http://127.0.0.1:8000/api/v1/baselines/build",
                data=json.dumps({
                    "asset_id": "demo_bench",
                    "run_ids": cal_run_ids,
                    "require_valid_axes": ["x"],
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(bsl_req, timeout=10) as resp:
                bsl_res = json.loads(resp.read().decode())
                print(f"  Built demo_bench baseline: {bsl_res.get('baseline_id')}")

            # Reload workstation and select demo_bench
            await page.goto("http://127.0.0.1:3000", wait_until="domcontentloaded")
            await page.wait_for_selector('[data-testid="select-active-asset"]', timeout=10000)
            await page.wait_for_function(
                """() => {
                    const sel = document.querySelector('[data-testid="select-active-asset"]');
                    return sel && Array.from(sel.options).some(o => o.value === 'demo_bench');
                }""",
                timeout=10000,
            )
            await page.select_option('[data-testid="select-active-asset"]', 'demo_bench')
            await page.locator('[data-testid="mode-video-replay"]').click()
            await page.select_option('[data-testid="select-video-preset"]', 'portable_changed')
            await page.wait_for_selector('img[alt="Preview Frame 0"]', timeout=8000)
            await page.wait_for_selector('[data-testid="live-baseline-screening-card"]:has-text("Baseline Armed:")', timeout=8000)
            await asyncio.sleep(0.8)

            print("  Starting continuous monitoring on portable_changed against demo_bench baseline...")
            await page.locator('[data-testid="btn-start-session"]').click()
            await page.locator('button:has-text("Raw Shake")').click()

            review_verified = False
            start_wait = time.time()
            while time.time() - start_wait < 25.0:
                await asyncio.sleep(0.8)
                state_el = await page.query_selector('span:has-text("ENGINE STATE:")')
                state_txt = await state_el.inner_text() if state_el else ""
                bsl_el = await page.query_selector('[data-testid="live-baseline-screening-card"]')
                bsl_txt = await bsl_el.inner_text() if bsl_el else ""
                shake_el = await page.query_selector('[data-testid="shake-cancellation-pill"]')
                shake_txt = await shake_el.inner_text() if shake_el else ""
                if (
                    "ACTIVE" in state_txt
                    and "REVIEW" in bsl_txt
                    and "Max |z|" in bsl_txt
                    and "Raw Tgt RMS:" in shake_txt
                    and "Differential RMS:" in shake_txt
                ):
                    review_verified = True
                    print(f"  Verified Live Baseline REVIEW card + Raw Shake pill: {shake_txt.strip()}")
                    break

            assert review_verified, "Live session did not reach ACTIVE + REVIEW + Raw Shake pill within 25s"

            # Verify Baseline reference line is rendered on live Welch PSD SVG
            has_bsl_line = await page.is_visible('svg text:has-text("BASELINE 8.5")')
            print(f"  Live SpectrumPlot BASELINE reference marker visible: {has_bsl_line}")
            assert has_bsl_line, "Expected BASELINE reference marker on live SpectrumPlot"

            await page.evaluate("() => window.scrollTo(0, 0)")
            shot6 = str(screenshots_dir / "06_live_baseline_review.png")
            await page.screenshot(path=shot6, full_page=True)
            print(f"  Saved screenshot: {shot6}")

            # Stop session & verify Export Report JSON button
            await page.locator('[data-testid="btn-stop-session"]').click()
            await page.wait_for_selector('h2:has-text("INSPECTION RUN REPORT")', timeout=10000)
            export_btn_visible = await page.is_visible('[data-testid="btn-export-report-json"]')
            assert export_btn_visible, "Export Report JSON button missing in SessionReportModal"
            await page.click('button:has-text("Close Report")')

            # Verify History Spectrum Overlay comparison on demo_bench REVIEW run
            await page.click('button:has-text("Assets & History")')
            await page.wait_for_selector('[data-testid="run-row"]', timeout=8000)
            await asyncio.sleep(0.6)
            await page.locator('[data-testid="run-row"]').first.click()
            await page.wait_for_selector('[data-testid="select-overlay-run"]', timeout=8000)
            await page.wait_for_selector('[data-testid="spectrum-overlay-path"]', timeout=8000)
            overlay_chip = await page.inner_text('[data-testid="spectrum-overlay-chip"]')
            print(f"  Verified History Spectrum Overlay comparison: '{overlay_chip.strip()}'")

            await browser.close()

        # ==============================================================
        # ASSERTIONS
        # ==============================================================
        print("\n=== Verifying browser errors and API responses ===")
        print(f"Total uncaught page errors: {len(page_errors)}")
        print(f"Total console error logs: {len(console_errors)}")
        print(f"Total HTTP 500 responses: {len(http_500_errors)}")

        if page_errors:
            print("PAGE ERRORS:")
            for e in page_errors:
                print("  -", e)

        if http_500_errors:
            print("HTTP 500 ERRORS:")
            for e in http_500_errors:
                print("  -", e)

        assert len(page_errors) == 0, f"Expected 0 page errors, got {len(page_errors)}"
        assert len(http_500_errors) == 0, f"Expected 0 HTTP 500 errors, got {len(http_500_errors)}"
        print("\nALL BROWSER UI WORKFLOWS AND USERMEDIA STREAMING VERIFIED CLEANLY!")

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

        if os.path.exists("tmp_baseline.y4m"):
            try:
                os.remove("tmp_baseline.y4m")
                print("Cleaned up tmp_baseline.y4m")
            except Exception as e:
                print("Warning: could not clean up tmp_baseline.y4m:", e)

        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
            print(f"Cleaned up isolated temporary storage: {temp_dir}")
        print("Browser UI verification finished.")


if __name__ == "__main__":
    asyncio.run(run_browser_verification())
