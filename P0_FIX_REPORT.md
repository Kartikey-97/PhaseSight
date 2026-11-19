# PhaseSight P0 Engineering Fix Report — Strict Test-Driven Execution

**Repository:** `~/Desktop/PhaseSight_Validation_Kit`  
**Execution Date:** November 19, 2026  
**Git Base Checkpoint:** `checkpoint-pre-p0-fixes` (`47bf500`)  
**Git Final Commit:** `8e4f963` (Tagged: `p0-fixes-complete`)  
**Test Suite Pass Rate:** **117 / 117 tests passing (100%)** (+28 new regression tests)  
**Proposal Validation Protocols (T1–T6):** **6 / 6 protocols passing (100%)**  

---

## 1. Executive Summary

An independent engineering audit identified three potentially measurement-invalidating algorithmic defects and one CLI execution flaw:
1. **P0-1 (Tracker):** Missing per-frame texture and response validation in `PhaseCorrelationTracker.process()`, allowing untextured or flat frames to return artificial half-width/half-height displacement jumps ($(W/2, H/2)$).
2. **P0-2 (Spectral Analysis):** Harmonic detection integrated spectral power around $2 \times f_0$ without requiring a true local peak or prominence above the noise floor, producing false non-zero harmonic ratios on pure sine waves.
3. **P0-3 (Temporal Sampling):** Video analysis synthesized timestamps using `index / fps`, concealing dropped frames, container timestamp jitter, and variable frame rates, while `analyse_displacement` silently interpolated across arbitrary missing intervals.
4. **P0-4 (CLI Launcher):** `phasesight ui` hardcoded `"streamlit"` as the executable name in `subprocess.run()`, raising `FileNotFoundError` when `.venv/bin` was not on `$PATH`.

All four issues have been resolved using minimal, targeted, test-driven changes. Ground truths were never weakened, and dedicated regression test matrices were added for every fix.

---

## 2. Task 1 — Dynamic ROI Quality Validation

### 2.1 Root Cause
In OpenCV, `cv2.phaseCorrelate(src1, src2, window)` on an untextured or all-zero patch produces a cross-power spectrum with zero division or uniform phase, returning the coordinate center $(W/2, H/2)$ with a `response = 0.0`. When `PhaseCorrelationTracker` only validated texture on frame 0, any subsequent drop in image quality (e.g. occlusion, blackouts, glare, or camera disconnection) caused spurious displacement jumps of $+80.0$ px on a $160 \times 160$ ROI, contaminating downstream Welch spectra.

### 2.2 Implementation Details (`phasesight/tracker.py`)
1. **Extended `MotionSample`:** Added `valid: bool = True` and `rejection_reason: str | None = None` to the immutable `MotionSample` dataclass.
2. **Per-Frame Quality Gate:** In `PhaseCorrelationTracker.process()`:
   - Validated crop dimensions against expected ROI dimensions (`invalid_crop_dimensions`).
   - Verified that all pixels in target and anchor crops are finite (`target_non_finite`, `anchor_non_finite`).
   - Checked pixel contrast/texture standard deviation: `target_std >= min_texture_std` and `anchor_std >= min_texture_std` (default `min_texture_std = 2.0` px).
   - If texture fails or pixels are non-finite, `cv2.phaseCorrelate` is **not called**, preventing artificial $(W/2, H/2)$ coordinate jumps. Displacements are explicitly set to `float('nan')`, responses to `0.0`, `valid = False`, and `rejection_reason` is set.
   - If texture is valid, `phaseCorrelate` is executed and phase response is evaluated against `min_response` (default `0.15`). If response is below threshold, samples are marked invalid with `NaN` displacements.
   - When texture recovers, valid tracking resumes immediately without error accumulation or artificial offset.
3. **Downstream Gate in `phasesight/video.py`:** If any invalid tracking sample occurs during recorded video analysis, `analyse_video` raises `RuntimeError` rather than passing corrupted measurements to Welch PSD.

