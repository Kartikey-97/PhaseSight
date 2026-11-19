---
phase: 06-live-webcam
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - phasesight/capture.py
  - phasesight/cli.py
  - phasesight/app.py
  - phasesight/ui_helpers.py
  - tests/test_capture.py
  - tests/test_ui.py
autonomous: true
requirements:
  - CAP-01
  - CAP-02
  - CAP-03
  - CAP-04
  - CAP-05
  - CAP-06

estimate:
  tokens: 48000
  raw_tokens: 24000
  tasks: 3
  confidence: high

must_haves:
  truths:
    - "CaptureStabilityReport dataclass accurately encapsulates total frames, duration, nominal FPS, measured FPS, median/mean/std dt, standard jitter ratio, robust MAD jitter ratio, dropped frame counts, drop indices, large gap counts, stability status (STABLE, WARNING_JITTER, REJECTED_UNSTABLE), and diagnostic reasons per CAP-03 and CAP-04."
    - "calculate_timestamp_stability (and evaluate_timing_stability alias) computes empirical sampling frequency 1.0 / median(dt), detects dropped frame gaps (> 1.5x median dt), flags severe stalls (> 2.5x median dt), and classifies captures into STABLE, WARNING_JITTER, or REJECTED_UNSTABLE per CAP-03 and CAP-04."
    - "MockVideoCapture duck-types cv2.VideoCapture with isOpened, read, get, set, and release, supporting deterministic synthetic vibration frames with configurable FPS, injected jitter, and simulated frame drops per CAP-06."
    - "open_capture_source seamlessly handles integer camera indices, numeric strings, file paths, and 'mock:index' virtual sources with proper error messaging for macOS TCC camera permission denials per CAP-01."
    - "grab_preview_frame flushes OS driver buffer lag (reading 2 warmup frames) and retrieves a single fresh frame, safely releasing camera resources per CAP-01."
    - "capture_live_clip captures an N-second video buffer with monotonic time.perf_counter() timestamps, computes stability report, optionally encodes an MP4 container via cv2.VideoWriter, and returns CaptureResult per CAP-02."
    - "Streamlit workbench Tab 1 provides 'Live Webcam Stream' input mode with camera source input (supporting mock:0), duration controls (3-20s), 'Grab Preview Frame' with ROI overlay and texture check, 'Record Live Capture' with progress bar, Frame-Rate Stability Card, quality gating, and automatic handoff to analyse_video per CAP-05."
    - "phasesight capture CLI subcommand captures video from live cameras or mock sources, outputs constant-frame-rate MP4, and prints timing stability diagnostics per CAP-01, CAP-02, and CAP-03."
    - "Automated test suite in tests/test_capture.py and headless AppTest tests in tests/test_ui.py provide 100% test coverage for stability metrics, mock capture, dropped frames, and UI workflows per CAP-01 through CAP-06."
  artifacts:
    - phasesight/capture.py
    - phasesight/cli.py
    - phasesight/app.py
    - phasesight/ui_helpers.py
    - tests/test_capture.py
    - tests/test_ui.py
  key_links:
    - "phasesight/capture.py imports make_scene and SyntheticConfig from phasesight/synthetic.py for MockVideoCapture frame generation"
    - "phasesight/app.py imports open_capture_source, grab_preview_frame, capture_live_clip, CaptureResult, and CaptureStabilityReport from phasesight/capture.py"
    - "phasesight/app.py hands off valid captured MP4 with fps_override=result.stability.measured_fps to analyse_video in phasesight/video.py"
    - "phasesight/cli.py imports capture_live_clip from phasesight/capture.py for the 'capture' subcommand"
    - "tests/test_ui.py tests the 'Live Webcam Stream' mode using 'mock:0' source via streamlit.testing.v1.AppTest"
---

<objective>
Implement Phase 6: Live Webcam Stream & Dropped Frame Handling for PhaseSight. Transition the toolkit from offline-only video file processing into a real-time live screening instrument. Implement the unified camera capture engine in `phasesight/capture.py` supporting live hardware indices, video file paths, and deterministic virtual streams (`MockVideoCapture`); capture fixed-duration recording buffers with high-precision monotonic timestamps (`time.perf_counter()`); quantify timestamp regularity, empirical sampling rates ($f_s = 1.0 / \text{median}(\Delta t)$), and jitter ratios ($\text{std}(\Delta t) / \text{median}(\Delta t)$); detect dropped frames and severe stalls; classify capture stability (`STABLE`, `WARNING_JITTER`, `REJECTED_UNSTABLE`); integrate live camera controls, preview snapshot with ROI validation, and the Frame-Rate Stability Card into the Streamlit operator workbench (`phasesight/app.py`); add the `phasesight capture` CLI subcommand (`phasesight/cli.py`); and provide a comprehensive automated test suite in `tests/test_capture.py` and `tests/test_ui.py`.

