# Phase 6 Plan 01 Summary: Live Webcam Stream & Dropped Frame Handling

## Execution Overview
Phase 6 integrated real-time video acquisition into PhaseSight, addressing the physical timing irregularities inherent to low-cost USB webcams and variable lighting conditions. Video streams can now be acquired live from physical cameras or deterministic virtual streams (`mock:0`), with every frame timestamped using monotonic wall-clock timing (`time.perf_counter()`). A rigorous frame-rate stability engine calculates empirical sampling rates ($f_s = 1.0 / \text{median}(\Delta t)$), continuous timing jitter, and dropped frames. Streams failing Nyquist regularity requirements are flagged and gated before downstream Welch PSD spectral analysis, preventing spurious spectral artifacts.

## Core Deliverables

### 1. Robust Monotonic Capture & Stability Engine (`phasesight/capture.py`)
- **Monotonic Timestamping:** Records true arrival times with `time.perf_counter()` to defeat auto-exposure clock drift and variable frame delivery.
- **Empirical Sampling Rate:** Computes $f_s = 1.0 / \text{median}(\Delta t)$ rather than trusting nominal driver/container metadata.
- **Timing Jitter & Gap Analysis:** Computes standard jitter $\text{std}(\Delta t) / \text{median}(\Delta t)$, robust MAD jitter $1.4826 \times \text{MAD}(\Delta t) / \text{median}(\Delta t)$, integer dropped frame counts ($\Delta t > 1.5 \times \text{median}(\Delta t)$), and large frame stalls ($> 2.5 \times \text{median}(\Delta t)$).
- **Stability Quality Gate:**
  - `STABLE`: Jitter ratio $< 5\%$, 0 dropped frames, no large gaps.
  - `WARNING_JITTER`: Jitter $5\%-15\%$ or $\le 3$ dropped frames. Permitted for analysis with operator caution.
  - `REJECTED_UNSTABLE`: Jitter $> 15\%$, $> 3$ dropped frames, or large stalls. Spectral analysis is blocked.
- **MockVideoCapture Virtual Device:** Deterministic synthetic video capture stream supporting `mock:<index>` syntax for offline headless testing and CI/CD without physical webcam hardware.
- **Preview & Acquisition API:** `grab_preview_frame(source)` and `capture_live_clip(...)` with real-time progress callbacks and container rate clamping ($1 \le \text{fps} \le 120$).

### 2. CLI Live Capture Subcommand (`phasesight/cli.py`)
- Added `phasesight capture` subcommand:
  ```bash
  phasesight capture 0 --duration 5.0 --target-fps 30.0 --out output/webcam.mp4
  phasesight capture mock:0 --duration 2.0 --out output/mock.mp4
  ```
- Renders an ASCII stability diagnostics report detailing duration, nominal FPS, empirical FPS, jitter ratio, dropped frame counts, and gate status (`STABLE`, `WARNING_JITTER`, `REJECTED_UNSTABLE`).

### 3. Streamlit Operator Workbench Integration (`phasesight/app.py` & `phasesight/ui_helpers.py`)
- **Video Input Radio:** Added `"Live Webcam Stream"` option alongside portable clips and file upload.
- **Camera Acquisition Controls:** Inputs for Camera Index/Source (including `mock:0`), duration slider (2.0s to 20.0s), and target FPS selector (15, 30, 60 FPS).
- **Preview Frame Grabber:** "📸 Grab Preview Frame" acquires a single frame from the camera to configure and visually verify Target and Anchor ROIs before recording.
- **Live Recording with Progress:** "🔴 Record Live Capture" acquires frames with a real-time progress bar, saves the video container, and syncs empirical FPS to `fps_override`.
- **Frame-Rate Stability Card:** Renders Timing Status badge, Measured FPS, Timing Jitter %, Dropped Frames count, and contextual warning/rejection banners.
- **Spectral Gating:** Disables the "Run Vibration Analysis" button if acquisition status is `REJECTED_UNSTABLE` or if only a preview frame has been grabbed without recording a video clip.

### 4. Comprehensive Test Suite (`tests/test_capture.py` & `tests/test_ui.py`)
- **Capture Unit Tests (13 tests in `test_capture.py`):**
  - Monotonic stability calculation on uniform timestamps.
  - Jitter detection on perturbed timestamps.
  - Integer dropped frame gap detection and stall classification.
  - Multi-condition stability report logic (`STABLE`, `WARNING_JITTER`, `REJECTED_UNSTABLE`).
  - Empty and single-timestamp error handling.
  - `MockVideoCapture` initialization, frame reading, and release.
  - Frame preview grabbing.
  - Full simulated live capture and video generation.
  - Progress callback execution.
  - Graceful hardware failure handling.
  - CLI capture subcommand execution with `mock:0`.
- **UI Streamlit AppTest Tests (3 new tests in `test_ui.py`, 15 total):**
  - `test_stability_badge_formatting`: Tests colored status markdown strings.
  - `test_ui_live_webcam_mode_preview_and_record`: Verifies radio switching, camera input setting to `mock:0`, preview frame grabbing, duration sliding, live recording, and session state persistence.
  - `test_ui_live_webcam_rejected_unstable_blocks_analysis`: Verifies that `REJECTED_UNSTABLE` stability report disables the "Run Vibration Analysis" button.

## Verification Results
- **Full Pytest Suite:** 79 passed out of 79 tests in 17.01s (`pytest -v`). 100% pass rate.
- **Synthetic Validation Suite:** 4 of 4 scenarios pass (`phasesight validate --json data/validation_results.json`).
- **CLI Capture Validation:** Live capture on `mock:0` succeeds with 0 dropped frames and `STABLE` rating.