### 2.3 Regression Tests (`tests/test_tracker.py`)
Eight dedicated regression tests were added to cover the required scenarios:
- `test_dynamic_roi_regression_1_normal_moving_textured`: Valid frames maintain `valid=True`, finite displacement, and high response.
- `test_dynamic_roi_regression_2_black_halfway`: Halfway black target triggers `valid=False`, `rejection_reason="target_low_texture"`, `NaN` displacements, and verifies **no half-width jumps** (`target_dx != 80.0`).
- `test_dynamic_roi_regression_3_uniformly_white`: Uniform white target triggers `valid=False`, `NaN` displacements, no coordinate jump.
- `test_dynamic_roi_regression_4_gradual_contrast_loss`: Fading contrast is rejected as soon as `std < min_texture_std`.
- `test_dynamic_roi_regression_5_temporary_texture_loss_and_recovery`: Temporary 5-frame occlusion transitions from `valid` $\to$ `invalid` $\to$ `valid` recovery without drift.
- `test_dynamic_roi_regression_6_target_loses_texture_anchor_valid`: Target failure isolated (`target_low_texture` rejected while anchor is recognized valid).
- `test_dynamic_roi_regression_7_anchor_loses_texture_target_valid`: Anchor failure isolated (`anchor_low_texture` rejected while target is recognized valid).
- `test_dynamic_roi_regression_8_both_rois_invalid`: Both ROIs failing simultaneously reports both in `rejection_reason`.
- `test_dynamic_roi_non_finite_rejection`: `NaN`/`inf` pixel values rejected explicitly.

---

## 3. Task 2 — Harmonic Detection Correction

### 3.1 Root Cause
In `phasesight/analysis.py`, lines 145–151 previously computed:
```python
fundamental_power = float(np.sum(psd[fundamental_band]))
harmonic_power = float(np.sum(psd[harmonic_band]))
second_harmonic_ratio = harmonic_power / fundamental_power
```
This formula integrated power in a window $\pm 1.5 \Delta f$ centered at $2 \times f_0$ without requiring an actual spectral peak. On pure sine waves with zero harmonic content, Hann window sidelobes and broadband noise floor integrated into a non-zero numerator, yielding false harmonic ratios ($10^{-5}$ to $10^{-11}$, or $1.47$ on short windows).

### 3.2 Implementation Details (`phasesight/analysis.py`)
1. **Local Peak Requirement:** Located the candidate peak index `cand_idx = argmax(psd[harm_indices])` within the harmonic band $\pm 1.5 \Delta f$. Enforced strict local maximum condition:
   `is_local_max = psd[cand_idx] > psd[cand_idx - 1] and psd[cand_idx] > psd[cand_idx + 1]`.
   On monotonic sidelobes (pure sines, off-bin sines, 3x harmonic only), `is_local_max` is `False`.
2. **Local Background Estimation:** Computed median background noise floor in a local band $\pm 3.0$ Hz around $2 \times f_0$, excluding bins within $\pm 2$ of candidate harmonic and $\pm 3$ of fundamental peak.
3. **Prominence Gate:** Computed harmonic peak prominence in dB:
   $\text{prominence}_{\text{db}} = 10 \log_{10}(P_{\text{cand}} / P_{\text{background}})$.
   Required `is_local_max` AND $\text{prominence}_{\text{db}} \ge 10.0$ dB (parameter `min_harmonic_prominence_db: float = 10.0`).
4. **Explicit `None` for Undetected Harmonics:** If no local peak exists or prominence $< 10.0$ dB, `second_harmonic_ratio` is set to `None`.
5. **Baseline Compatibility:** `phasesight/baseline.py` already implements tri-state harmonic evaluation (`_compute_harmonic_deviation`). When both baseline and current runs have `None`, harmonic deviation is cleanly omitted without generating false zero deviations.

### 3.3 Regression Test Matrix (`tests/test_analysis.py`)

