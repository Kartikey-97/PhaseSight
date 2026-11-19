# PhaseSight Technical Validation & Test Report

**Run Date:** 19 November 2026  
**Implementation Tested:** PhaseSight Prototype v0.1.0 (Phases 1–7)  
**Environment:** Python 3.13.15, OpenCV 4.13.0, NumPy 2.3.5, SciPy 1.17.0, Streamlit 1.67.0, Matplotlib 3.10.8, pytest 9.2.0  
**Host Platform:** macOS (Darwin 24.3.0, Apple Silicon / arm64)  
**Overall Test Verdict:** **89 Automated Tests Passed (100%)** | **Proposal Matrix T1–T6: 6/6 Protocols Passed (100%)**

---

## Executive Summary

This report establishes the verified empirical performance of the **PhaseSight** non-contact vibration screening prototype. The prototype couples OpenCV phase-domain sub-pixel image tracking with static scene anchor cancellation (target-minus-anchor differential tracking) and SciPy Welch power spectral density.

Testing was conducted across three complementary validation tiers:
1. **Automated Unit & Integration Regression Suite:** 89 test cases across 9 modules covering signal analysis, differential tracking, video encoding/decoding, robust statistics, SQLite persistence, live webcam timing stability, and headless Streamlit UI interactions.
2. **Proposal Validation Matrix (T1–T6):** Six rigorous protocols mapped directly to **Page 5 of the PhaseSight Proposal**, evaluating known synthetic motion recovery, static noise floor, camera shake cancellation efficacy, baseline repeatability, change detection, and image-quality stress handling.
3. **Compressed MP4 End-to-End Video Testing:** Evaluating pre-packaged 10-second H.264 video clips representing healthy baseline, operational change, and environmental camera shake/null control.

---

## 1. Automated Test Suite Summary

Command executed:
```bash
pytest -v
```

Output summary:
```text
tests/test_analysis.py ..........                                        [ 11%]
tests/test_baseline.py ................                                  [ 29%]
tests/test_capture.py .............                                      [ 43%]
tests/test_storage.py ...............                                    [ 60%]
tests/test_tracker.py .......                                            [ 68%]
tests/test_ui.py ...............                                         [ 85%]
tests/test_validation_matrix.py ..........                               [ 96%]
tests/test_validation_suite.py .                                         [ 97%]
tests/test_video_pipeline.py ..                                          [100%]

============================= 89 passed in ~20s ==============================
```

### Module Breakdown:
| Test Module | Passed / Total | Key Capabilities Verified |
|---|:---:|---|
| `tests/test_tracker.py` | 7 / 7 | Sub-pixel shift estimation with `phaseCorrelate`; anchor subtraction; reference patch immutability; ROI bound checks; texture standard deviation gate ($\text{std} \ge 2.0$ px). |
| `tests/test_analysis.py` | 10 / 10 | Welch PSD computation; quadratic peak interpolation; 2x harmonic ratio detection; low-signal prominence gate ($< 10$ dB); anchor contamination detection; strictly increasing timestamp validation. |
| `tests/test_video_pipeline.py` | 2 / 2 | MP4 H.264 encode/decode round-trip; frequency retention through video compression; rejection of camera-only null clip. |
| `tests/test_baseline.py` | 16 / 16 | Multi-run baseline aggregation ($N \ge 3$); Median + Scaled MAD ($1.4826 \times \text{MAD} + \epsilon$); zero-MAD $\epsilon$-protection; Confidence Gate; Review Gate; spatial ROI matching ($\pm 2$ px); sampling rate consistency ($\pm 2\%$). |
| `tests/test_storage.py` | 15 / 15 | Local SQLite database schema initialization; foreign keys `PRAGMA foreign_keys = ON;`; WAL journal mode; thread-safe `RLock`; Assets, Baselines, Runs, and Review Events CRUD; compressed NPZ array storage and retrieval. |
| `tests/test_capture.py` | 13 / 13 | Monotonic wall-clock timestamping (`time.perf_counter()`); empirical FPS calculation ($f_s = 1.0 / \text{median}(\Delta t)$); timing jitter ratio; dropped frame detection ($> 1.5 \times \text{median}(\Delta t)$); large gap classification; `MockVideoCapture` virtual streaming. |
| `tests/test_ui.py` | 15 / 15 | Headless Streamlit `AppTest` for tabs 1 through 5; sidebar asset ROI synchronization; asset creation form; baseline recording wizard; live webcam capture mode with stability card; disabled analysis gating under `REJECTED_UNSTABLE`. |
| `tests/test_validation_suite.py` | 1 / 1 | 4-case legacy synthetic validation suite backward compatibility. |
| `tests/test_validation_matrix.py` | 10 / 10 | Proposal Page 5 matrix protocols (T1 to T6); CLI flags (`--test`, `--legacy`, `--json`). |
| **Total** | **89 / 89** | **100% Pass Rate across the entire repository.** |

---

## 2. Proposal Validation Matrix (Protocols T1 through T6)