Purpose: Enable operators to perform on-machine vibration screening directly from live camera streams while rigorously verifying frame-rate stability and preventing frequency estimation errors and spectral distortion caused by webcam auto-exposure throttling and dropped frames.
Output: New module `phasesight/capture.py`, updated `phasesight/cli.py`, updated `phasesight/app.py`, updated `phasesight/ui_helpers.py`, new test suite `tests/test_capture.py`, and updated `tests/test_ui.py`.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/06-live-webcam/06-RESEARCH.md
@phasesight/analysis.py
@phasesight/video.py
@phasesight/synthetic.py
@phasesight/tracker.py
@phasesight/storage.py
@phasesight/app.py
@phasesight/ui_helpers.py
@phasesight/cli.py
@tests/test_ui.py
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Core Live Capture Engine, Stability Quantification, and MockVideoCapture Tracer</name>
  <files>phasesight/capture.py, tests/test_capture.py</files>
  <action>
Implement the end-to-end capture engine, monotonic timing analysis, and deterministic mock stream per CAP-01, CAP-02, CAP-03, CAP-04, and CAP-06.

1. In `phasesight/capture.py`:
   - Define dataclass `CaptureStabilityReport`:
     - `total_frames: int`
     - `duration_s: float`
     - `nominal_fps: float`
     - `measured_fps: float`
     - `median_dt_s: float`
     - `mean_dt_s: float`
     - `std_dt_s: float`
     - `min_dt_s: float`
     - `max_dt_s: float`
     - `jitter_ratio: float` (std_dt / median_dt)
     - `robust_jitter_ratio: float` (1.4826 * MAD(dt) / median_dt)
     - `dropped_frames_count: int`
     - `dropped_frame_indices: list[int] = field(default_factory=list)`
     - `large_gap_count: int = 0` (count of dt > 2.5 * median_dt)
     - `status: str = "STABLE"` (one of 'STABLE', 'WARNING_JITTER', 'REJECTED_UNSTABLE')
     - `status_reasons: list[str] = field(default_factory=list)`
   - Define dataclass `CaptureResult`:
     - `frames: np.ndarray` (shape (N, H, W, C) uint8)
     - `timestamps_s: np.ndarray` (1D float64)
     - `stability: CaptureStabilityReport`
     - `video_path: Path | None = None`
   - Implement `calculate_timestamp_stability(timestamps_s: np.ndarray | list[float], nominal_fps: float = 30.0, *, warning_jitter_threshold: float = 0.05, reject_jitter_threshold: float = 0.15, max_tolerated_dropped_frames: int = 3) -> CaptureStabilityReport`:
     - Provide alias `evaluate_timing_stability = calculate_timestamp_stability`.
     - Convert timestamps to float64 1D array.
     - If `len(t) < 32`: return `REJECTED_UNSTABLE` with reason: 'Too few frames captured: minimum 32 frames required for spectral analysis.'
     - Compute inter-frame intervals `dt = np.diff(t)`.
     - If `np.any(dt <= 0)`: return `REJECTED_UNSTABLE` with reason: 'Non-monotonic timestamps detected: frame timestamps must be strictly increasing.'
     - Compute `median_dt = float(np.median(dt))`, `mean_dt = float(np.mean(dt))`, `std_dt = float(np.std(dt))`.
     - Calculate `measured_fps = 1.0 / median_dt if median_dt > 0 else 0.0`.
     - Calculate `jitter_ratio = std_dt / median_dt if median_dt > 0 else 0.0`.
     - Calculate `robust_jitter_ratio = (1.4826 * float(np.median(np.abs(dt - median_dt)))) / median_dt if median_dt > 0 else 0.0`.
     - Dropped frame detection: compute `drop_ratios = dt / median_dt`. For each interval, estimated dropped frames is `np.maximum(0, np.round(drop_ratios).astype(int) - 1)`. Total `dropped_frames_count = int(np.sum(drops_per_interval))`, and record indices where drops occurred.
     - Severe stalls: count intervals where `dt > 2.5 * median_dt`.
     - Stability classification logic:
       - If `dropped_frames_count > max_tolerated_dropped_frames` (more than 3 drops) or `large_gap_count > 0` (any stall > 2.5x median dt) or `jitter_ratio >= reject_jitter_threshold` (jitter >= 15%):
         `status = "REJECTED_UNSTABLE"`, add detailed rejection reasons.
       - Else if `jitter_ratio >= warning_jitter_threshold` (jitter >= 5%) or `dropped_frames_count > 0`:
         `status = "WARNING_JITTER"`, add warning reasons.
       - Else:
         `status = "STABLE"`.
     - Return populated `CaptureStabilityReport`.
   - Implement `MockVideoCapture`:
     - Duck-typed OpenCV `VideoCapture` object.
     - `__init__(self, frames: np.ndarray | None = None, fps: float = 30.0, drop_indices: set[int] | None = None, jitter_ms: float = 0.0, seed: int = 42, num_synthetic_frames: int = 150, width: int = 640, height: int = 360)`:
       - If `frames is None`: synthesize realistic vibrating scene frames using `phasesight.synthetic.make_scene(SyntheticConfig(num_frames=num_synthetic_frames, fps=int(fps), width=width, height=height, frequency_hz=8.5, target_amplitude_px=0.35, seed=seed))`.
       - Validate `frames.ndim == 4` (N, H, W, C).
       - Maintain `self.index = 0` and `self.opened = True`.
     - `isOpened(self) -> bool`: return `self.opened`.
     - `read(self) -> tuple[bool, np.ndarray | None]`:
       - If not opened or index >= len(frames): return `False, None`.
       - If `self.index in self.drop_indices`: advance index and simulate dropped frame.
       - Retrieve `frame = self.frames[self.index].copy()`, advance index, return `True, frame`.
     - `get(self, prop: int) -> float`: handle `cv2.CAP_PROP_FRAME_WIDTH`, `cv2.CAP_PROP_FRAME_HEIGHT`, `cv2.CAP_PROP_FPS`, `cv2.CAP_PROP_FRAME_COUNT`, and `cv2.CAP_PROP_POS_FRAMES`.
     - `set(self, prop: int, val: float) -> bool`: return True.
     - `release(self) -> None`: set `self.opened = False`.
   - Implement `open_capture_source(source: int | str | Path | Any, fps: float = 30.0) -> cv2.VideoCapture | MockVideoCapture`:
     - If string starts with "mock" (e.g. 'mock', 'mock:0', 'mock:1'): instantiate and return `MockVideoCapture(fps=fps)`.
     - If integer or numeric string: open `cv2.VideoCapture(int(source))`.
     - Else: open `cv2.VideoCapture(str(source))`.
     - Guard: `if not cap.isOpened(): raise RuntimeError(f"Could not open video capture source: {source}. If on macOS, verify Camera permission in System Settings -> Privacy & Security -> Camera.")`.
   - Implement `grab_preview_frame(source: int | str | Path | Any, warmup_frames: int = 2) -> np.ndarray`:
     - Open source using `open_capture_source`.
     - In `try...finally: cap.release()`: read `warmup_frames` frames to flush OS driver ring-buffer lag, then read single preview frame. If read fails, raise `RuntimeError`. Return BGR `np.ndarray`.
   - Implement `capture_live_clip(source: int | str | Path | Any, duration_s: float = 5.0, target_fps: float | None = 30.0, output_path: str | Path | None = None, progress_callback: Callable[[float], None] | None = None, stop_event: threading.Event | None = None) -> CaptureResult`:
     - Open source via `open_capture_source(source, fps=target_fps or 30.0)`.
     - Set requested FPS on capture device if supported.
     - In `try...finally: cap.release()`:
       - Read initial frame, record `t0 = time.perf_counter()`.
       - Buffer initial frame and timestamp 0.0.
       - Loop while `(stop_event is None or not stop_event.is_set()) and (time.perf_counter() - t0 < duration_s)`:
         - Read frame, record arrival timestamp `t_now = time.perf_counter() - t0`.
         - Append frame and timestamp.
         - If `progress_callback` is provided, call with `min(1.0, (time.perf_counter() - t0) / duration_s)`.
     - Compute `stability = calculate_timestamp_stability(timestamps_s, nominal_fps=target_fps or 30.0)`.
     - If `output_path` is specified and frames were captured:
       - Ensure parent directory exists.
       - Determine container writing FPS: use `stability.measured_fps` if > 0 else (target_fps or 30.0).
       - Create `cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), float(fps_to_write), (w, h))`.
       - In `try...finally: writer.release()`: write all buffered frames.
     - Return `CaptureResult(frames=frame_array, timestamps_s=t_arr, stability=stability, video_path=Path(output_path) if output_path else None)`.