| Case # | Signal Condition | Fundamental ($f_0$) | Prominence (dB) | Decision | Second Harmonic Ratio |
|---|---|---|---|---|---|
| **Case 1** | Pure 1.0 Hz sine | 1.007 Hz | 29.76 dB | **UNDETECTED (not a peak)** | `None` |
| **Case 2** | Pure 5.0 Hz sine | 5.019 Hz | 4.14 dB | **UNDETECTED (not a peak)** | `None` |
| **Case 3** | Pure 8.5 Hz sine | 8.531 Hz | 2.45 dB | **UNDETECTED (not a peak)** | `None` |
| **Case 4** | Pure 12.0 Hz sine | 12.043 Hz | -3.36 dB | **UNDETECTED (not a peak)** | `None` |
| **Case 5** | 8.5 Hz + weak 2x (1% amp, -40 dB) | 8.531 Hz | 57.56 dB | **DETECTED** | `0.000101` |
| **Case 6** | 8.5 Hz + strong 2x (10% amp, -20 dB) | 8.531 Hz | 65.73 dB | **DETECTED** | `0.010074` |
| **Case 7** | 8.5 Hz + 3x only (25.5 Hz, no 2x) | 8.531 Hz | 2.69 dB | **UNDETECTED (not a peak)** | `None` |
| **Case 8a** | Pure 8.5 Hz + noise (SNR 30 dB) | 8.532 Hz | 9.48 dB | **UNDETECTED (prom < 10 dB)** | `None` |
| **Case 8b** | Pure 8.5 Hz + noise (SNR 20 dB) | 8.530 Hz | -0.56 dB | **UNDETECTED (prom < 10 dB)** | `None` |
| **Case 8c** | Pure 8.5 Hz + noise (SNR 10 dB) | 8.539 Hz | -3.04 dB | **UNDETECTED (prom < 10 dB)** | `None` |
| **Case 9** | Off-bin sines (5.17, 8.43, 11.29 Hz) | Exact | < 3.0 dB | **UNDETECTED (not a peak)** | `None` |
| **Case 10** | Near-boundary 13 Hz (2x = 26 > 25 Hz) | 13.040 Hz | N/A | **OUT_OF_BOUNDS** | `None` |

---

## 4. Task 3 — Recorded Video Timestamp Integrity

### 4.1 Root Cause
In `phasesight/video.py`, timestamps were generated solely via `timestamp_s = index / fps`. This synthetic time series assumed constant frame intervals, concealing frame drops, decoding stalls, and variable frame rates. Furthermore, in `phasesight/analysis.py`, `analyse_displacement` linearly interpolated with `np.interp` across arbitrarily large missing intervals, producing false spectral energy.

### 4.2 Implementation Details (`phasesight/video.py` & `phasesight/analysis.py`)
1. **Container Presentation Timestamps:** In `analyse_video()`, presentation timestamps are queried on every frame using `cap.get(cv2.CAP_PROP_POS_MSEC)`. If timestamps advance and are monotonic, container PTS is utilized (`timestamp_source = "container_pts"`). If the video backend returns frozen or zero PTS, the system falls back to nominal CFR (`timestamp_source = "inferred_cfr_fallback"`).
2. **Temporal Stability Gate:** `analyse_video()` executes `calculate_timestamp_stability(timestamps, nominal_fps=fps)`:
   - Evaluates monotonicity, timing jitter ratio ($\sigma_{\Delta t} / \text{median}(\Delta t)$), dropped frames count, and large gaps.
   - If `stability.status == "REJECTED_UNSTABLE"` and `not allow_unstable_sampling`, `analyse_video` raises `RuntimeError` with specific diagnostic reasons.
3. **Interpolation Safeguard in `analyse_displacement()`:**
   - Parameterized with `max_tolerated_gap_ratio = 1.5` and `max_tolerated_jitter = 0.15`.
   - Any interval $> 1.5 \times \text{median}(\Delta t)$ raises `ValueError("Severe timestamp gap detected...")`.
   - Any jitter ratio $> 15\%$ raises `ValueError("Severe timestamp jitter detected...")`.
   - Minor jitter ($\le 15\%$, gaps $\le 1.5\times$) is safely resampled onto the uniform grid.