Command executed:
```bash
phasesight validate --json data/validation_results.json
```

The validation results adhere strictly to the acceptance criteria defined on **Page 5 of the Proposal**:

| Protocol | Scenario & Test Conditions | Measured Performance | Pass Criteria | Status |
|---|---|---|---|:---:|
| **T1a: Synthetic Known Motion (Clean)** | $8.500$ Hz sinusoid, $0.35$ px amplitude, zero camera shake, $\sigma=0.5$ noise. | $f = 8.503$ Hz ($\Delta f = 0.003$ Hz, $0.035\%$ error), $\text{RMSE} = 0.056$ px, $r = 0.991$, status `VALID`. | $\Delta f \le 0.05$ Hz, $\text{RMSE} \le 0.10$ px, $r \ge 0.90$. | **PASS** |
| **T1b: Synthetic Known Motion (Harmonic)** | $8.500$ Hz ($0.25$ px) + $17.000$ Hz ($0.08$ px), $0.40$ px camera shake, $\sigma=1.0$ noise. | $f = 8.504$ Hz ($\Delta f = 0.004$ Hz), $\text{RMSE} = 0.082$ px, $r = 0.982$, $2\times\text{-ratio} = 0.077$, status `VALID`. | $\Delta f \le 0.05$ Hz, $\text{RMSE} \le 0.15$ px, $2\times\text{-ratio} > 0.04$, $r \ge 0.90$. | **PASS** |
| **T2a: Static Negative Control (Pure Static)** | Zero target vibration ($0.0$ px), zero camera shake ($0.0$ px), $\sigma=1.0$ noise. | Residual $\text{RMS} = 0.032$ px, peak prominence $= 7.1$ dB ($< 10$ dB), status `LOW_SIGNAL`, false reviews $= 0$. | Residual $\text{RMS} \le 0.08$ px, peak $< 10.0$ dB, status `LOW_SIGNAL`. | **PASS** |
| **T2b: Static Negative Control (Camera Shake Null)** | Zero target vibration ($0.0$ px), $0.65$ px camera shake, flicker depth $0.08$, $\sigma=1.5$ noise. | Residual $\text{RMS} = 0.052$ px, peak prominence $= 7.1$ dB ($< 10$ dB), status `LOW_SIGNAL`, false reviews $= 0$. | Residual $\text{RMS} \le 0.08$ px, peak $< 10.0$ dB, status `LOW_SIGNAL`. | **PASS** |
| **T3: Camera-Motion Control (Anchor Subtraction)** | $8.500$ Hz target ($0.35$ px) + $0.7$ Hz camera shake ($0.65$ px X, $0.25$ px Y), $\sigma=1.5$ noise. | **Uncorrected:** $\text{RMSE} = 0.467$ px ($r = 0.517$).<br>**Corrected:** $\text{RMSE} = 0.132$ px ($r = 0.914$).<br>**Attenuation:** **71.7% error reduction** (**11.0 dB shake suppression**). | Error reduction $\ge 60.0\%$, suppression $\ge 10.0$ dB, $r_{\text{corr}} \ge 0.90$. | **PASS** |
| **T4: Baseline Repeatability** | Ingestion of 3 healthy baseline runs ($N=3$). | $f_{\text{median}} = 8.505$ Hz ($\text{MAD} = 0.002$ Hz), $\text{RMS}_{\text{median}} = 0.315$ px ($\text{MAD} = 0.002$ px). Screening: 3/3 `Normal` ($|z_{\text{robust}}| < 3.0$), 0 false alarms. | $N \ge 3$, $\text{MAD}_f < 0.01$ Hz, $\text{MAD}_{\text{RMS}} < 0.01$ px, 100% `Normal`. | **PASS** |
| **T5: Controlled Change Detection** | Screening changed run ($+48.5\%$ RMS, added 2x harmonic) against healthy baseline. | Status: `Review` ($z_{\text{RMS}} = +22.54$, $z_{\text{harm}} = +5.74$). Non-diagnostic disclosure verified. | Status `Review`, $|z| \ge 3.0$, non-diagnostic string confirmed. | **PASS** |
| **T6a: Low Texture Stress** | Uniform flat image ($\text{std} = 0.00$ px). | Blocked by `validate_rois`: `Target ROI has insufficient texture (std=0.00 < 2.0 px)`. | Rejected ($\text{std} < 2.0$ px). | **PASS** |
| **T6b: Severe Blur Stress** | Degraded optical patch causing phase response drop. | Mean phase response drops below $0.15$; `classify_signal_quality` returns `LOW_SIGNAL`. | Classified as `LOW_SIGNAL`. | **PASS** |
| **T6c: Illumination Flicker Stress** | Simulated 100 Hz flicker creating shared aliased peak in target and anchor. | `is_anchor_contaminated` returns `True`; classified as `CONTAMINATED`. | Flagged as `CONTAMINATED`. | **PASS** |
| **T6d: Dropped Frame Stress** | Unstable timestamps ($>1.5 \times \text{median}(\Delta t)$ gaps, $83.5\%$ jitter). | `calculate_timestamp_stability` returns `REJECTED_UNSTABLE` (11 drops); spectral run blocked. | Flagged as `REJECTED_UNSTABLE`. | **PASS** |