2. In `tests/test_capture.py`:
   - Create initial test suite verifying:
     - `test_stability_report_stable`: uniform timestamps with dt=1/30 produce STABLE status, jitter < 1%, 0 drops.
     - `test_stability_report_too_few_frames`: array with <32 elements returns REJECTED_UNSTABLE.
     - `test_stability_report_non_monotonic`: non-strictly-increasing timestamps return REJECTED_UNSTABLE.
     - `test_mock_video_capture_duck_typing`: verify isOpened, read, get, and release behavior.
     - `test_open_capture_source`: verify opening 'mock:0' and real video file.
     - `test_grab_preview_frame`: verify shape (H, W, 3) and uint8 dtype from mock source.
     - `test_capture_live_clip`: verify capturing 1.0s clip from 'mock:0', writing MP4, and validating CaptureResult fields and measured FPS.
  </action>
  <verify>
    <automated>./.venv/bin/pytest tests/test_capture.py -v</automated>
  </verify>
  <done>
CaptureStabilityReport, calculate_timestamp_stability, MockVideoCapture, open_capture_source, grab_preview_frame, and capture_live_clip are fully implemented in phasesight/capture.py and pass all automated unit tests in tests/test_capture.py.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: CLI Subcommand `phasesight capture` and Comprehensive Jitter / Dropped-Frame Test Suite</name>
  <files>phasesight/cli.py, tests/test_capture.py</files>
  <behavior>
    - Test 1: calculate_timestamp_stability detects moderate jitter (5% to 15%) and flags WARNING_JITTER.
    - Test 2: calculate_timestamp_stability detects severe jitter (>= 15%) and flags REJECTED_UNSTABLE.
    - Test 3: calculate_timestamp_stability detects 1 to 3 dropped frames and flags WARNING_JITTER with accurate dropped frame indices and counts.
    - Test 4: calculate_timestamp_stability detects > 3 dropped frames and flags REJECTED_UNSTABLE.
    - Test 5: calculate_timestamp_stability detects severe stalls (> 2.5x median dt) and flags REJECTED_UNSTABLE.
    - Test 6: MockVideoCapture with drop_indices simulates dropped frames correctly.
    - Test 7: CLI subcommand `phasesight capture mock:0 --duration 1.0` records clip, outputs MP4, prints diagnostic table with measured FPS and stability badge, and exports JSON report if requested.
    - Test 8: capture_live_clip respects threading.Event cancellation token.
  </behavior>
  <action>