4. **Structured Output:** `summary["temporal_stability"]` and `summary["timestamp_source"]` are serialized to inspection JSON. CSV output now records per-frame `valid` and `rejection_reason` columns.

### 4.3 Regression Tests (`tests/test_video_pipeline.py`)
1. `test_timestamp_integrity_1_perfectly_regular_60fps`: Regular 60 fps is STABLE (`drops=0`, `jitter=0.0000`).
2. `test_timestamp_integrity_2_minor_timing_jitter`: 1% jitter is STABLE and resampled cleanly.
3. `test_timestamp_integrity_3_severe_timing_jitter_rejected`: Bimodal high jitter (>20%) is rejected by `analyse_displacement` and marked `REJECTED_UNSTABLE`.
4. `test_timestamp_integrity_4_dropped_frames_large_gap_rejected`: 5-frame dropped gap is rejected with `ValueError` ("Severe timestamp gap detected").
5. `test_timestamp_integrity_5_non_monotonic_timestamps_rejected`: Non-monotonic timestamps raise `ValueError` ("strictly increasing").
6. `test_timestamp_integrity_6_repeated_timestamps_rejected`: Repeated timestamps (zero $\Delta t$) raise `ValueError`.
7. `test_timestamp_integrity_7_vfr_video_unstable_rejected`: Variable frame rate (30 to 60 fps) rejected as unstable.
8. `test_timestamp_integrity_8_video_container_fallback_and_metadata`: Video container inspection records stability and source in summary JSON.

---

## 5. Task 4 — Streamlit CLI Launcher

### 5.1 Root Cause
In `phasesight/cli.py` (line 289), `subprocess.run(["streamlit", "run", ...])` was invoked. When running inside a virtual environment (`.venv`) not explicitly exported to the user's interactive shell `$PATH`, the OS could not locate the `streamlit` executable, raising `FileNotFoundError: [Errno 2] No such file or directory: 'streamlit'`.

### 5.2 Implementation Details (`phasesight/cli.py`)
Replaced:
```python
cmd = [
    "streamlit",
    "run",
    str(app_path),
    f"--server.port={args.port}",
    f"--server.address={args.host}",
]
```
With:
```python
cmd = [
    sys.executable,
    "-m",
    "streamlit",
    "run",
    str(app_path),
    f"--server.port={args.port}",
    f"--server.address={args.host}",
]
```
This guarantees execution via the exact Python interpreter running `phasesight`, ensuring all virtualenv dependencies are accessible regardless of `$PATH`.

### 5.3 Regression Test (`tests/test_ui.py`)
- `test_cli_ui_launcher_uses_sys_executable_with_sanitized_path`: Scrubs `.venv` from `os.environ["PATH"]` and executes `phasesight ui --port 8599 --host 127.0.0.1`. Confirmed that launcher executes `sys.executable -m streamlit run` without `FileNotFoundError`.

---

## 6. Verification & Test Results

### 6.1 Pytest Suite Run
```
tests/test_analysis.py ....................                              [ 17%]
tests/test_baseline.py ................                                  [ 30%]
tests/test_capture.py .............                                      [ 41%]
tests/test_storage.py ...............                                    [ 54%]
tests/test_tracker.py ................                                   [ 68%]
tests/test_ui.py ................                                        [ 82%]
tests/test_validation_matrix.py ..........                               [ 90%]
tests/test_validation_suite.py .                                         [ 91%]
tests/test_video_pipeline.py ..........                                  [100%]

======================== 117 passed in 77.54s (0:01:17) ========================
```