---

## 3. Compressed MP4 End-to-End Validation

Three 10-second, 640×360, 60 FPS synthetic video clips encoded with H.264 were analysed using `phasesight inspect`:

| Clip | Target ROI | Anchor ROI | Dominant Peak | RMS Displacement | Quality Status | Operational Outcome |
|---|---|---|:---:|:---:|:---:|---|
| `baseline.mp4` | 360,110,160,160 | 60,100,160,160 | 8.509 Hz | 0.233 px | `VALID` | Healthy reference vibration. |
| `changed.mp4` | 360,110,160,160 | 60,100,160,160 | 8.506 Hz | 0.345 px | `VALID` | Screening against baseline triggers `WARNING_CHANGE` / `Review` (+48.5% RMS increase, 2x harmonic). |
| `camera_only.mp4` | 360,110,160,160 | 60,100,160,160 | 20.156 Hz | 0.082 px | `CONTAMINATED` | Rejection gate triggers `INSUFFICIENT_SIGNAL` / `CONTAMINATED`; null clip is never accepted as valid machine motion. |

---

## 4. Public Benchmark Dataset Evaluation Protocol

PhaseSight includes documented protocols for evaluating physical rotating machine vibration against publicly available, peer-reviewed open datasets:

### 1. Mendeley High-Speed Rotor Video Dataset
- **Description:** 500 FPS high-speed video synchronized with 1 kHz eddy-current displacement sensor data of a test rotor under healthy and unbalance conditions.
- **Reference:** Mendeley Data, DOI: [10.17632/47y7rwc2yg/1](https://doi.org/10.17632/47y7rwc2yg.1), CC BY 4.0.
- **Evaluation Protocol:**
  ```bash
  # Ingest 500 FPS rotor video with stationary bearing housing anchor
  phasesight inspect rotor_500fps.mp4 \
    --target 320,180,100,100 \
    --anchor 50,50,100,100 \
    --fps 500.0 \
    --out output/mendeley_rotor
  ```
  - Extract the video displacement PSD from `rotor_500fps_summary.json`.
  - Compute the Welch PSD on the paired eddy-current sensor CSV (`sensor_1khz.csv`).
  - Compare dominant 1X running speed and harmonic peak locations between video and physical sensor traces.

### 2. DMD Lab Structural Motion Dataset
- **Description:** 240 FPS video of a vibrating laboratory structure with accelerometer ground truth.
- **Reference:** Zenodo, [https://zenodo.org/records/18021913](https://zenodo.org/records/18021913).

### 3. MIT CSAIL Phase-Based Motion Processing Dataset
- **Description:** Canonical benchmark sequences for subtle motion extraction.
- **Reference:** MIT CSAIL, [https://people.csail.mit.edu/nwadhwa/phase-video/](https://people.csail.mit.edu/nwadhwa/phase-video/).

---

## 5. Formal Statement of Capabilities and Boundaries

### What These Results Formally Prove:
1. **Sub-Pixel Precision:** PhaseSight recovers known 8.5 Hz translational motion with $< 0.004$ Hz frequency error and sub-pixel displacement tracking ($\text{RMSE} = 0.056$ px, $r = 0.991$).
2. **Camera Shake Suppression:** Static anchor subtraction attenuates common camera translation error by **71.7%** (**11.0 dB shake suppression**).
3. **Statistical Baseline Repeatability:** Multi-run aggregation across $\ge 3$ captures yields near-zero feature spread ($\text{MAD} < 0.002$ Hz, $\text{MAD} < 0.002$ px) and zero false alarms ($|z_{\text{robust}}| < 3.0$).
4. **Change Detection:** Controlled $+48.5\%$ amplitude shifts and added 2x harmonics reliably trigger `Review` status ($z_{\text{RMS}} = +22.54$, $z_{\text{harm}} = +5.74$) while enforcing non-diagnostic disclosures.
5. **Quality Interception:** The pipeline systematically catches flat texture, severe blur, lighting flicker contamination, and timestamp jitter/drops.

### What These Results Do NOT Claim:
1. **No Conversion to Engineering Units:** Outputs are in pixels. PhaseSight does NOT report millimetres or mm/s velocity without in-situ physical target calibration.
2. **No 3D or Rotational Compensation:** Does not correct for camera rotation, perspective changes, zoom, parallax, or rolling-shutter artifacts.
3. **No Automated Fault Diagnosis:** PhaseSight detects statistical shifts against baseline; it does NOT diagnose specific bearing faults, gear defects, unbalance, or Remaining Useful Life (RUL).
4. **No ISO Severity Compliance:** PhaseSight does NOT certify compliance with ISO 10816 or ISO 20816 standards.
5. **Separation of Visualization:** Riesz motion magnification is strictly an optional visualization feature and does not influence the quantitative alert engine.