Implement CLI capture command and expand unit test matrix per CAP-01, CAP-02, CAP-03, and CAP-04.

1. In `phasesight/cli.py`:
   - Import `capture_live_clip`, `calculate_timestamp_stability`, and `CaptureStabilityReport` from `.capture`.
   - Add `capture` subparser to `_build_parser()`:
     - Positional argument `source`: default `"0"`, help "Camera index (e.g. 0), video file path, or 'mock:0'".
     - `--duration`: float, default `5.0`, help "Capture duration in seconds (1.0 to 30.0)".
     - `--fps`: float, default `30.0`, help "Requested nominal frame rate".
     - `--out`: Path, default `None`, help "Output MP4 video file path (default: output/webcam_captures/capture_<timestamp>.mp4)".
     - `--json`: Path, default `None`, help "Output JSON path for CaptureStabilityReport".
     - `--warmup`: int, default `2`, help "Warmup frames to flush driver buffer".
   - Implement handler for `args.command == "capture"`:
     - Validate duration ($1.0 \le \text{duration} \le 30.0$).
     - If `--out` is not specified, construct default path `Path("output/webcam_captures") / f"capture_{datetime.now():%Y%m%d_%H%M%S}.mp4"`.
     - Sanitize output file name to prevent directory traversal.
     - Print start notification: `Capturing {duration}s from source '{source}' at target {fps} FPS...`.
     - Execute `result = capture_live_clip(source=args.source, duration_s=args.duration, target_fps=args.fps, output_path=output_file)`.
     - Print structured console diagnostics:
       - Header: PhaseSight Live Capture Stability Report
       - Container: output MP4 file path, frame dimensions, total frames buffered
       - Timing: Nominal FPS, Measured Empirical FPS ($1.0/\text{median}(\Delta t)$), Duration
       - Regularity: Jitter Ratio (`std(dt)/median(dt)`), Robust MAD Jitter Ratio
       - Integrity: Dropped frame count, Dropped frame indices, Large stall count
       - Verdict Badge: `[🟢 STABLE]`, `[🟡 WARNING_JITTER]`, or `[🔴 REJECTED_UNSTABLE]`
       - If status reasons exist, print each reason bullet.
     - If `--json` path is specified, serialize `dataclasses.asdict(result.stability)` with indentation to the JSON path.
     - Return exit code 0 on STABLE or WARNING_JITTER, and exit code 1 if REJECTED_UNSTABLE (or return structured status).
   - In `phasesight inspect` subcommand handler:
     - Check if `args.video` argument is a camera index (digit string) or starts with `"mock"`. If so, automatically capture a live clip to a temporary file first, notify operator, and proceed to inspection passing `fps_override=result.stability.measured_fps`.