### 6.2 Master Validation Matrix (T1–T6)
Executed: `phasesight validate --json data/validation_results.json`
```
================================================================================
PhaseSight Proposal Validation Matrix (T1–T6) — Innovathon 2026
================================================================================
[PASS] T1: Synthetic Known Motion Recovery
       - Clean Target (8.5 Hz):      f=8.503 Hz (err=0.003 Hz), RMSE=0.056 px, r=0.991
       - Harmonic Target (8.5+17Hz): f=8.504 Hz, RMSE=0.082 px, 2x_ratio=0.077, r=0.982
[PASS] T2: Static Negative Control & Noise Floor
       - Pure Static Scene:          RMS=0.032 px, peak=7.1 dB, qual=LOW_SIGNAL
       - Camera Shake Only (Null):   RMS=0.052 px, peak=7.1 dB, qual=LOW_SIGNAL
[PASS] T3: Camera-Motion Control (Anchor Subtraction Efficacy)
       - Uncorrected Motion:         RMSE=0.467 px, r=0.517
       - Corrected (Subtracted):     RMSE=0.132 px, r=0.914
       - Efficacy:                   71.7% error reduction (11.0 dB shake suppression)
[PASS] T4: Portable Baseline Repeatability (>=3 Captures)
       - Multi-Run Aggregation:      f=8.505 Hz (MAD=0.002), RMS=0.315 px (MAD=0.002)
       - Screening Nominal Runs:     3/3 Normal status, 0 false triggers (|z| < 3.0)
[PASS] T5: Controlled Change Detection (Baseline vs Changed)
       - Changed Clip Screening:     Status: Review (z_rms=+22.54, z_harm=+5.74)
       - Boundary Verification:      Non-diagnostic disclosure confirmed
[PASS] T6: Image-Quality Stress Testing
       - T6a Low Texture:            REJECTED by validate_rois (std=0.00 < 2.0 px)
       - T6b Severe Blur:            DEGRADED phase response -> LOW_SIGNAL
       - T6c Illumination Flicker:   CONTAMINATED flag confirmed (shared peak)
       - T6d Dropped Frames:         REJECTED_UNSTABLE confirmed (jitter=83.5%, 11 drops)
================================================================================
Overall Verdict: ALL 6 PROPOSAL VALIDATION PROTOCOLS PASSED (100%)
================================================================================
```

### 6.3 Packaged Clip Inspections
1. **`baseline.mp4`**:
   - Status: `STABLE`, source: `container_pts`, jitter: $0.0000$, drops: $0$.
   - X-Axis: $f_0 = 8.509$ Hz, RMS $= 0.232$ px, Prominence $= 27.35$ dB, Quality: `VALID`.
   - Harmonic: `null` (pure tone harmonic correctly reported as `null`).
2. **`changed.mp4`**:
   - Status: `STABLE`, source: `container_pts`, jitter: $0.0000$, drops: $0$.
   - X-Axis: $f_0 = 8.506$ Hz, RMS $= 0.345$ px (+48.5%), Prominence $= 26.74$ dB, Quality: `VALID`.
   - Harmonic: `0.0510` (5.1% harmonic detected and measured).
3. **`camera_only.mp4`**:
   - Status: `STABLE`, source: `container_pts`.
   - X-Axis: $f_0 = 20.156$ Hz, RMS $= 0.082$ px, Prominence $= 16.00$ dB, Quality: `CONTAMINATED`.
   - Correctly flagged as `CONTAMINATED` due to shared motion in anchor; not presented as machine vibration.
4. **Comparisons**:
   - `baseline` vs `changed`: `status = "WARNING_CHANGE"`, `rms_change_percent = +48.48%`.
   - `baseline` vs `camera_only`: `status = "INSUFFICIENT_SIGNAL"` (rejected comparison against noise).

---

## 7. Remaining Physical Boundaries & Non-Negotiable Limits

1. **Units:** Outputs remain strictly in image pixels and pixel displacement ($px$), not millimetres or $mm/s$.
2. **2D Translation Only:** Tracking measures planar translation; does not compensate for out-of-plane rotation, perspective warping, roll, or rolling-shutter artifacts.
3. **Static Anchor Prerequisite:** Differential subtraction relies on the anchor ROI remaining physically stationary and in the same focal plane.
4. **Screening vs. Diagnosis:** A `Review` or `WARNING_CHANGE` verdict indicates a statistically significant change against baseline, not a diagnosed bearing, gear, or electrical fault.