2. In `tests/test_capture.py`:
   - Implement full test matrix for jitter and dropped frame quantification:
     - `test_timing_stability_warning_jitter`: inject synthetic jitter with 8% std/median, assert `status == "WARNING_JITTER"` and reasons mention moderate jitter.
     - `test_timing_stability_rejected_jitter`: inject synthetic jitter with 18% std/median, assert `status == "REJECTED_UNSTABLE"` and reasons mention severe jitter.
     - `test_timing_stability_single_and_multiple_drops`:
       - 2 dropped frame gaps: assert `dropped_frames_count == 2`, `status == "WARNING_JITTER"`.
       - 5 dropped frame gaps: assert `dropped_frames_count == 5`, `status == "REJECTED_UNSTABLE"`.
     - `test_timing_stability_severe_stalls`: inject gap of 3.0x median dt, assert `large_gap_count >= 1` and `status == "REJECTED_UNSTABLE"`.
     - `test_mock_video_capture_with_drop_simulation`: verify `MockVideoCapture(drop_indices={5, 10})` skips frames at specified indices.
     - `test_cli_capture_subcommand_mock_stdout_and_json(tmp_path)`: invoke CLI capture with `mock:0`, duration 1.0s, output to `tmp_path / "test.mp4"`, `--json` output, verify video file exists, JSON report exists and matches schema, and stdout includes stability metrics.
     - `test_capture_live_clip_cancellation`: start capture in thread with `stop_event`, set event after 0.2s, assert capture finishes before full duration and returns valid CaptureResult.
  </action>
  <verify>
    <automated>./.venv/bin/pytest tests/test_capture.py -v</automated>
  </verify>
  <done>
The `phasesight capture` CLI command is operational with diagnostic reporting and JSON export, and tests/test_capture.py comprehensively tests all jitter thresholds, dropped frame counts, stalls, and mock streams.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Streamlit Operator Workbench Live Webcam Mode, ROI Preview, Stability Card, and Headless UI Tests</name>
  <files>phasesight/app.py, phasesight/ui_helpers.py, tests/test_ui.py</files>
  <behavior>
    - Test 1: ui_helpers.stability_badge returns proper formatted badge for STABLE, WARNING_JITTER, REJECTED_UNSTABLE, and unknown.
    - Test 2: Streamlit Tab 1 renders "Live Webcam Stream" radio option alongside sample clips and upload.
    - Test 3: Selecting "Live Webcam Stream" renders camera controls (source input, duration slider, target FPS selectbox).
    - Test 4: Clicking "Grab Preview Frame" with source "mock:0" stores preview frame in session state and renders annotated frame with target/anchor ROIs and texture checks.
    - Test 5: Clicking "Record Live Capture" runs live capture, shows progress, saves MP4 to output/webcam_captures/, and renders the Frame-Rate Stability Card with status badge and metrics.
    - Test 6: When capture is REJECTED_UNSTABLE, an error alert with guidance is displayed and video analysis execution is blocked.
    - Test 7: When capture is STABLE or WARNING_JITTER, analysis executes with fps_override set to measured_fps, supporting 1-click auto-assessment and run saving.
  </behavior>
  <action>
Implement the Streamlit workbench webcam integration and headless AppTest test suite per CAP-01, CAP-02, CAP-03, CAP-04, and CAP-05.

1. In `phasesight/ui_helpers.py`:
   - Implement `stability_badge(status: str) -> str`:
     - Return `"🟢 STABLE"` for `"STABLE"`.
     - Return `"🟡 WARNING_JITTER"` for `"WARNING_JITTER"`.
     - Return `"🔴 REJECTED_UNSTABLE"` for `"REJECTED_UNSTABLE"`.
     - Return `"⚪ UNKNOWN"` for any other value.

2. In `phasesight/app.py`:
   - Import `open_capture_source`, `grab_preview_frame`, `capture_live_clip`, `CaptureStabilityReport`, and `CaptureResult` from `.capture`.
   - Import `stability_badge` from `.ui_helpers`.
   - Update `render_inspection_tab()`:
     - Update `source_mode` radio to include 3 options:
       `["Sample portable clips", "Upload video file", "Live Webcam Stream"]`
     - When `source_mode == "Live Webcam Stream"`:
       - Render camera configuration controls in 3 columns:
         - Column 1: `camera_source_str = st.text_input("Camera Source / Index:", value="0", help="Camera index integer (e.g. 0, 1), device path, or 'mock:0' for virtual test stream.", key="webcam_source_input")`
         - Column 2: `capture_duration_s = st.slider("Duration (seconds):", min_value=3.0, max_value=20.0, value=5.0, step=0.5, key="webcam_duration_input")`
         - Column 3: `requested_fps = st.selectbox("Target FPS:", options=[30, 60, 15], index=0, key="webcam_fps_input")`
       - Render Action Controls:
         - Col A: "📸 Grab Preview Frame" button:
           - On click: call `frame = grab_preview_frame(camera_source_str)`.
           - Store `st.session_state["webcam_preview_frame"] = frame`.
           - Display `st.success("Live preview frame acquired.")`.
         - Col B: "🔴 Record Live Capture" button:
           - On click:
             - Progress bar `prog = st.progress(0.0)`.
             - Status text `status_txt = st.empty()`.
             - Callback updates `prog.progress(pct)` and `status_txt.text(f"Recording... {pct*100:.0f}%")`.
             - Output file: `Path("output/webcam_captures") / f"webcam_{datetime.now():%Y%m%d_%H%M%S}.mp4"`.
             - Run `result = capture_live_clip(source=camera_source_str, duration_s=capture_duration_s, target_fps=float(requested_fps), output_path=output_file, progress_callback=cb)`.
             - Store `st.session_state["webcam_capture_result"] = result`.
             - If `result.stability.status != "REJECTED_UNSTABLE"`:
               set `video_path = result.video_path` in session state so downstream analysis pipeline receives the captured video.
       - If `st.session_state.get("webcam_preview_frame") is not None` and `video_path is None`:
         - Set `first_frame = st.session_state["webcam_preview_frame"]`.
         - Set `meta = {"width": first_frame.shape[1], "height": first_frame.shape[0], "fps": float(requested_fps), "frame_count": int(capture_duration_s * requested_fps)}`.
         - Render info message: 'Preview frame loaded. Adjust Target and Anchor ROIs below before recording.'
       - If `st.session_state.get("webcam_capture_result") is not None`:
         - Retrieve `cap_res: CaptureResult = st.session_state["webcam_capture_result"]`.
         - Render Frame-Rate Stability Card:
           - Header with `st.subheader("📹 Capture Stability & Timing Diagnostics")`.
           - Status badge banner: `st.markdown(f"### Status: {stability_badge(cap_res.stability.status)}")`.
           - 4 metric cards (`st.columns(4)`):
             - Card 1: Measured FPS: `f"{cap_res.stability.measured_fps:.2f} FPS"` (delta: `f"{cap_res.stability.measured_fps - cap_res.stability.nominal_fps:+.1f} vs target"`).
             - Card 2: Timestamp Jitter: `f"{cap_res.stability.jitter_ratio * 100:.1f}%"` (sub: `f"Robust: {cap_res.stability.robust_jitter_ratio * 100:.1f}%"`).
             - Card 3: Dropped Frames: `f"{cap_res.stability.dropped_frames_count}"` (sub: `f"{len(cap_res.stability.dropped_frame_indices)} intervals"`).
             - Card 4: Capture Duration: `f"{cap_res.stability.duration_s:.2f} s"` (sub: `f"{cap_res.stability.total_frames} frames"`).
           - If `cap_res.stability.status == "REJECTED_UNSTABLE"`:
             - Render `st.error()`:
               - Bullet points of all `cap_res.stability.status_reasons`.
               - Guidance: 'Capture rejected due to unstable frame timing or excessive dropped frames. In-situ vibration Welch PSD requires constant frame rate. Remediation: check camera connection, verify USB bus bandwidth, reduce CPU load, or adjust lighting to prevent camera auto-exposure rate dropping.'
             - Suppress / block vibration analysis execution until a stable recording is obtained.
           - Else:
             - If `cap_res.stability.status == "WARNING_JITTER"`:
               - Render `st.warning()` with warning reasons.
             - Pass `fps_override = cap_res.stability.measured_fps` to downstream `analyse_video` call so frequency spectra use empirical ground truth!
             - Proceed to standard analysis execution, auto-assessment against stored baseline, and 'Save Run to Asset History'.

3. In `tests/test_ui.py`:
   - Add unit test for `stability_badge` helper.
   - Add headless `AppTest` test case `test_ui_webcam_mode_selection_and_controls`:
     - Load `AppTest.from_file(APP_PATH)`.
     - Select "Live Webcam Stream" on the source radio.
     - Run script.
     - Assert text input for camera source exists and default is "0".
     - Assert duration slider and FPS selectbox exist.
   - Add headless `AppTest` test case `test_ui_webcam_preview_grab_mock`:
     - Set camera source to `"mock:0"`.
     - Click "Grab Preview Frame".
     - Run script.
     - Assert preview frame is stored in session state and displayed.
   - Add headless `AppTest` test case `test_ui_webcam_record_and_stability_card`:
     - Set camera source to `"mock:0"`, duration to 3.0s.
     - Click "Record Live Capture".
     - Run script.
     - Assert `webcam_capture_result` exists in session state.
     - Assert stability badge and metrics render.
   - Add headless `AppTest` test case `test_ui_webcam_unstable_rejection_blocks_analysis`:
     - Create CaptureResult with `status="REJECTED_UNSTABLE"`.
     - Inject into session state.
     - Run script.
     - Assert error banner is present and analysis button is blocked or suppressed.
  </action>
  <verify>
    <automated>./.venv/bin/pytest tests/test_ui.py -v && ./.venv/bin/pytest</automated>
  </verify>
  <done>
The Streamlit operator workbench seamlessly supports live webcam stream acquisition with preview ROI validation, live progress reporting, Frame-Rate Stability Card diagnostics, quality gating, and automatic handoff to analyse_video with measured FPS. All headless AppTest tests in tests/test_ui.py and full test suite pass with zero regressions.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Operator UI / CLI Input → Camera Capture Engine | Untrusted camera source string (e.g. index, path, or mock) and duration values passed to OpenCV VideoCapture and capture loops. |
| OS Video Driver (AVFoundation / V4L2) → In-Memory Buffer | Physical camera hardware and OS driver delivering variable-rate frames and potential buffer lag. |
| In-Memory Capture Buffer → Filesystem Storage | Buffered video frames written to MP4 container in `output/webcam_captures/` and stability metadata JSON. |
| Frame-Rate Stability Gate → Downstream Vibration PSD | Measured empirical timestamps and stability classification passed to `analyse_video` and Welch PSD calculations. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-06-01 | Denial of Service | `phasesight/capture.py:capture_live_clip`, `grab_preview_frame` | high | mitigate | Wrap all `cv2.VideoCapture` and `cv2.VideoWriter` instances in strict `try...finally: cap.release(); writer.release()` blocks to guarantee camera hardware device locks and file handles are released even on exceptions or user cancellation. |
| T-06-02 | Denial of Service / Memory Exhaustion | `phasesight/capture.py:capture_live_clip`, `phasesight/app.py` | medium | mitigate | Validate capture duration ($1.0 \le \text{duration} \le 30.0$ s, default 5.0 s) and cap maximum allowed recording time to 30.0 seconds to prevent unbounded in-memory frame buffering from exhausting RAM. |
| T-06-03 | Tampering / Path Traversal | `phasesight/cli.py`, `phasesight/capture.py` | medium | mitigate | Sanitize user-provided output file paths using `Path(output_path).name` and anchor recordings strictly within project directory `output/webcam_captures/`. |
| T-06-04 | Integrity / Frequency Distortion | `phasesight/capture.py:calculate_timestamp_stability` → `phasesight/video.py` | high | mitigate | Derive empirical sampling rate $f_s = 1.0 / \text{median}(\Delta t)$ strictly from high-resolution monotonic timestamps (`time.perf_counter()`) rather than unreliable camera metadata FPS (`CAP_PROP_FPS`), and pass `fps_override=measured_fps` to `analyse_video`. |
| T-06-05 | Integrity / Spectral Leakage from Dropped Frames | `phasesight/capture.py:calculate_timestamp_stability` → `phasesight/app.py` | high | mitigate | Gate downstream analysis: classify capture stability into `STABLE`, `WARNING_JITTER`, and `REJECTED_UNSTABLE`. Reject captures with $>3$ dropped frames, severe stalls ($>2.5\times\text{median}(\Delta t)$), or jitter $\ge 15\%$, blocking spectral analysis and guiding operator remediation. |
| T-06-SC | Tampering / Supply Chain | `pyproject.toml` | high | mitigate | Strictly use verified in-repo dependencies (`opencv-python==5.1.0`, `numpy==2.5.5`, `scipy==1.18.1`, `streamlit==1.67.0`, `pytest==9.2.0`). Zero new external dependencies are introduced. |
</threat_model>

<verification>
Automated verification commands:
1. Capture Module & Stability Unit Tests: `./.venv/bin/pytest tests/test_capture.py -v`
2. Streamlit UI Headless AppTest Suite: `./.venv/bin/pytest tests/test_ui.py -v`
3. CLI Capture Command Check: `./.venv/bin/python -m phasesight.cli capture mock:0 --duration 1.0 --out output/webcam_captures/cli_test.mp4 --json output/webcam_captures/cli_report.json`
4. Full Test Suite (Zero Regressions): `./.venv/bin/pytest -v` (70+ tests passing)
</verification>

<success_criteria>
1. `phasesight/capture.py` implements `CaptureStabilityReport`, `CaptureResult`, `calculate_timestamp_stability`, `MockVideoCapture`, `open_capture_source`, `grab_preview_frame`, and `capture_live_clip`.
2. Timing jitter ($\text{std}(\Delta t)/\text{median}(\Delta t)$ and robust MAD), dropped frames ($\Delta t > 1.5\times\text{median}(\Delta t)$), and large stalls are accurately detected and classified into `STABLE`, `WARNING_JITTER`, or `REJECTED_UNSTABLE`.
3. `MockVideoCapture` duck-types `cv2.VideoCapture` and generates synthetic vibrating scenes, enabling 100% automated headless test execution without physical camera hardware.
4. `phasesight capture` CLI subcommand records clips from cameras or mock streams, outputs constant-frame-rate MP4 containers, displays timing diagnostics, and exports JSON reports.
5. Streamlit operator workbench (`phasesight/app.py`) provides "Live Webcam Stream" mode in Tab 1 with camera controls, "📸 Grab Preview Frame" with ROI overlay and texture check, "🔴 Record Live Capture" with progress bar, Frame-Rate Stability Card, quality gating, and automatic handoff to `analyse_video`.
6. Valid webcam recordings pass empirical `measured_fps` into `analyse_video`, seamlessly enabling downstream 1-click auto-assessment and run saving to SQLite and NPZ storage.
7. Automated test suites in `tests/test_capture.py` and `tests/test_ui.py` pass cleanly, and full test suite passes with zero regressions across the codebase.
8. Non-negotiable technical boundaries (pixel domain only, 2D translation only, screening vs diagnosis, monotonic timing, no image domain interpolation) are strictly maintained.
</success_criteria>

<output>
Create `.planning/phases/06-live-webcam/06-01-SUMMARY.md` when execution is complete.
</output>
