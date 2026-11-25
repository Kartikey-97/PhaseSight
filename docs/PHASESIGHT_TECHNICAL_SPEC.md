# PhaseSight — Canonical Technical Specification & Architectural Baseline
**Document Version:** 1.0 (Pre-Migration Architecture Specification)  
**Date:** November 2026  
**Status:** Canonical Engineering Record  
**Target Repository:** `~/Desktop/PhaseSight_Validation_Kit`  
**Current Git HEAD:** `d1b201f60b578656a8220f88af729b5667721623` (Branch: `master`)  
**Python Runtime:** Python 3.13.15 (`.venv/bin/python`)  
**Core Dependencies:** `numpy 2.5.5`, `scipy 1.18.1`, `opencv-python 5.1.0.95`, `streamlit 1.67.0`, `plotly 7.1.0`, `pytest 9.2.0`

---

## Document Control & Environment Baseline

Before any future migration or re-architecture is executed, this document establishes the exhaustive, non-promotional, source-verified technical specification of the PhaseSight measurement engine. It documents every implemented equation, algorithmic pipeline, data model, persistence schema, validation protocol, known technical limitation, and architectural gap.

### Pre-Audit Repository State
* **Project Root:** `/Users/kartikeygupta/Desktop/PhaseSight_Validation_Kit`
* **Active Git Branch:** `master`
* **Commit Hash:** `d1b201f60b578656a8220f88af729b5667721623`
* **Clean/Dirty Tree:** Uncommitted UI styling improvements and test suite harness enhancements preserved in working tree.
* **CLI Entry Points:** `phasesight = phasesight.cli:main` (via `pyproject.toml`)
* **UI Entry Points:** `phasesight/app.py` (Streamlit runtime)
* **Automated Test Suite:** 129 passing tests across 9 test modules (`pytest tests/`).

---

# SECTION 1 — PHASESIGHT PRODUCT DEFINITION

### 1.1 Original Objective vs. Implemented Objective
* **Original Aspirational Objective:** A camera-based vibration monitoring system capable of connecting to ordinary fixed factory security/CCTV cameras over IP networks (RTSP/ONVIF), continuously tracking rotating machinery, converting optical pixel motion into calibrated metric vibration displacement ($mm$ or $mm/s$), and automatically diagnosing mechanical faults (bearing defects, unbalance, misalignment, looseness) or predicting Remaining Useful Life (RUL).
* **Current Implemented Objective:** A local, video-based vibration *screening* toolkit that tracks relative 2D planar translation of a selected machine region (Target ROI) against a static reference region (Anchor ROI) using sub-pixel phase correlation. It estimates dominant vibration frequencies and peak-to-peak/RMS displacement in the **image pixel domain ($px$)**, evaluates timing regularity and signal prominence, compares results against a statistically established baseline ($N \ge 3$ captures) using robust non-parametric statistics (Median and Median Absolute Deviation), and flags statistical deviations for human operator review.

### 1.2 Current Supported Measurement Capabilities
1. **Sub-Pixel Planar Translation Tracking:** 2D translation $(dx, dy)$ of rigid image patches using OpenCV 2D phase correlation with Hanning windowing and sub-pixel parabolic peak interpolation.
2. **Common-Mode Camera Motion Cancellation:** Real-time algebraic subtraction of anchor ROI motion from target ROI motion to isolate machine displacement from rigid camera vibration.
3. **Temporal Stability Auditing:** Hardware PTS extraction, inter-frame interval $(\Delta t)$ tracking, continuous jitter quantification ($\text{std}(\Delta t) / \text{median}(\Delta t)$), robust MAD jitter, and dropped-frame gap detection.
4. **Spectral Decomposition:** Welch Power Spectral Density (PSD) estimation using median periodogram averaging, 1X fundamental peak localization, peak-to-median spectral prominence scoring (dB), and second harmonic (2X) ratio calculation.
5. **Quality-Gated Verification:** Automatic rejection of low-texture frames ($\sigma < 2.0$), low correlation responses ($r < 0.150$), severe acquisition jitter ($>15\%$), and timestamp gaps ($>1.5\times \text{median}(\Delta t)$).
6. **Robust Statistical Baselines:** Creation of immutable asset baseline profiles from $N \ge 3$ healthy inspection runs using sample Median and scaled MAD ($1.4826 \times \text{MAD}$), followed by two-stage screening (Confidence Gate and Review Gate) using robust z-scores ($|z| \ge 3.0$).
7. **Hybrid Persistence:** Local relational SQLite metadata (`phasesight.db`) paired with compressed NumPy NPZ archives for high-speed time-series and spectral array storage.

### 1.3 Semantic Reality of PhaseSight Outputs
* **Pixel Domain, Not Millimetres:** PhaseSight measures motion in **image pixels ($px$)**. It does **not** output calibrated physical displacement ($\mu m$, $mm$) or vibration velocity ($mm/s$, $\text{in/s}$). Without a known optical scale factor ($\text{mm/pixel}$), verified working distance, perpendicular optical axis alignment, and lens distortion correction, pixel measurements cannot be directly converted to ISO 10816 / ISO 20816 vibration severity standards.
* **Screening vs. Condition Monitoring vs. Fault Diagnosis:**
  * **Screening (What PhaseSight Implements):** Detecting whether an optical signal contains a prominent periodic frequency and whether its motion deviates significantly from a prior healthy statistical baseline.
  * **Condition Monitoring (Partially Implemented):** Tracking trended vibration features over days, weeks, or months to observe progressive degradation. (PhaseSight provides run history in SQLite, but lacks automated degradation forecasting).
  * **Fault Diagnosis (NOT Implemented):** Identifying the specific physical failure mode (e.g., distinguishing an unbalance from an angular misalignment, a bent shaft, or an inner race bearing defect). PhaseSight does not map spectral harmonics to machine kinematics (shaft orders, gear mesh frequencies, or bearing fault frequencies BPFO/BPFI/BSF/FTF).
  * **Remaining Useful Life / RUL (NOT Implemented):** Estimating hours of remaining operational life requires physics-of-failure or trained survival degradation models. PhaseSight contains zero RUL estimation logic.

### 1.4 Fixed Factory/Security CCTV Vision vs. Current Implementation
* **The Long-Term Vision:** Repurposing existing 24/7 factory surveillance cameras or fixed CCTV RTSP streams to eliminate physical accelerometer installation costs.
* **The Implemented Reality:** The current system operates strictly on **locally loaded video files (MP4/AVI)** or **bounded local clip recordings (5–30 seconds via OpenCV)**. It lacks RTSP/H.264 stream decoders, network reconnection logic, ONVIF discovery, Pan-Tilt-Zoom (PTZ) motion compensation, auto-focus/auto-exposure locking, and continuous rolling-buffer analysis.

---

# SECTION 2 — COMPLETE REPOSITORY MAP

### 2.1 Directory Structure
```
PhaseSight_Validation_Kit/
├── .streamlit/
│   └── config.toml                  # Streamlit server and theme configuration
├── data/
│   ├── portable/                    # Portable verification MP4 videos and ground truth
│   │   ├── baseline.mp4             # 640x360 @ 60 FPS synthetic baseline
│   │   ├── camera_only.mp4          # Synthetic camera shake only (null control)
│   │   └── changed.mp4              # Synthetic unbalance / +48% amplitude change
│   ├── rotor_dataset/               # Public SpectraQuest Rotor Test Rig dataset (Mendeley)
│   │   ├── Raw videos/              # High-speed AVI video recordings (500 FPS physical)
│   │   └── Sensor data/             # 4-channel eddy current displacement CSVs (1000 sps)
│   └── storage/                     # Default local SQLite and NPZ storage root
├── docs/                            # Canonical technical specifications and architecture docs
├── output/                          # Inspection outputs, plots, CSVs, and webcam clips
├── phasesight/                      # Core Python measurement engine
│   ├── __init__.py                  # Package exports
│   ├── analysis.py                  # Welch PSD, peak extraction, harmonics, signal quality
│   ├── app.py                       # Streamlit Spectral Observatory user interface
│   ├── baseline.py                  # Robust statistical baseline engine (Median, MAD, z-score)
│   ├── capture.py                   # Live webcam acquisition, timing stability, MockVideoCapture
│   ├── cli.py                       # CLI command parser and subcommands
│   ├── storage.py                   # SQLite relational storage manager and NPZ array archives
│   ├── synthetic.py                 # Synthetic video generation and physical camera shake models
│   ├── tracker.py                   # Sub-pixel phase correlation tracking and dynamic ROI quality
│   ├── ui_fonts.py                  # Embedded base64 font definitions (Zero-404 offline fonts)
│   ├── ui_helpers.py                # Viewport drawing, telemetry badges, and CSV array parsing
│   ├── ui_styles.py                 # Liquid Glass CSS injection and Plotly workstation theming
│   ├── ui_tokens.py                 # Design tokens (colors, glass tokens, typography)
│   ├── ui_viewport.py               # Scientific measurement viewport and ROI inspector cards
│   ├── validation.py                # Master validation matrix protocols (T1 to T6)
│   └── video.py                     # Offline video decoding, timestamp synthesis, inspection pipeline
├── reports/                         # Generated benchmark reports and validation records
├── static/                          # Static assets and typography files
├── tests/                           # Pytest test suite (129 unit, regression, and E2E tests)
├── tools/                           # Public dataset benchmarking tools and scripts
│   └── rotor_dataset_benchmark/     # Phase 1-6 analysis scripts for SpectraQuest rotor dataset
├── pyproject.toml                   # Project metadata, dependencies, and CLI script entry point
└── README.md                        # Project overview and quickstart guide
```

### 2.2 Detailed Source Module Catalog

#### `phasesight/tracker.py`
* **Purpose:** Core optical motion estimation engine. Extracts 2D planar sub-pixel translations between image patches using Fourier-domain phase correlation with dynamic quality gating.
* **Important Classes:**
  * `ROI(x: int, y: int, width: int, height: int)`: Immutable rectangular bounding box. Methods: `validate(frame_shape, name)`, `crop(frame)`.
  * `MotionSample`: Dataclass containing per-frame tracking results: `timestamp_s`, `target_dx_px`, `target_dy_px`, `anchor_dx_px`, `anchor_dy_px`, `relative_dx_px`, `relative_dy_px`, `target_response`, `anchor_response`, `valid`, `rejection_reason`.
  * `PhaseCorrelationTracker`: State machine tracking target translation relative to a fixed anchor reference patch.
* **Important Functions:**
  * `to_gray_float(frame: np.ndarray) -> np.ndarray`: Converts BGR/BGRA/gray frames to single-channel contiguous `float32`.
  * `_normalise_patch(patch: np.ndarray) -> np.ndarray`: Zero-means and unit-variance normalizes an image patch.
  * `check_roi_texture(frame: np.ndarray, roi: ROI, min_std: float = 2.0) -> tuple[bool, float]`: Computes pixel intensity standard deviation $\sigma$.
  * `validate_rois(frame: np.ndarray, target: ROI, anchor: ROI, min_size=32, min_texture_std=2.0) -> list[str]`: Pre-flight bounds, overlap, and texture check.
  * `draw_rois_on_frame(frame, target_roi, anchor_roi) -> np.ndarray`: Annotates OpenCV viewport with bounding boxes and dimensions.
* **Callers:** `phasesight/video.py`, `phasesight/validation.py`, `phasesight/app.py`, `tests/test_tracker.py`.
* **Callees:** `cv2.phaseCorrelate`, `cv2.createHanningWindow`, `cv2.cvtColor`.
* **Dependencies:** `opencv-python`, `numpy`.
* **Classification:** Production-path core.

#### `phasesight/analysis.py`
* **Purpose:** Spectral analysis and signal quality evaluation. Converts 1D displacement time series into power spectral densities, identifies peak vibration frequencies, computes harmonic distortion, and classifies signal validity.
* **Important Classes:**
  * `SpectrumResult`: Immutable container holding frequency grid, PSD array, dominant peak frequency, peak power, peak-to-median prominence (dB), second harmonic ratio (2X), displacement RMS ($px$), sampling rate ($f_s$), frequency resolution ($\Delta f$), and sample count.
  * `ComparisonResult`: Delta summary comparing two spectral runs.
* **Important Functions:**
  * `analyse_displacement(timestamps_s, displacement_px, min_freq=0.5, max_freq=None, nperseg=256, ...) -> SpectrumResult`: Core Welch spectral estimator. Performs gap auditing, jitter auditing, uniform resampling, linear detrending, median Welch averaging, parabolic peak interpolation, and 2X harmonic extraction.
  * `classify_signal_quality(result: SpectrumResult, min_peak_to_median_db=10.0, mean_phase_response=None, min_phase_response=0.15) -> str`: Returns `"VALID"` or `"LOW_SIGNAL"`.
  * `is_anchor_contaminated(relative_result, anchor_result, frequency_tolerance_hz=None, min_anchor_peak_to_median_db=10.0) -> bool`: Checks if the relative peak matches a dominant peak in the static anchor ROI.
  * `compare_to_baseline(baseline, current, ...) -> ComparisonResult`: Primitive percentage-based comparison between two spectra.
  * `compare_inspection_summaries(baseline: dict, current: dict, ...) -> dict`: Higher-level dictionary-based inspection comparison with noise floor evaluation.
* **Callers:** `phasesight/video.py`, `phasesight/validation.py`, `phasesight/cli.py`, `phasesight/app.py`, `tests/test_analysis.py`.
* **Callees:** `scipy.signal.welch`, `scipy.signal.detrend`, `numpy.interp`.
* **Dependencies:** `scipy`, `numpy`.
* **Classification:** Production-path core.

#### `phasesight/video.py`
* **Purpose:** Offline video decoding and inspection orchestration. Reads video containers, manages hardware PTS vs explicit FPS override synthesis, runs frame-by-frame tracking, verifies temporal stability, executes spectral analysis, and exports motion CSV, spectrum PNG, and summary JSON.
* **Important Functions:**
  * `parse_roi(value: str) -> ROI`: Parses `"x,y,w,h"` string into an `ROI` instance.
  * `analyse_video(video_path, target_roi, anchor_roi, output_dir, fps_override=None, ...) -> dict`: Master offline batch analysis pipeline.
* **Callers:** `phasesight/cli.py` (`inspect` command), `phasesight/app.py` (`Run Vibration Analysis`), test harness.
* **Callees:** `cv2.VideoCapture`, `phasesight.tracker.PhaseCorrelationTracker`, `phasesight.analysis.analyse_displacement`, `phasesight.capture.calculate_timestamp_stability`.
* **Dependencies:** `opencv-python`, `numpy`, `matplotlib`.
* **Classification:** Production-path core.

#### `phasesight/capture.py`
* **Purpose:** Camera acquisition, hardware timestamping, timing regularity quantification, and synthetic stream mocking.
* **Important Classes:**
  * `CaptureStabilityReport`: Comprehensive quantitative audit of frame intervals ($\Delta t$), jitter ratios, dropped frames, and stability status (`STABLE`, `WARNING_JITTER`, `REJECTED_UNSTABLE`, `ASSUMED_UNIFORM`).
  * `CaptureResult`: Buffered uint8 frame array, timestamp array, stability report, and optional saved MP4 file path.
  * `MockVideoCapture`: Deterministic duck-typed OpenCV capture source simulating camera frames, sinusoidal vibration, dropped frames, and timestamp jitter.
* **Important Functions:**
  * `calculate_timestamp_stability(timestamps_s, nominal_fps=30.0, ...) -> CaptureStabilityReport`: Analyzes monotonicity, intervals, jitter ratio ($\text{std} / \text{median}$), robust MAD jitter, and dropped frame gaps ($>1.5\times$ and $>2.5\times$ median $\Delta t$).
  * `open_capture_source(source, fps=30.0)`: Opens device index, file path, or `'mock:0'`.
  * `grab_preview_frame(source, warmup_frames=2) -> np.ndarray`: Grabs a single frame after flushing driver buffer lag.
  * `capture_live_clip(source, duration_s=5.0, target_fps=30.0, output_path=None, ...) -> CaptureResult`: Records bounded live clips using high-resolution monotonic timestamps (`time.perf_counter()`).
* **Callers:** `phasesight/app.py`, `phasesight/cli.py` (`capture`), `tests/test_capture.py`.
* **Callees:** `cv2.VideoCapture`, `cv2.VideoWriter`, `time.perf_counter`.
* **Dependencies:** `opencv-python`, `numpy`.
* **Classification:** Production-path core.

#### `phasesight/baseline.py`
* **Purpose:** Statistical baseline aggregation and two-stage screening engine. Aggregates $N \ge 3$ healthy inspection runs into an immutable `BaselineRecord` using Median and MAD, and screens candidate runs using robust z-scores.
* **Important Classes:**
  * `FeatureStats`: Container for median, MAD, scale factor ($1.4826$), epsilon, sample count, and raw values.
  * `AxisBaseline`: Bundle of `FeatureStats` for frequency, RMS displacement, peak prominence dB, and 2X harmonic ratio.
  * `BaselineRecord`: Complete asset baseline record with ROI geometry, sampling rate, and both axis baselines.
  * `FeatureDeviation`: Standardized deviation score ($z_{\text{robust}}$) for a feature.
  * `BaselineEvaluation`: Complete screening evaluation output (`status`: `"Normal"`, `"Review"`, or `"Low confidence"`).
* **Important Functions:**
  * `compute_robust_stats(values, epsilon, scale_factor=1.4826) -> FeatureStats`: Calculates sample median and scaled MAD.
  * `build_baseline(runs: list[dict], asset_id, min_runs=3, ...) -> BaselineRecord`: Aggregates runs, enforcing ROI spatial consistency ($\le 2\text{ px}$) and sampling rate consistency ($\le 2\%$).
  * `evaluate_run_against_baseline(current: dict, baseline: BaselineRecord, z_threshold=3.0, axis="both") -> BaselineEvaluation`: Evaluates run through Confidence Gate (ROI match, valid signal) and Review Gate ($|z| \ge 3.0$).
* **Callers:** `phasesight/storage.py`, `phasesight/cli.py` (`build-baseline`, `assess`), `phasesight/app.py`, `tests/test_baseline.py`.
* **Dependencies:** `numpy`.
* **Classification:** Production-path core.

#### `phasesight/storage.py`
* **Purpose:** Relational SQLite and compressed NPZ persistence manager.
* **Important Classes:**
  * `AssetRecord`: Asset metadata, nominal RPM, expected FPS, target ROI, anchor ROI.
  * `StoredBaseline`: Database representation of a `BaselineRecord`.
  * `InspectionRunRecord`: Persisted inspection run metadata and summary JSON.
  * `ReviewEventRecord`: Operator audit assessment, notes, and evidence.
  * `RunArrays`: Numerical time series and PSD arrays saved via `np.savez_compressed`.
  * `StorageManager`: Thread-safe database connection manager and file coordinator.
* **Important Functions:**
  * `create_connection(db_path) -> sqlite3.Connection`: Connects with `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = WAL`, `PRAGMA synchronous = NORMAL`.
  * `init_schema(conn)`: Idempotently creates tables (`assets`, `baselines`, `inspection_runs`, `review_events`) and indices.
* **Callers:** `phasesight/app.py`, `phasesight/cli.py` (`asset`, `db-info`), `tests/test_storage.py`.
* **Dependencies:** `sqlite3`, `numpy`.
* **Classification:** Production-path core.

#### `phasesight/synthetic.py`
* **Purpose:** Mathematical ground-truth simulation of vibrating targets, rigid camera shake, illumination flicker, and sensor noise.
* **Important Classes:** `SyntheticConfig`.
* **Important Functions:**
  * `make_scene(config: SyntheticConfig) -> tuple[np.ndarray, np.ndarray]`: Synthesizes video frames and 1D true relative displacement arrays.
  * `write_video(path, frames, fps)`: Writes synthesized frames to MP4.
* **Callers:** `phasesight/validation.py`, `phasesight/capture.py` (`MockVideoCapture`), `phasesight/cli.py` (`generate-synthetic`), test harness.
* **Dependencies:** `opencv-python`, `numpy`.
* **Classification:** Validation & synthetic simulation engine.

#### `phasesight/validation.py`
* **Purpose:** Automated protocol verification suite implementing the Proposal Validation Matrix protocols (T1 to T6).
* **Important Functions:**
  * `validate_t1_synthetic_motion()`: Protocol T1 (Clean & harmonic recovery).
  * `validate_t2_static_negative_control()`: Protocol T2 (Null control & noise floor).
  * `validate_t3_camera_shake_cancellation()`: Protocol T3 (Anchor subtraction efficacy).
  * `validate_t4_baseline_repeatability()`: Protocol T4 (Multi-run baseline repeatability).
  * `validate_t5_controlled_change_detection()`: Protocol T5 (Baseline vs. changed run detection).
  * `validate_t6_image_quality_stress()`: Protocol T6 (Texture loss, blur, flicker, dropped frames).
  * `run_full_validation_matrix() -> dict`: Master runner executing T1–T6.
  * `run_validation_suite() -> list[dict]`: Legacy 4-case synthetic validation suite.
* **Callers:** `phasesight/cli.py` (`validate`), `tests/test_validation_matrix.py`, `tests/test_validation_suite.py`.
* **Dependencies:** `numpy`, `phasesight` core.
* **Classification:** Validation & verification test harness.

#### `phasesight/cli.py`
* **Purpose:** Command-line interface exposing all measurement, validation, baseline, storage, and capture tools.
* **Callers:** Terminal users, automated test harness (`tests/`).
* **Classification:** Production-path interface.

#### `phasesight/app.py`, `ui_helpers.py`, `ui_styles.py`, `ui_tokens.py`, `ui_viewport.py`, `ui_fonts.py`
* **Purpose:** Streamlit-based graphical user interface implementing the Spectral Observatory precision scientific workstation.
* **Classification:** Current frontend interface layer.

### 2.3 Unused, Overlapping, and Disconnected Code
1. **`phasesight/analysis.py:compare_to_baseline` vs `compare_inspection_summaries` vs `phasesight/baseline.py:evaluate_run_against_baseline`:**
   * `compare_to_baseline` is an early Phase 1 primitive comparing two raw `SpectrumResult` objects using arbitrary 25% and 50% percentage thresholds.
   * `compare_inspection_summaries` is a Phase 2 dictionary-based comparator that adds noise floor checking.
   * `evaluate_run_against_baseline` is the production Phase 4 robust z-score statistical engine.
   * *Status:* `compare_to_baseline` is legacy and superseded by `phasesight/baseline.py`.
2. **`phasesight/validation.py:run_validation_suite` vs `run_full_validation_matrix`:**
   * `run_validation_suite` runs a legacy 4-case synthetic test.
   * `run_full_validation_matrix` runs the formal 6-protocol (T1–T6) matrix.
   * *Status:* Legacy suite maintained solely for backward compatibility with `phasesight validate --legacy`.
3. **`tools/rotor_dataset_benchmark/`:**
   * Contains standalone research scripts (`phase1_dataset_inventory.py`, `phase2_sensor_analysis.py`, `benchmark_suite.py`, `phase6_rampup_analysis.py`).
   * *Status:* Non-production research harness used to validate against Mendeley dataset 47y7rwc2yg.1.

---

# SECTION 3 — COMPLETE CURRENT ARCHITECTURE

### 3.1 Master System Architecture
```mermaid
graph TD
    subgraph Inputs["Acquisition & Ingestion"]
        V_FILE["Stored Video File (MP4/AVI)"]
        UVC_CAM["Local Physical Camera (cv2.VideoCapture)"]
        MOCK_CAM["Synthetic Stream (MockVideoCapture 'mock:0')"]
    end

    subgraph Capture_Module["phasesight/capture.py"]
        CAP_LIVE["capture_live_clip()"]
        STAB_AUDIT["calculate_timestamp_stability()"]
        PREVIEW["grab_preview_frame()"]
    end

    subgraph Tracking_Module["phasesight/tracker.py"]
        ROI_VAL["validate_rois() & check_roi_texture()"]
        TRACKER["PhaseCorrelationTracker"]
        HANN["cv2.createHanningWindow()"]
        PHASE_CORR["cv2.phaseCorrelate()"]
        DIFF["relative_dx = target_dx - anchor_dx<br/>relative_dy = target_dy - anchor_dy"]
    end

    subgraph Analysis_Module["phasesight/analysis.py"]
        TIME_GATE["Jitter & Gap Rejection Gate"]
        RESAMPLE["Uniform Resampling (np.interp)"]
        DETREND["Linear Detrending (signal.detrend)"]
        WELCH["Welch PSD (signal.welch, median)"]
        PEAK_EXT["3-Bin Parabolic Peak Localization"]
        HARM_EXT["2X Harmonic Prominence & Power Ratio"]
        QUAL_CLASS["classify_signal_quality() & is_anchor_contaminated()"]
    end

    subgraph Baseline_Module["phasesight/baseline.py"]
        BUILD_BASE["build_baseline() (N >= 3, Median & MAD)"]
        CONF_GATE["Confidence Gate (ROI match, Valid signal)"]
        REV_GATE["Review Gate (Robust z-score >= 3.0)"]
    end

    subgraph Storage_Module["phasesight/storage.py"]
        SQLITE[("SQLite Database: phasesight.db<br/>assets, baselines, runs, review_events")]
        NPZ_STORE["NumPy Compressed NPZ Archives<br/>data/storage/npz/"]
    end

    subgraph Interfaces["User Interfaces"]
        CLI["CLI: phasesight (inspect, validate, baseline, asset)"]
        STREAMLIT["Streamlit Workbench: phasesight/app.py"]
    end

    V_FILE --> TRACKER
    UVC_CAM --> CAP_LIVE
    MOCK_CAM --> CAP_LIVE
    CAP_LIVE --> STAB_AUDIT
    CAP_LIVE -->|Saved MP4| TRACKER

    TRACKER --> ROI_VAL
    TRACKER --> HANN
    TRACKER --> PHASE_CORR
    PHASE_CORR --> DIFF
    DIFF --> TIME_GATE

    TIME_GATE --> RESAMPLE
    RESAMPLE --> DETREND
    DETREND --> WELCH
    WELCH --> PEAK_EXT
    PEAK_EXT --> HARM_EXT
    HARM_EXT --> QUAL_CLASS

    QUAL_CLASS --> BUILD_BASE
    QUAL_CLASS --> CONF_GATE
    CONF_GATE --> REV_GATE

    BUILD_BASE --> SQLITE
    REV_GATE --> SQLITE
    DIFF --> NPZ_STORE
    WELCH --> NPZ_STORE

    SQLITE <--> STREAMLIT
    SQLITE <--> CLI
    NPZ_STORE <--> STREAMLIT
```

---

### 3.2 Pipeline Execution Traces

#### Pipeline A: Uploaded Video Analysis (`phasesight/video.py:analyse_video`)
```mermaid
sequenceDiagram
    autonumber
    participant U as User / UI / CLI
    participant V as video.py (analyse_video)
    participant C as OpenCV VideoCapture
    participant T as PhaseCorrelationTracker
    participant A as analysis.py (analyse_displacement)
    participant O as Disk Storage (CSV, PNG, JSON)

    U->>V: video_path, target_roi, anchor_roi, fps_override
    V->>C: cv2.VideoCapture(video_path)
    V->>C: Read frame 0 (reference frame)
    V->>T: PhaseCorrelationTracker(first_frame, target_roi, anchor_roi)
    T->>T: Check initial texture std >= 2.0 (Target & Anchor)
    T->>T: Precompute Hanning windows
    loop Every subsequent frame i = 1 .. N
        V->>C: Read frame i
        V->>V: Determine timestamp t_i (explicit override or POS_MSEC)
        V->>T: tracker.process(frame, t_i)
        T->>T: Check frame texture std >= 2.0
        T->>T: cv2.phaseCorrelate(target_ref, target_crop)
        T->>T: cv2.phaseCorrelate(anchor_ref, anchor_crop)
        T->>T: Check response >= 0.150
        T->>T: Compute relative_dx = target_dx - anchor_dx
        T-->>V: MotionSample(valid=True/False)
    end
    V->>V: Evaluate tracking quality gate (Reject if any sample invalid)
    V->>V: Evaluate timestamp stability (CaptureStabilityReport)
    V->>A: analyse_displacement(timestamps, relative_dx)
    A->>A: Verify dt > 0, gaps <= 1.5x, jitter <= 15%
    A->>A: Linear detrend, Hann Welch PSD, 3-bin peak, 2X harmonic
    A-->>V: SpectrumResult (X axis)
    V->>A: analyse_displacement(timestamps, relative_dy)
    A-->>V: SpectrumResult (Y axis)
    V->>A: is_anchor_contaminated(relative, anchor)
    V->>O: Write motion CSV, spectrum PNG, summary JSON
    V-->>U: Return summary dictionary
```

#### Pipeline B: Local Camera Preview (`phasesight/capture.py:grab_preview_frame`)
* **Entry:** User opens Streamlit or triggers preview.
* **Execution:** Calls `cv2.VideoCapture(source)`.
* **Buffer Flush:** Reads and discards 2 warmup frames (`cap.read()`) to clear stale driver buffer frames.
* **Frame Grab:** Reads 1 current frame, validates non-empty `float32`, releases capture source.
* **Processing:** Displays frame in viewport with `draw_rois_on_frame`. No tracking or FFT is performed.

#### Pipeline C: Bounded Live Recording (`phasesight/capture.py:capture_live_clip`)
* **Entry:** User clicks "Start Live Capture" in UI or runs `phasesight capture`.
* **Execution:** Bounded capture loop for `duration_s` (typically 5.0 to 10.0 seconds).
* **Timestamps:** Assigned via `time.perf_counter() - t0` upon arrival of each frame in Python space.
* **Encoding:** Buffered frames are encoded into an MP4 file on disk using OpenCV `VideoWriter` (`mp4v` codec) at the measured frame rate.
* **Batch Transfer:** Returns `CaptureResult(frames, timestamps_s, stability, video_path)`.
* **Result Generation:** Bounded capture **only records the video**. To perform vibration analysis, the saved MP4 file is passed into Pipeline A (`analyse_video`).

#### Pipeline D: Experimental Live Tracking / Oscilloscope Mode
* **Status in Codebase:** **NOT IMPLEMENTED.**
* **Audit Finding:** The repository contains no real-time rolling-window tracking loop, no rolling Welch PSD, and no live oscilloscope trace component.
* **Clarification:** `phasesight/app.py` previously contained a button labeled `btn_start_live_stream` in earlier exploratory prototypes; in the current verified implementation, this button triggers `capture_live_clip()`, which records a bounded clip to disk before triggering standard offline batch analysis.

#### Pipeline E: Synthetic `mock:0` Capture
* **Entry:** User specifies `mock:0` as the capture device source.
* **Execution:** `open_capture_source("mock:0")` instantiates `MockVideoCapture`.
* **Frame Generation:** Uses `phasesight.synthetic.make_scene` to produce deterministic frames containing a known carrier frequency ($8.50\text{ Hz}$, amplitude $0.35\text{ px}$) and camera shake.
* **Timing Emulation:** Synthesizes arrival timestamps with nominal frame intervals ($1/f_{\text{nom}}$) plus optional configurable Gaussian jitter (`jitter_ms`).
* **Output:** Saves synthetic MP4 and evaluates stability identically to a physical camera.

#### Pipeline F: CLI Inspection (`phasesight/cli.py:inspect`)
* **Entry:** User executes `phasesight inspect <video> --target <x,y,w,h> --anchor <x,y,w,h> --out <dir>`.
* **Execution:** Parses arguments and delegates directly to `phasesight.video.analyse_video`. Prints dominant frequency, RMS displacement, peak-to-median ratio, and quality status to stdout.

---

# SECTION 4 — ALL MATHEMATICS AND SIGNAL-PROCESSING LOGIC

### 4.1 Frame and ROI Representation
* **Coordinate System:** Standard OpenCV 2D image coordinates: origin $(0, 0)$ is at the top-left corner of the image. The X-axis extends horizontally to the right; the Y-axis extends vertically downward.
* **ROI Data Structure (`phasesight/tracker.py:ROI`):**
  $$\text{ROI} = (x, y, w, h) \quad \text{where } x, y, w, h \in \mathbb{Z}^+$$
  * Constraints: $w \ge 32$, $h \ge 32$ pixels.
  * Frame Containment: $x \ge 0, \; y \ge 0, \; x + w \le W_{\text{frame}}, \; y + h \le H_{\text{frame}}$.
  * Non-Overlap Constraint: Target ROI and Anchor ROI axis-aligned bounding boxes must not intersect:
    $$\neg \left( x_T + w_T \le x_A \lor x_A + w_A \le x_T \lor y_T + h_T \le y_A \lor y_A + h_A \le y_T \right)$$
* **Texture Contrast Validation (`check_roi_texture`):**
  For patch $I(x, y)$ cropped from grayscale frame $G$:
  $$\mu_I = \frac{1}{w \cdot h} \sum_{u=0}^{w-1} \sum_{v=0}^{h-1} I(u, v)$$
  $$\sigma_I = \sqrt{\frac{1}{w \cdot h} \sum_{u=0}^{w-1} \sum_{v=0}^{h-1} \left( I(u, v) - \mu_I \right)^2}$$
  **Threshold:** $\sigma_I \ge 2.0\text{ intensity counts}$. If $\sigma_I < 2.0$, tracking is rejected (`target_low_texture` / `anchor_low_texture`).
* **Reference Patch Retention:** The reference patches $I_{T,\text{ref}}$ and $I_{A,\text{ref}}$ are cropped from frame $t=0$ and stored as contiguous `float32` arrays. They are **never updated** during subsequent frames. This prevents cumulative position drift, but restricts valid tracking to translations that stay within the boundary of the reference patch.

---

### 4.2 2D Phase Correlation
Phase correlation estimates translation between two image patches by finding the peak of their normalized cross-power spectrum.

1. **Patch Normalization (`_normalise_patch`):**
   Before spectral transformation, the DC component is removed and contrast is scaled:
   $$\hat{I}(u, v) = \frac{I(u, v) - \mu_I}{\sigma_I + \epsilon}, \quad \epsilon = 10^{-6}$$
2. **Windowing:**
   To reduce edge discontinuity artifacts in the 2D spatial FFT, a separable 2D Hanning window $W(u, v) = w_x(u) \cdot w_y(v)$ is applied:
   $$w_x(u) = 0.5 \left( 1 - \cos\left( \frac{2\pi u}{w - 1} \right) \right), \quad w_y(v) = 0.5 \left( 1 - \cos\left( \frac{2\pi v}{h - 1} \right) \right)$$
   Applied via OpenCV: `cv2.createHanningWindow((width, height), cv2.CV_32F)`.
3. **Cross-Power Spectrum:**
   Let $F_{\text{ref}}(u, v) = \mathcal{F}\{\hat{I}_{\text{ref}} \odot W\}$ and $F_{\text{curr}}(u, v) = \mathcal{F}\{\hat{I}_{\text{curr}} \odot W\}$:
   $$R(u, v) = \frac{F_{\text{curr}}(u, v) \cdot F_{\text{ref}}^*(u, v)}{\left| F_{\text{curr}}(u, v) \cdot F_{\text{ref}}^*(u, v) \right| + \epsilon}$$
4. **Inverse Transformation & Peak Localization:**
   The spatial cross-correlation surface is $r(x, y) = \mathcal{F}^{-1}\{R(u, v)\}$.
   OpenCV's `cv2.phaseCorrelate` computes sub-pixel peak coordinates $(\Delta x, \Delta y)$ by fitting a 2D quadratic or centroid surface around the discrete maximum.
5. **Correlation Response Metric:**
   The returned scalar response $r_{\text{resp}} \in [0.0, 1.0]$ measures the relative power of the correlation peak relative to background correlation energy:
   **Threshold:** `min_response = 0.150`. If $r_{\text{resp}} < 0.150$, the sample is rejected as an invalid measurement (`target_low_response` / `anchor_low_response`).

---

### 4.3 Target and Anchor Differential Motion
* **Raw Measurements:** Target translation $(x_T(t), y_T(t))$ and Anchor translation $(x_A(t), y_A(t))$ in pixels.
* **Differential Motion Equation (`phasesight/tracker.py:211-212`):**
  $$x_{\text{rel}}(t) = x_T(t) - x_A(t)$$
  $$y_{\text{rel}}(t) = y_T(t) - y_A(t)$$
* **Physical Assumptions & Breakdown Modes:**
  * **Compensated Effects:** Pure rigid 2D planar camera translation parallel to the image sensor plane ($\Delta X_{\text{cam}}, \Delta Y_{\text{cam}}$). Because both ROIs share the identical camera translation, subtraction cancels the nuisance motion:
    $$x_T(t) = x_{\text{vib}}(t) + \Delta X_{\text{cam}}(t), \quad x_A(t) = \Delta X_{\text{cam}}(t) \implies x_{\text{rel}}(t) = x_{\text{vib}}(t)$$
  * **UNCOMPENSATED Effects (Known Failure Modes):**
    1. **Camera Roll / Rotation ($\theta_z$):** Rotational motion introduces tangential displacement proportional to the distance from the optical center. If Target and Anchor are at different radii, subtraction leaves large residual errors: $\Delta x_{\text{res}} \approx -\theta_z \cdot (y_T - y_A) \ne 0$.
    2. **Out-of-Plane Tilt / Pitch / Yaw ($\theta_x, \theta_y$):** Introduces perspective warping across the field of view.
    3. **Optical Parallax:** If the target and anchor are at different working distances from the camera ($Z_T \ne Z_A$), identical camera translation produces different pixel displacements ($\Delta x_T \propto 1/Z_T \ne \Delta x_A \propto 1/Z_A$).
    4. **Mechanically Vibrating Anchor:** If the anchor is mounted on a flexible machine shroud or vibrating foundation, $x_A(t)$ contains machine vibration, causing spectral contamination (flagged by `is_anchor_contaminated`).

---

### 4.4 Temporal Sampling and Timestamps
* **Timestamp Precedence Hierarchy (`phasesight/video.py:95-127`):**
  1. **Explicit FPS Override (`--fps <float>`):**
     Highest priority. Completely overrides container headers. Timestamps are synthesized:
     $$t_i = \frac{i}{\text{fps}_{\text{override}}}, \quad i = 1, 2, \dots, N$$
     Source string: `"explicit_fps_override"`. Stability status: `"ASSUMED_UNIFORM"`.
  2. **Hardware/Container Presentation Timestamps (PTS):**
     Used when no override is passed and container returns advancing timestamps:
     $$t_i = \frac{\text{POS\_MSEC}_i - \text{POS\_MSEC}_0}{1000.0}$$
     Source string: `"container_pts"`.
  3. **Inferred Constant Frame Rate Fallback:**
     Used when container PTS is frozen, non-advancing, or returning constant zeroes:
     $$t_i = \frac{i}{\text{fps}_{\text{meta}}}$$
     Source string: `"inferred_cfr_fallback"`.
* **Timing Regularity Quantification (`calculate_timestamp_stability`):**
  Given arrival intervals $\Delta t_i = t_i - t_{i-1}$:
  * Median frame interval: $\Delta t_{\text{med}} = \text{median}(\Delta t)$
  * Measured sampling rate: $f_s = 1.0 / \Delta t_{\text{med}}$
  * Classical Jitter Ratio: $J_{\text{std}} = \frac{\text{std}(\Delta t)}{\Delta t_{\text{med}}}$
  * Robust MAD Jitter Ratio: $J_{\text{mad}} = \frac{1.4826 \cdot \text{median}\left( |\Delta t - \Delta t_{\text{med}}| \right)}{\Delta t_{\text{med}}}$
  * Dropped Frames: Intervals with $\Delta t_i / \Delta t_{\text{med}} > 1.5$. Number of dropped frames estimated as $\text{round}(\Delta t_i / \Delta t_{\text{med}}) - 1$.
  * Large Gaps: Intervals with $\Delta t_i / \Delta t_{\text{med}} > 2.5$.
* **Stability Classification Statuses:**
  * `"STABLE"`: $J_{\text{eff}} < 0.05$ (5%) and dropped frames $= 0$ and large gaps $= 0$.
  * `"WARNING_JITTER"`: $0.05 \le J_{\text{eff}} < 0.15$ or dropped frames $> 0$ (up to 3).
  * `"REJECTED_UNSTABLE"`: $J_{\text{eff}} \ge 0.15$ (15%) or dropped frames $> 3$ or large gaps $> 0$ or non-monotonic timestamps ($\Delta t_i \le 0$) or $N < 32$.
  * `"ASSUMED_UNIFORM"`: Assigned when timestamps are mathematically synthesized from explicit FPS override.

---

### 4.5 Signal Preprocessing
1. **Rejection Gates:**
   * Length check: $N \ge 32$ samples required.
   * Finiteness check: Arrays must contain zero NaN or $\pm\infty$ values.
   * Monotonicity check: $t_i > t_{i-1}$ strictly.
   * Maximum Gap Ratio Gate: If $\max(\Delta t) / \Delta t_{\text{med}} > 1.5$, raises `ValueError`.
   * Maximum Jitter Gate: If $\text{std}(\Delta t) / \Delta t_{\text{med}} > 0.15$, raises `ValueError`.
2. **Uniform Resampling (`np.interp`):**
   Welch spectral analysis requires strictly uniform time steps. If minor jitter is present ($J_{\text{std}} > 0.002$ or not `allclose` within 0.2%):
   $$t_{\text{uniform}} = \text{linspace}(t_0, t_{N-1}, N)$$
   $$x_{\text{uniform}} = \text{interp}(t_{\text{uniform}}, t, x)$$
   $$f_s = \frac{N - 1}{t_{N-1} - t_0}$$
3. **Linear Detrending:**
   Removes DC component and linear thermal/optical drift:
   $$x_{\text{detrended}}(t) = x(t) - (\hat{\alpha} t + \hat{\beta})$$
   Calculated via SciPy: `signal.detrend(x, type="linear")`.

---

### 4.6 RMS Displacement
Root-Mean-Square displacement measures vibration energy in pixels:
$$\text{RMS}_{px} = \sqrt{\frac{1}{N} \sum_{i=0}^{N-1} \left( x_{\text{detrended}}[i] \right)^2}$$
* **Zero-Mean Property:** Because linear detrending is performed immediately prior to RMS calculation, $\mu_x \equiv 0$, making $\text{RMS}_{px}$ identically equal to the sample standard deviation $\sigma_x$.
* **Units:** Strictly image pixels ($px$).

---

### 4.7 Welch Power Spectral Density
Computed via SciPy `scipy.signal.welch`:
* **Parameters:**
  * Segment length: $N_{\text{seg}} = \min(\max(32, \text{nperseg}), N)$. Default $\text{nperseg} = 256$.
  * Window: Periodic Hann window $w[n] = 0.5 \left(1 - \cos\left(\frac{2\pi n}{N_{\text{seg}}}\right)\right)$.
  * Overlap: $50\%$ ($N_{\text{overlap}} = N_{\text{seg}} // 2$).
  * Segment Detrending: `"constant"` (removes mean of each segment).
  * Scaling: `"density"` (Power Spectral Density in $\text{px}^2 / \text{Hz}$).
  * Averaging: `"median"` (Robust Welch averaging using the median of segment periodograms rather than the mean, suppressing transient burst outliers).
* **Discrete Frequency Resolution:**
  $$\Delta f_{\text{bin}} = \frac{f_s}{N_{\text{seg}}}$$
* **Analysis Band:**
  $$f_{\min} = 0.5\text{ Hz}, \quad f_{\max} = \min(\text{user\_max}, 0.90 \cdot f_{\text{Nyquist}}, 0.95 \cdot f_{\text{Nyquist}})$$

---

### 4.8 Peak Extraction & Harmonic Detection
1. **Discrete Peak Selection:**
   Within the band $[f_{\min}, f_{\max}]$, locate the maximum PSD bin:
   $$k_{\text{peak}} = \arg\max_{k \in \text{band}} \text{PSD}[k], \quad f_{\text{discrete}} = k_{\text{peak}} \cdot \Delta f_{\text{bin}}$$
2. **Spectral Prominence (Peak-to-Median Ratio in dB):**
   Background noise floor $\text{PSD}_{\text{bg}}$ is computed by taking the median of all bins in the band excluding a $\pm 2$-bin guard band around $k_{\text{peak}}$:
   $$\text{Prominence}_{\text{dB}} = 10 \log_{10} \left( \frac{\max(\text{PSD}[k_{\text{peak}}], 10^{-30})}{\max(\text{median}(\text{PSD}_{\text{bg}}), 10^{-30})} \right)$$
3. **Logarithmic Parabolic Interpolation:**
   Sub-bin continuous frequency refinement using a 3-bin parabolic fit on log-power:
   $$y_0 = \ln(\text{PSD}[k_{\text{peak}} - 1]), \quad y_1 = \ln(\text{PSD}[k_{\text{peak}}]), \quad y_2 = \ln(\text{PSD}[k_{\text{peak}} + 1])$$
   $$\delta = \text{clip}\left( \frac{0.5 (y_0 - y_2)}{y_0 - 2y_1 + y_2}, -1.0, 1.0 \right)$$
   $$f_{\text{dominant}} = (k_{\text{peak}} + \delta) \cdot \Delta f_{\text{bin}}$$
4. **Second Harmonic (2X) Extraction:**
   * Target frequency: $f_{2X} = 2.0 \cdot f_{\text{dominant}}$.
   * Bandwidth: $\pm \max(1.5 \cdot \Delta f_{\text{bin}}, 0.15\text{ Hz})$.
   * Strict Local Maximum Criterion: Candidate bin must strictly exceed both immediate neighbors: $\text{PSD}[k] > \text{PSD}[k-1] \land \text{PSD}[k] > \text{PSD}[k+1]$.
   * Local Background: Evaluated in a $\pm 3.0\text{ Hz}$ window excluding the 2X candidate and 1X fundamental peaks.
   * Prominence Threshold: Candidate must exhibit $\ge 10.0\text{ dB}$ local prominence.
   * Harmonic Power Ratio:
     $$\text{Ratio}_{2X} = \frac{\sum_{k \in \text{band}_{2X}} \text{PSD}[k]}{\sum_{k \in \text{band}_{1X}} \text{PSD}[k]}$$
     If criteria are not met, $\text{Ratio}_{2X}$ is assigned `None`.

---

### 4.9 Signal-Quality Classification
Evaluated per spatial axis (X and Y):
1. **Contamination Check (`is_anchor_contaminated`):**
   * Compares dominant relative peak $f_{\text{rel}}$ against dominant anchor peak $f_{\text{anchor}}$.
   * Tolerance: $\Delta f = \max(\Delta f_{\text{res, rel}}, \Delta f_{\text{res, anchor}})$.
   * Flagged if: $|f_{\text{rel}} - f_{\text{anchor}}| \le \Delta f$ AND $\text{Prominence}_{\text{anchor}} \ge 10.0\text{ dB}$.
   * Result: Status set to `"CONTAMINATED"`.
2. **Prominence & Phase Response Gate (`classify_signal_quality`):**
   * Checks if $\text{Prominence}_{\text{dB}} < 10.0\text{ dB} \implies$ `"LOW_SIGNAL"`.
   * Checks if $\text{mean}(r_{\text{resp}}) < 0.150 \implies$ `"LOW_SIGNAL"`.
   * Otherwise $\implies$ `"VALID"`.

---

### 4.10 Baseline Mathematics & Robust Deviation Scoring
* **Quorum Requirement:** $N \ge 3$ healthy inspection runs required to build a baseline.
* **Spatial & Acquisition Consistency Checks:**
  * Target ROI coordinates must match Run 1 within $\pm 2$ pixels: $|x_i - x_1| \le 2, |y_i - y_1| \le 2, |w_i - w_1| \le 2, |h_i - h_1| \le 2$.
  * Anchor ROI coordinates must match Run 1 within $\pm 2$ pixels.
  * Sampling rate must match Run 1 within $\pm 2\%$: $|f_{s, i} - f_{s, 1}| / f_{s, 1} \le 0.02$.
  * Quality Admission: At least one axis must be consistently `"VALID"` across all $N$ runs.
* **Robust Scale Estimator (Median and Scaled MAD):**
  Given baseline run observations $X = \{x_1, x_2, \dots, x_N\}$:
  $$\text{Median}(X) = \text{med}(X)$$
  $$\text{MAD}(X) = \text{med}\left( |x_i - \text{med}(X)| \right)$$
  $$\text{Scale Factor } k = 1.482602218505602 \quad (\text{ensures } k \cdot \text{MAD} \to \sigma \text{ for normal distributions})$$
* **Floor Epsilon Regularization:**
  To prevent division by zero when runs are identical (zero MAD):
  $$\epsilon_{\text{freq}} = 0.020\text{ Hz}, \quad \epsilon_{\text{RMS}} = 0.005\text{ px}, \quad \epsilon_{\text{prom}} = 1.000\text{ dB}, \quad \epsilon_{\text{harm}} = 0.010$$
* **Robust Z-Score Calculation:**
  $$z_{\text{robust}} = \frac{x_{\text{current}} - \text{Median}(X)}{1.4826 \cdot \text{MAD}(X) + \epsilon}$$
* **Two-Stage Screening Evaluation:**
  1. **Stage 1 — Confidence Gate:** Checks if current ROI geometry matches baseline within $\pm 2\text{ px}$ and current signal quality is `"VALID"`. If failed $\implies$ Status = `"Low confidence"`.
  2. **Stage 2 — Review Gate:** If Confidence Gate passes, evaluates $z_{\text{robust}}$ across all features. If any $|z_{\text{robust}}| \ge 3.0$ ($z$-threshold) $\implies$ Status = `"Review"`. If all $|z_{\text{robust}}| < 3.0 \implies$ Status = `"Normal"`.

---

# SECTION 5 — DATA STRUCTURES AND PERSISTENCE

### 5.1 Relational SQLite Schema (`phasesight.db`)
Database initialized by `phasesight/storage.py:init_schema`. Pragmas enforced: `PRAGMA foreign_keys = ON; PRAGMA journal_mode = WAL; PRAGMA synchronous = NORMAL;`.

```sql
CREATE TABLE IF NOT EXISTS assets (
    asset_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    nominal_speed_rpm REAL,
    target_roi_json TEXT NOT NULL,
    anchor_roi_json TEXT NOT NULL,
    expected_fps REAL NOT NULL CHECK (expected_fps > 0),
    scale_calibration_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS baselines (
    baseline_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    run_count INTEGER NOT NULL CHECK (run_count >= 1),
    camera_settings_json TEXT NOT NULL DEFAULT '{}',
    baseline_record_json TEXT NOT NULL,
    npz_rel_path TEXT,
    notes TEXT NOT NULL DEFAULT '',
    version TEXT NOT NULL DEFAULT '1.0'
);

CREATE TABLE IF NOT EXISTS inspection_runs (
    run_id TEXT PRIMARY KEY,
    asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
    baseline_id TEXT REFERENCES baselines(baseline_id) ON DELETE SET NULL,
    timestamp TEXT NOT NULL,
    video_path TEXT NOT NULL,
    measured_fps REAL NOT NULL CHECK (measured_fps > 0),
    duration_s REAL NOT NULL CHECK (duration_s >= 0),
    frames_analysed INTEGER NOT NULL CHECK (frames_analysed >= 0),
    valid_patch_ratio REAL NOT NULL DEFAULT 1.0,
    npz_rel_path TEXT,
    summary_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'Unassessed'
);

CREATE TABLE IF NOT EXISTS review_events (
    event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES inspection_runs(run_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('Normal', 'Review', 'Low confidence')),
    triggered_features_json TEXT NOT NULL DEFAULT '[]',
    operator_note TEXT NOT NULL DEFAULT '',
    evidence_image_rel_path TEXT,
    evaluation_json TEXT,
    created_at TEXT NOT NULL,
    operator_id TEXT NOT NULL DEFAULT 'operator'
);
```

### 5.2 Compressed NumPy NPZ Storage (`phasesight/storage.py:RunArrays`)
Numerical arrays are stored on disk in compressed binary format (`np.savez_compressed`):
* **Storage Path:** `<storage_root>/npz/runs/<run_id>.npz`
* **Array Dictionary Keys & Shapes:**
  * `"timestamps_s"`: `(N,) float64` — Monotonic time base in seconds.
  * `"relative_dx_px"`: `(N,) float64` — Differential X displacement in pixels.
  * `"relative_dy_px"`: `(N,) float64` — Differential Y displacement in pixels.
  * `"target_dx_px"`: `(N,) float64` — Raw target X displacement.
  * `"target_dy_px"`: `(N,) float64` — Raw target Y displacement.
  * `"anchor_dx_px"`: `(N,) float64` — Raw anchor X displacement.
  * `"anchor_dy_px"`: `(N,) float64` — Raw anchor Y displacement.
  * `"target_response"`: `(N,) float64` — Phase correlation peak response for target patch.
  * `"anchor_response"`: `(N,) float64` — Phase correlation peak response for anchor patch.
  * `"x_frequencies_hz"`: `(K,) float64` — Welch frequency bins for X axis.
  * `"x_psd_px2_per_hz"`: `(K,) float64` — Welch Power Spectral Density for X axis.
  * `"y_frequencies_hz"`: `(K,) float64` — Welch frequency bins for Y axis.
  * `"y_psd_px2_per_hz"`: `(K,) float64` — Welch Power Spectral Density for Y axis.

### 5.3 Inspection Summary JSON Schema
Exported by `phasesight/video.py` and stored in SQLite `inspection_runs.summary_json`:
```json
{
  "video": "data/portable/baseline.mp4",
  "fps_used": 60.0,
  "frames_analysed": 600,
  "duration_s": 9.983,
  "timestamp_source": "explicit_fps_override",
  "timebase_source": "explicit_fps_override",
  "temporal_stability": {
    "total_frames": 600,
    "duration_s": 9.983,
    "nominal_fps": 60.0,
    "measured_fps": 60.0,
    "median_dt_s": 0.016667,
    "mean_dt_s": 0.016667,
    "std_dt_s": null,
    "min_dt_s": 0.016667,
    "max_dt_s": 0.016667,
    "jitter_ratio": null,
    "robust_jitter_ratio": null,
    "dropped_frames_count": null,
    "dropped_frame_indices": [],
    "large_gap_count": 0,
    "status": "ASSUMED_UNIFORM",
    "status_reasons": ["Timestamps were synthesized from an explicit FPS override."]
  },
  "target_roi_xywh": {"x": 360, "y": 110, "width": 160, "height": 160},
  "anchor_roi_xywh": {"x": 60, "y": 100, "width": 160, "height": 160},
  "x_axis": {
    "dominant_frequency_hz": 8.509,
    "rms_displacement_px": 0.2325,
    "peak_to_median_db": 15.42,
    "signal_quality": "VALID",
    "anchor_dominant_frequency_hz": 0.701,
    "anchor_peak_to_median_db": 2.14,
    "target_dominant_frequency_hz": 8.509,
    "second_harmonic_ratio": 0.0003,
    "frequency_resolution_hz": 0.2344,
    "sampling_rate_hz": 60.0
  },
  "y_axis": {
    "dominant_frequency_hz": 0.701,
    "rms_displacement_px": 0.0121,
    "peak_to_median_db": 2.45,
    "signal_quality": "LOW_SIGNAL",
    "anchor_dominant_frequency_hz": 0.701,
    "anchor_peak_to_median_db": 2.14,
    "target_dominant_frequency_hz": 0.701,
    "second_harmonic_ratio": null,
    "frequency_resolution_hz": 0.2344,
    "sampling_rate_hz": 60.0
  },
  "mean_min_phase_correlation_response": 0.892,
  "interpretation": "Screening measurement in pixels; not a calibrated vibration diagnosis.",
  "quality_notes": {
    "CONTAMINATED": "A strong peak at the same frequency appears in the anchor ROI...",
    "LOW_SIGNAL": "No sufficiently prominent, reliable vibration peak was found..."
  },
  "outputs": {
    "csv": "output/baseline/baseline_motion.csv",
    "plot": "output/baseline/baseline_spectrum.png",
    "summary": "output/baseline/baseline_summary.json"
  }
}
```

---

# SECTION 6 — CLI AND APPLICATION INTERFACES

### 6.1 CLI Command Reference
The CLI is invoked via `phasesight <command>`:

| Command | Purpose | Required Arguments | Optional Flags & Defaults | Backing Functions |
|---|---|---|---|---|
| `validate` | Execute synthetic validation matrix | None | `--test {all,T1..T6}` (default: all)<br/>`--legacy` (4-case suite)<br/>`--json <path>` | `validation.py:run_full_validation_matrix`<br/>`validation.py:run_validation_suite` |
| `inspect` | Measure video file via phase correlation | `video`, `--target x,y,w,h`, `--anchor x,y,w,h` | `--out <dir>` (default: phasesight_output)<br/>`--fps <float>` (override)<br/>`--min-frequency` (0.5)<br/>`--max-frequency`<br/>`--nperseg` (256) | `video.py:analyse_video` |
| `capture` | Acquire video clip with timing stability audit | None (default source: 0) | `source` (0, mock:0, file)<br/>`--duration` (5.0s)<br/>`--fps` (30.0)<br/>`--out <mp4_path>`<br/>`--json <report_path>` | `capture.py:capture_live_clip`<br/>`capture.py:calculate_timestamp_stability` |
| `build-baseline` | Aggregate $\ge 3$ runs into a `BaselineRecord` | `runs...` ($\ge 3$ summary JSONs) | `--asset-id` (default_asset)<br/>`--min-runs` (3)<br/>`--notes` ("")<br/>`--out` (baseline.json) | `baseline.py:build_baseline`<br/>`baseline.py:serialize_baseline` |
| `assess` | Screen run against a `BaselineRecord` | `current` (JSON), `baseline` (JSON) | `--threshold` (3.0 z)<br/>`--axis {x,y,both}` (both)<br/>`--out` (assessment.json) | `baseline.py:evaluate_run_against_baseline` |
| `compare` | Compare two raw summary JSONs | `baseline` (JSON), `current` (JSON) | `--axis {x,y}` (x)<br/>`--warning-rms-change` (25%)<br/>`--alert-rms-change` (50%)<br/>`--noise-floor-summary`<br/>`--out` (comparison.json) | `analysis.py:compare_inspection_summaries` |
| `generate-synthetic` | Generate synthetic vibration MP4 | `output` (path) | `--frequency` (8.5)<br/>`--amplitude` (0.35)<br/>`--fps` (60)<br/>`--duration` (10.0)<br/>`--camera-shake` (0.65)<br/>`--noise` (1.5) | `synthetic.py:make_scene`<br/>`synthetic.py:write_video` |
| `asset create` | Register asset definition in SQLite | `name`, `--target`, `--anchor` | `--fps` (60)<br/>`--speed` (RPM)<br/>`--desc` ("")<br/>`--asset-id`<br/>`--storage-root` | `storage.py:StorageManager.create_asset` |
| `asset list` | List assets in SQLite | None | `--json`<br/>`--storage-root` | `storage.py:StorageManager.list_assets` |
| `asset show` | Display asset metadata & baseline | `asset_id` | `--json`<br/>`--storage-root` | `storage.py:StorageManager.get_asset`<br/>`storage.py:StorageManager.get_active_baseline` |
| `db-info` | Print SQLite database diagnostics | None | `--json`<br/>`--storage-root` | `storage.py:StorageManager` |
| `ui` | Launch Streamlit web interface | None | `--port` (8501)<br/>`--host` (localhost) | Subprocess launch: `streamlit run phasesight/app.py` |

### 6.2 Streamlit User Interface Workflow (`phasesight/app.py`)
* **State Management (`st.session_state`):**
  * `storage_manager`: Cached `StorageManager` instance.
  * `selected_asset_id`: Active machine asset bound from sidebar.
  * `tx_input, ty_input, tw_input, th_input`: Target ROI coordinates.
  * `ax_input, ay_input, aw_input, ah_input`: Anchor ROI coordinates.
  * `fps_override_val`: Explicit FPS override value.
  * `latest_summary`, `latest_csv_path`, `latest_run_arrays`: In-memory inspection cache.
* **Three Primary Tab Destinations:**
  1. **Inspect Tab:**
     * Section 1: Ingestion Source (Upload video, Sample video, or Webcam/Live Stream).
     * Section 2: Optical Measurement Viewport (Displays first frame with rendered bounding boxes and center crosshairs).
     * Section 3: Measurement Inspector (1-Click Presets: `Rotor Rig Preset`, `Center Rig`, `Sample Baseline`, coordinate spinbuttons, Run button, telemetry summary, and interactive Plotly spectra).
  2. **History Tab:**
     * Asset run history table from SQLite (`inspection_runs`).
     * Status filter (`All`, `Normal`, `Review`, `Low confidence`, `Unassessed`).
     * Run detail inspector: Loads compressed NPZ array from disk to render high-resolution displacement and Welch PSD plots.
     * Review Event logger: Allows operator to record notes and classification (`Normal`, `Review`, `Low confidence`).
  3. **Baselines Tab:**
     * Asset Catalog management (Create, Edit, Delete machine assets).
     * Baseline Calibration Wizard: Selects $N \ge 3$ historical runs, enforces spatial and sampling quorum, builds immutable `BaselineRecord`, and saves to SQLite and disk.
     * Stored Baseline Inspector: Displays robust feature parameters (median, MAD, $\epsilon$).
* **Separation of Concerns:** The core mathematical algorithms (`phasesight.tracker`, `phasesight.analysis`, `phasesight.baseline`, `phasesight.storage`) have zero dependencies on Streamlit. All UI code is strictly isolated in `phasesight/app.py` and `ui_*.py`.

---

# SECTION 7 — VALIDATION AND EVIDENCE

### 7.1 Automated Test Suite Inventory
The test suite consists of **129 passing automated tests** executed via Pytest (`pytest tests/ -q`):

1. **`tests/test_analysis.py` (20 tests):**
   * Welch recovery of known carrier frequencies.
   * `LOW_SIGNAL` classification for flat spectra.
   * 2X harmonic emergence and power ratio scaling.
   * Baseline percentage comparisons (`compare_to_baseline`).
   * Timestamp validation: rejection of non-monotonic, non-finite, and short arrays.
   * Nyquist aliasing verification.
   * Static anchor contamination detection (`is_anchor_contaminated`).
   * Summary dictionary comparisons and noise floor multiples.
   * Harmonic test matrix (10 distinct synthetic frequency/noise/harmonic configurations).
2. **`tests/test_baseline.py` (23 tests):**
   * Quorum rejection ($N < 3$ runs).
   * Valid 3-run baseline construction.
   * Zero-MAD numerical stability via floor epsilon.
   * Outlier breakdown point ($< 50\%$ contaminated runs rejected).
   * Confidence Gate rejections: low signal, anchor contamination, baseline contamination.
   * Full 8-combination baseline admission truth table (`test_baseline_admission_matrix`).
   * Review Gate triggers: RMS surge, frequency shift, harmonic emergence.
   * Normal run pass-through within 3.0 z bounds.
   * Tri-state second harmonic deviation logic (both None, emergence, disappearance, both present).
   * JSON serialization and deserialization fidelity.
   * ROI coordinate divergence rejection ($> 2\text{ px}$).
   * Verification against real physical portable test rig data (`data/portable/`).
3. **`tests/test_capture.py` (13 tests):**
   * Stability report generation (`CaptureStabilityReport`).
   * Boundary checks: too few frames ($<32$), non-monotonic timestamps.
   * Jitter classification: `WARNING_JITTER` ($\ge 5\%$), `REJECTED_UNSTABLE` ($\ge 15\%$).
   * Dropped frame detection: single drops, burst drops, severe acquisition stalls ($>2.5\times$).
   * `MockVideoCapture` duck-typing, frame generation, and drop simulation.
   * Preview frame capture and driver warmup flushing.
   * Bounded live recording (`capture_live_clip`) and MP4 video encoding.
   * Cancellation event handling during capture.
   * CLI `capture` subcommand execution.
4. **`tests/test_storage.py` (15 tests):**
   * Asset CRUD operations and duplicate ID handling.
   * ROI dataclass JSON round-tripping.
   * Stored baseline persistence and active baseline retrieval.
   * Inspection run archival, foreign keys, and status validation.
   * Operator review event logging and status constraints.
   * `RunArrays` compressed NPZ compression, loading fidelity, and optional array handling.
   * Foreign key cascading: asset deletion cascades to baselines and runs; baseline deletion sets null on runs.
   * Disk file cleanup upon database record deletion.
   * In-memory SQLite isolation (`:memory:`) and temporary directory creation.
   * Multi-threaded SQLite concurrency safety.
   * Idempotent schema initialization (`PRAGMA user_version`).
   * Path traversal attack prevention in NPZ relative paths.
5. **`tests/test_tracker.py` (16 tests):**
   * Sub-pixel translation recovery ($0.35\text{ px}$) and camera shake cancellation.
   * Reference patch preservation across repeated iterations.
   * Overlapping and out-of-bounds ROI validation.
   * Standard deviation texture checking (`check_roi_texture`).
   * Dynamic per-frame quality regression suite (8 tests): normal moving textured, black frame halfway, white frame halfway, gradual contrast decay, temporary texture loss and recovery, target invalid with anchor valid, anchor invalid with target valid, both invalid.
   * Non-finite float/NaN rejection.
6. **`tests/test_ui.py` (16 tests):**
   * Video metadata extraction and first frame loading.
   * Invalid video handling and UI badge formatting.
   * CSV array parsing (`run_arrays_from_csv`) and Matplotlib figure generation.
   * Streamlit app loading and headless render tests.
   * Sample clip inspection execution.
   * Dynamic asset selection and session state ROI synchronization.
   * Asset management CRUD wizard.
   * Baseline wizard quorum and validation rules.
   * History table rendering and NPZ trace loading.
   * Operator review event logging and status syncing.
   * Automatic assessment of completed runs against active baselines.
   * Live webcam preview and bounded capture UI flow.
   * Live webcam unstable timing error container blocking.
   * CLI UI launcher executable path sanitization.
7. **`tests/test_validation_matrix.py` (10 tests):**
   * Protocol T1 (Synthetic motion recovery).
   * Protocol T2 (Negative control).
   * Protocol T3 (Camera shake cancellation).
   * Protocol T4 (Baseline repeatability).
   * Protocol T5 (Controlled change detection).
   * Protocol T6 (Image-quality stress testing).
   * Master runner execution (`run_full_validation_matrix`).
   * CLI `validate` stdout formatting and JSON export.
   * CLI single protocol selection (`--test T1`).
   * CLI legacy flag (`--legacy`).
8. **`tests/test_validation_suite.py` (1 test):**
   * Deterministic legacy 4-case synthetic validation suite.
9. **`tests/test_video_pipeline.py` (15 tests):**
   * End-to-end encoded video round-trip frequency recovery.
   * Camera-only H.264 clip anchor contamination flagging.
   * Timestamp integrity suite: regular 60 FPS, minor jitter, severe jitter rejection ($>15\%$), dropped frames gap rejection ($>1.5\times$), non-monotonic rejection, repeated timestamp rejection, variable frame rate (VFR) rejection, container PTS fallback.
   * Explicit FPS override precedence over container PTS metadata.
   * Container PTS preservation when no override is passed.
   * Non-finite or negative FPS override rejection.
   * Timebase source and resolution metadata recording.
   * Explicit FPS stability contract (`ASSUMED_UNIFORM`).

---

### 7.2 Proposal Validation Matrix Protocols (T1 – T6)
Implemented in `phasesight/validation.py` and verified via `phasesight validate`:

| Protocol | Purpose | Synthetic Stimulus | Pass / Acceptance Criteria | Observed Output |
|---|---|---|---|---|
| **T1: Known Motion Recovery** | Verify sub-pixel frequency & amplitude recovery | Case 1: Pure $8.5\text{ Hz}, 0.35\text{ px}$<br/>Case 2: $8.5\text{ Hz} + 17.0\text{ Hz}$ 2X | $\Delta f \le 0.05\text{ Hz}$, $\text{RMSE} \le 0.10\text{ px}$, $r \ge 0.90$, $\text{Ratio}_{2X} > 0.04$, Status: `VALID` | **PASS** ($\Delta f = 0.009\text{ Hz}$, $\text{RMSE} = 0.051\text{ px}$, $r = 0.976$, $\text{Ratio}_{2X} = 0.058$) |
| **T2: Negative Control** | Quantify optical noise floor | Case 1: Pure static scene ($\sigma_{\text{noise}}=1.0$)<br/>Case 2: Camera shake only ($0.65\text{ px}$) | $\text{RMS} \le 0.08\text{ px}$, $\text{Prominence} < 10.0\text{ dB}$, Status: `LOW_SIGNAL` | **PASS** ($\text{RMS} = 0.021\text{ px}$, $\text{Prominence} = 2.1\text{ dB}$, Status: `LOW_SIGNAL`) |
| **T3: Camera Shake Control** | Evaluate anchor subtraction efficacy | $8.5\text{ Hz}$ vibration ($0.35\text{ px}$) + $0.7\text{ Hz}$ camera shake ($0.65\text{ px}$) | Error reduction $\ge 60\%$, Shake suppression $\ge 10\text{ dB}$, $r \ge 0.90$, $\text{RMSE} < 0.16\text{ px}$ | **PASS** (Error reduction: $76.4\%$, Suppression: $12.5\text{ dB}$, $r = 0.963$, $\text{RMSE} = 0.112\text{ px}$) |
| **T4: Baseline Repeatability** | Verify baseline aggregation across $N \ge 3$ runs | 3 independent runs with varying noise seeds ($s = 101, 102, 103$) | $\text{MAD}_{\text{freq}} < 0.01\text{ Hz}$, $\text{MAD}_{\text{RMS}} < 0.01\text{ px}$, All 3 runs evaluate to `Normal` | **PASS** ($\text{MAD}_{\text{freq}} = 0.000\text{ Hz}$, $\text{MAD}_{\text{RMS}} = 0.002\text{ px}$, Triggers: 0) |
| **T5: Change Detection** | Screen unbalance / amplitude change against baseline | Baseline ($0.23\text{ px}$) vs. Changed Run ($0.35\text{ px}$, $+48\%$ RMS, added 2X) | Confidence Gate passes, Status: `Review`, $z_{\text{RMS}} \ge 3.0$, $z_{2X} \ge 3.0$ | **PASS** (Status: `Review`, $z_{\text{RMS}} = +22.5$, $z_{2X} = +5.7$, Non-diagnostic text verified) |
| **T6: Image-Quality Stress** | Verify quality rejection under severe optical degradation | T6a: Flat texture ($\sigma=0$)<br/>T6b: Severe blur ($r=0.08$)<br/>T6c: Illumination flicker<br/>T6d: $400\text{ ms}$ dropped frame stall | T6a: `check_roi_texture` fails<br/>T6b: `LOW_SIGNAL`<br/>T6c: `CONTAMINATED`<br/>T6d: `REJECTED_UNSTABLE` | **PASS** (All 4 degradation gates strictly trigger rejection) |

---

### 7.3 Public Benchmark: SpectraQuest Rotor Dataset
Audited against Mendeley Data DOI `10.17632/47y7rwc2yg.1` (*Journal of Sound and Vibration*, 2025):
* **Experimental Setup:** SpectraQuest Rotor Dynamic Test Rig. High-speed video recorded by Phantom v2512 high-speed camera ($1280 \times 800\text{ px}$), Nikon optical lens, alongside 4-channel eddy current proximity probes ($1000\text{ sps}$).
* **Verified Benchmark Conditions:**
  * **Video Source:** `data/rotor_dataset/Raw videos/` (`4s-Unb1.avi`, `1000rpm-Unb1.avi`, `2000rpm-Unb1.avi`).
  * **Shaft Target ROI:** $X=850, Y=460, W=64, H=64$ (or $X=600, Y=460, W=64, H=64$ at center span).
  * **Rigid Base Anchor ROI:** $X=600, Y=560, W=64, H=64$ (rigid steel test bed).
* **Key Findings & Scientific Disclosures:**
  1. **Timebase Discrepancy:** The physical camera recorded at $500\text{ FPS}$, but the exported AVI file header specifies a nominal $100.0\text{ FPS}$ playback rate. When processed with the explicit physical override `--fps 500`, PhaseSight extracts the 1X rotational frequency with high precision ($16.50\text{ Hz}$ at 1000 RPM, $33.07\text{ Hz}$ at 2000 RPM, and $50.10\text{ Hz}$ at 3000 RPM). If the override is omitted, container PTS operates at $100\text{ Hz}$, yielding $5.0\times$ dilated frequencies ($3.30\text{ Hz}, 6.61\text{ Hz}, 10.02\text{ Hz}$).
  2. **Controlled Resonance Detection:** Passing through critical resonance ($2000\text{ RPM}$) caused measured video vibration amplitude to surge from $0.10\text{ px}$ (1000 RPM) to $0.53\text{ px}$ ($3.8\times$ increase). Unsaturated physical eddy current sensors showed a corresponding $6.1\times - 6.7\times$ amplitude growth. This confirms PhaseSight successfully captures gross resonance amplification in the pixel domain.
  3. **Fine Unbalance Mass Ranking Failure:** When testing subtle unbalance increments at fixed speed (Unb1: $0.4\text{ g}$, Unb2: $0.8\text{ g}$, Unb3: $1.2\text{ g}$ at 1000 RPM), the physical vibration difference was approximately $0.01\text{ px}$. Ambient lighting fluctuations and high-speed CMOS sub-pixel noise floor exceeded this tiny differential, preventing PhaseSight from accurately ranking unbalance severity. PhaseSight is a screening tool, not an unbalance mass quantifier.
  4. **Sensor Units Ambiguity:** The dataset documentation describes sensor signals as "voltage signals" with a $10\text{ V/mm}$ sensitivity, but exports zero-mean values without units. Reference sensor values must be treated as unverified sensor output units.

---

# SECTION 8 — CURRENT DEFECTS AND TECHNICAL LIMITATIONS

### 8.1 Technical Risk Register
The following table documents verified architectural defects, algorithmic limitations, and operational risks in the current codebase:

| Defect / Limitation ID | Component | Severity | Current Behavior & Evidence | Suggested Architectural Resolution | Target Next.js / FastAPI Milestone |
|---|---|---|---|---|---|
| **DEF-01: Dominant-Only Anchor Contamination** | `phasesight/analysis.py:is_anchor_contaminated` | High | Only compares the globally dominant peak of the differential signal against the globally dominant peak of the anchor. If a secondary anchor harmonic coincides with the primary target peak, contamination is silently missed. | Scan all significant anchor peaks ($\text{prominence} \ge 6\text{ dB}$) against the differential peak list using set intersection within frequency tolerance. | Phase 2 (Core Algorithm Correction) |
| **DEF-02: Fixed Initial Reference Patch** | `phasesight/tracker.py:PhaseCorrelationTracker` | Medium | Reference patch is locked at $t=0$. If the machine undergoes large quasi-static deflection, thermal expansion, or optical drift exceeding patch dimensions, correlation response collapses to zero and tracking terminates. | Implement a keyframe-updating reference strategy or adaptive template update with bounded drift compensation. | Phase 5 (Continuous Acquisition) |
| **DEF-03: Pure Translation Model** | `phasesight/tracker.py:PhaseCorrelationTracker` | High | Assumes pure 2D in-plane translation. Camera roll, tilt, pitch, yaw, and perspective warping violate phase correlation assumptions, inducing false displacement signals. | Upgrade to planar homography or affine registration (e.g. enhanced correlation coefficient / ECC or feature-based homography). | Post-Hackathon Roadmap |
| **DEF-04: Host-Side Camera Permissions (macOS TCC)** | `phasesight/capture.py:open_capture_source` | High | In Streamlit, OpenCV runs in the Python process on the host OS via AVFoundation. macOS TCC blocks access unless Terminal.app has explicit Camera permissions, while browser permissions are ignored. | Transition to browser-native `navigator.mediaDevices.getUserMedia` in Next.js, streaming frames to FastAPI over WebSockets. | Phase 4 (Next.js Ingestion) |
| **DEF-05: Non-Continuous Batch Clip Model** | `phasesight/capture.py:capture_live_clip` | High | "Live" mode only records a finite 5–10s clip to disk as MP4, then executes offline batch analysis. There is zero true real-time continuous streaming analysis. | Implement a rolling circular ring buffer of motion samples feeding an asynchronous background worker. | Phase 5 (Continuous Acquisition) |
| **DEF-06: Container Framerate Header Deception** | `phasesight/video.py:analyse_video` | Medium | High-speed video containers (Phantom AVI) often write 100 FPS playback headers despite 500 FPS capture. Native CLI previously ignored `--fps 500` because `POS_MSEC` was valid. | Resolved in P0 fixes by giving explicit `--fps` absolute priority (`is_override=True`). Must be maintained in FastAPI file upload metadata. | Phase 3 (FastAPI Service) |
| **DEF-07: Uncalibrated Displacement (Pixels vs mm)** | Entire System | Low / Design Boundary | System measures motion strictly in image pixels ($px$). Cannot assess absolute vibration severity against ISO 10816 velocity standards ($mm/s$). | Introduce an optional physical calibration wizard (checkerboard target or known millimeter dimension between two pixel markers). | Post-Hackathon Roadmap |
| **DEF-08: Tri-State Second Harmonic Ambiguity** | `phasesight/baseline.py:_compute_harmonic_deviation` | Medium | When 2X harmonic is absent in baseline ($0.0$) but emerges in current run, z-score is calculated as $z = x_{\text{curr}} / \epsilon$. A very small epsilon ($0.010$) can over-trigger false Review alerts. | Validate harmonic emergence with a secondary absolute power threshold before triggering an alert. | Phase 2 (Core Algorithm Correction) |
| **DEF-09: Single-Process SQLite Concurrency** | `phasesight/storage.py:StorageManager` | Medium | SQLite WAL mode allows concurrent readers, but concurrent writes from multiple worker processes during continuous multi-camera monitoring will trigger `database is locked` timeouts. | Migrate relational metadata to PostgreSQL for enterprise production, or serialize SQLite writes through a dedicated database worker queue in FastAPI. | Phase 8 (Enterprise Multi-Camera) |
| **DEF-10: Memory Accumulation in Long Streams** | `phasesight/capture.py` | High | Storing raw frames in Python lists (`frames: list[np.ndarray]`) consumes $\sim 55\text{ MB/s}$ at 1080p @ 30 FPS, causing an Out-Of-Memory (OOM) crash within minutes of continuous capture. | Eliminate frame accumulation. Extract ROIs immediately in memory, discard full frames, and push scalar $(dx, dy)$ coordinates into a compact float64 ring buffer. | Phase 5 (Continuous Acquisition) |
| **DEF-11: Rolling Shutter Artifacts** | `phasesight/capture.py` | Low | CMOS webcams read out line-by-line, causing high-frequency vibration to appear as spatial wave distortion (wobble) rather than uniform patch translation. | Document rolling shutter limits. Recommend global-shutter cameras for high-frequency machinery ($>30\text{ Hz}$). | Phase 7 (CCTV Source Adapter) |
| **DEF-12: Absence of RTSP/ONVIF Network Adapters** | Entire System | High | The codebase contains zero RTSP URL handling, H.264/H.265 network stream demuxing, or ONVIF camera discovery. | Implement an asynchronous PyAV or GStreamer/OpenCV RTSP ingestion worker with automatic reconnection logic. | Phase 7 (CCTV Source Adapter) |

---

# SECTION 9 — REAL-TIME MONITORING GAP ANALYSIS

### 9.1 Current Offline Model vs. Target Continuous Pipeline
* **Current Operational Flow:**
  $$\text{Camera} \xrightarrow{\text{OpenCV}} \text{Record Clip (5s)} \xrightarrow{\text{Encode}} \text{Save MP4 to Disk} \xrightarrow{\text{Decode}} \text{Batch Track} \xrightarrow{\text{Batch Welch}} \text{Static Result}$$
  * Total Latency: Duration ($5\text{ s}$) $+$ Encoding ($1\text{ s}$) $+$ Decoding & Tracking ($2\text{ s}$) $+$ FFT ($0.2\text{ s}$) $\approx \mathbf{8.2\text{ seconds}}$ post-event.
* **Target Continuous Flow:**
  $$\text{Camera/RTSP} \xrightarrow{\text{Frame Drop}} \text{Worker Process} \xrightarrow{\text{ROI Crop}} \text{Phase Correlate} \xrightarrow{(dx, dy)} \text{Ring Buffer} \xrightarrow{\text{Rolling PSD}} \text{WebSocket} \xrightarrow{\text{Next.js}}$$
  * Latency: Motion sample available within **$15\text{ ms}$**; rolling spectral estimate updated every **$500\text{ ms}$**.

```mermaid
graph LR
    subgraph Target_Continuous_Engine["Target Continuous Real-Time Architecture"]
        direction LR
        CAM["Camera Stream<br/>(Browser / RTSP)"] -->|Frame t| CROP["In-Memory Crop<br/>Target & Anchor"]
        CROP -->|Patches| PC["Phase Correlation<br/>(OpenCV C++)"]
        PC -->|Sample dt, dx, dy| RING["Ring Buffer (NumPy)<br/>Capacity N = 1024"]
        RING -->|Every 500ms| ROLLING_PSD["Rolling Welch PSD<br/>(Scipy / FFTW)"]
        ROLLING_PSD -->|Telemetry Event| WS["FastAPI WebSocket<br/>/ws/telemetry"]
        WS -->|Live JSON| UI["Next.js WebGL / Canvas<br/>Real-Time Scope & Spectrum"]
    end
```

---

### 9.2 Rolling-Window Spectral Analysis
To transition from batch to continuous monitoring without altering the mathematical integrity of Welch's method:
* **Circular Ring Buffer:** A pre-allocated NumPy array of shape $(N_{\text{buf}}, 3)$ storing `[timestamp, relative_dx, relative_dy]`.
  * For $f_s = 60\text{ Hz}$ and buffer duration $T = 8.53\text{ seconds}$, $N_{\text{buf}} = 512$ samples.
* **Spectral Resolution Trade-Off:**
  $$\Delta f = \frac{f_s}{N_{\text{seg}}}$$
  * To resolve a $0.5\text{ Hz}$ frequency shift at $60\text{ FPS}$, the minimum window segment must be:
    $$N_{\text{seg}} \ge \frac{60}{0.5} = 120\text{ samples} \approx 2.0\text{ seconds}$$
* **Update Interval vs. Computational Load:**
  * While tracking occurs per-frame ($60\text{ Hz}$, taking $\sim 1.5\text{ ms}$ per frame pair), rolling Welch analysis should execute asynchronously at **$2\text{ Hz}$ to $4\text{ Hz}$** ($250\text{ ms} - 500\text{ ms}$ intervals).
  * Reusing the existing `analyse_displacement` logic on the current window contents guarantees complete mathematical consistency with historic offline records.

---

### 9.3 Camera Ingestion Modalities

```mermaid
graph TD
    subgraph Browser_Source["Modality A: Browser-Connected Camera"]
        B1["Next.js Frontend"] -->|getUserMedia| B2["HTML5 <video> & Canvas"]
        B2 -->|Compressed Frames / MJPEG| B3["FastAPI WebSocket"]
    end

    subgraph Factory_Source["Modality B: Factory Security Camera (CCTV)"]
        F1["RTSP / ONVIF Network Camera"] -->|H.264 / H.265 RTSP Stream| F2["Backend Ingestion Worker (PyAV / OpenCV)"]
        F2 -->|Raw Decoded BGR Frame| F3["Phase Correlation Engine"]
    end

    subgraph Local_Source["Modality C: Host Machine Camera"]
        L1["USB / UVC Webcam"] -->|Direct V4L2 / AVFoundation| L2["Local OpenCV VideoCapture"]
        L2 -->|Local Memory Pointer| L3["Phase Correlation Engine"]
    end
```

* **Modality A (Browser Camera):** Uses Chrome's camera access. Camera permissions are handled by the browser. Requires transferring frames across local WebSocket to the backend. Best for rapid demonstration and zero-install client devices.
* **Modality B (Factory CCTV Camera):** Connects directly from backend server to factory IP camera over local Ethernet via RTSP (`rtsp://user:pass@192.168.1.100:554/live`). Highly robust, completely bypasses host OS UI permissions, but requires backend RTSP decoding libraries.
* **Modality C (Host UVC Camera):** Current OpenCV implementation. High local performance, but restricted by OS process permissions (macOS TCC).

---

### 9.4 Sampling Rate & Frequency Feasibility Matrix
Theoretical Nyquist frequency vs. realistic observable machinery vibration bandwidth:

| Nominal Camera FPS | Theoretical Nyquist ($f_{\text{Nyq}} = f_s / 2$) | Realistic Observable Vibration Bandwidth | Target Machinery Screening Scope | Feasibility with Standard CCTV Feeds |
|---|---|---|---|---|
| **15 FPS** (Low CCTV) | $7.5\text{ Hz}$ | **$0.5 - 5.0\text{ Hz}$** ($30 - 300\text{ RPM}$) | Slow conveyor belts, agitators, giant wastewater aerators. | Marginally feasible; severe risk of frequency aliasing. |
| **25 FPS** (PAL CCTV) | $12.5\text{ Hz}$ | **$0.5 - 9.0\text{ Hz}$** ($30 - 540\text{ RPM}$) | Low-speed industrial mixers, cooling tower fans ($< 540\text{ RPM}$). | Feasible for low-speed machinery only. |
| **30 FPS** (NTSC CCTV / Webcams) | $15.0\text{ Hz}$ | **$0.5 - 12.0\text{ Hz}$** ($30 - 720\text{ RPM}$) | Sub-harmonic oil whirl, low-speed fans, pumps ($< 720\text{ RPM}$). | Standard baseline; cannot resolve 1X of standard $1800/3600\text{ RPM}$ motors. |
| **60 FPS** (High-Rate UVC / IP) | $30.0\text{ Hz}$ | **$0.5 - 24.0\text{ Hz}$** ($30 - 1440\text{ RPM}$) | Direct-drive fans, 4-pole induction motors operating at slip ($1450\text{ RPM}$). | Excellent screening sweet spot for industrial machinery. |
| **120 FPS** (Specialized Industrial) | $60.0\text{ Hz}$ | **$0.5 - 48.0\text{ Hz}$** ($30 - 2880\text{ RPM}$) | Standard 2-pole 50 Hz motors ($2950\text{ RPM}$), full 1X rotational unbalance. | Requires dedicated industrial USB3/GigE camera (Basler/FLIR). |
| **240 FPS** (High-Speed Industrial) | $120.0\text{ Hz}$ | **$0.5 - 96.0\text{ Hz}$** ($30 - 5760\text{ RPM}$) | 2-pole 60 Hz motors ($3550\text{ RPM}$), 2X harmonics on 50 Hz machines ($100\text{ Hz}$). | Industrial machine vision cameras only. |
| **500 FPS** (Research High-Speed) | $250.0\text{ Hz}$ | **$0.5 - 200.0\text{ Hz}$** ($30 - 12000\text{ RPM}$) | High-speed turbines, blade passing frequencies, 4X bearing harmonics. | Phantom / Photron specialized cameras (e.g. SpectraQuest benchmark). |

---

# SECTION 10 — NEXT.JS + FASTAPI TARGET ARCHITECTURE

### 10.1 Modular Clean Architecture Separation
```mermaid
graph TD
    subgraph Frontend["Next.js 15 Frontend (App Router, React 19, TypeScript)"]
        UI_DASH["Asset Dashboard & Screening Alerts"]
        UI_MON["Live Machine Monitoring Screen"]
        UI_VIEW["Interactive Canvas Viewport (Mouse ROI Selection)"]
        UI_SCOPE["WebGL Real-Time Oscilloscope Trace"]
        UI_SPEC["Plotly / Chart.js Live Spectral View"]
        UI_HIST["Inspection History & Baseline Calibration Wizard"]
    end

    subgraph API_Layer["FastAPI Gateway (Uvicorn / Starlette)"]
        REST_ASSETS["/api/v1/assets (CRUD)"]
        REST_BASE["/api/v1/baselines (Build & Query)"]
        REST_RUNS["/api/v1/runs (Offline Upload & History)"]
        WS_LIVE["/ws/v1/monitoring/{asset_id} (Bi-directional Telemetry)"]
    end

    subgraph Core_Engine["Decoupled Python Scientific Core (Independent Package)"]
        TRACK_ENG["phasesight.tracker (PhaseCorrelationTracker)"]
        ANAL_ENG["phasesight.analysis (Welch, Harmonics, Quality)"]
        BASE_ENG["phasesight.baseline (Median, MAD, Robust Z)"]
        STAB_ENG["phasesight.capture (Stability & Jitter Auditing)"]
    end

    subgraph Workers["Asynchronous Monitoring Workers"]
        WORKER_MGR["MonitoringSessionManager"]
        RING_BUF["MotionSampleRingBuffer"]
        RTSP_ADAPT["RTSP / Camera Stream Ingest Worker"]
    end

    subgraph Storage["Persistence Layer"]
        DB[(PostgreSQL / SQLite WAL)]
        NPZ_FILES[("Local Compressed NPZ Archives")]
    end

    Frontend <-->|REST HTTP| API_Layer
    UI_SCOPE <-->|WebSocket Binary / JSON| WS_LIVE
    UI_SPEC <-->|WebSocket Telemetry| WS_LIVE

    API_Layer --> Core_Engine
    API_Layer <--> WORKER_MGR
    WORKER_MGR --> RTSP_ADAPT
    RTSP_ADAPT --> TRACK_ENG
    TRACK_ENG --> RING_BUF
    RING_BUF --> ANAL_ENG
    ANAL_ENG --> BASE_ENG
    BASE_ENG --> WS_LIVE

    API_Layer <--> DB
    WORKER_MGR --> NPZ_FILES
```

---

### 10.2 Proposed FastAPI Endpoints & Data Contracts

#### 1. Machinery Assets (`/api/v1/assets`)
* `GET /api/v1/assets`: List all registered machine assets. Returns `list[AssetSchema]`.
* `POST /api/v1/assets`: Register a new machine asset with default ROIs and operating parameters.
  * *Request Body:* `{ name: str, description: str, nominal_speed_rpm: float, target_roi: ROIModel, anchor_roi: ROIModel, expected_fps: float }`
  * *Response:* `AssetSchema` ($201\text{ Created}$).
* `GET /api/v1/assets/{asset_id}`: Retrieve single asset details and current active baseline.

#### 2. Offline Video Inspection (`/api/v1/runs`)
* `POST /api/v1/runs/upload`: Upload video file (multipart form) for batch processing.
  * *Form Parameters:* `file: UploadFile`, `asset_id: str`, `target_roi: str`, `anchor_roi: str`, `fps_override: float | None`.
  * *Response:* `InspectionRunSummarySchema` (Dominant frequencies, RMS displacement, quality status, baseline screening status).
* `GET /api/v1/runs/{run_id}/arrays`: Download raw time-series and spectral arrays as JSON or binary NPZ.

#### 3. Statistical Baselines (`/api/v1/baselines`)
* `POST /api/v1/baselines/build`: Aggregate $\ge 3$ completed inspection runs into an immutable baseline.
  * *Request Body:* `{ asset_id: str, run_ids: list[str], notes: str }`
  * *Response:* `BaselineRecordSchema`.
* `GET /api/v1/baselines/{baseline_id}`: Retrieve baseline statistics (medians, MADs, tolerances).

#### 4. Real-Time Telemetry WebSocket (`/ws/v1/monitoring/{asset_id}`)
* **Protocol:** Bi-directional JSON WebSocket.
* **Client Handshake:** `{ action: "start", source: "rtsp://...", target_roi: {...}, anchor_roi: {...} }`.
* **Server Telemetry Message (Broadcast at $4\text{ Hz}$):**
  ```json
  {
    "type": "telemetry_update",
    "asset_id": "ast_pump_01",
    "timestamp": 1732450000.125,
    "measured_fps": 59.94,
    "stability_status": "STABLE",
    "jitter_ratio": 0.012,
    "current_motion": {
      "relative_dx_px": 0.241,
      "relative_dy_px": -0.012,
      "target_response": 0.912,
      "anchor_response": 0.884
    },
    "spectral_summary": {
      "x_axis": {
        "dominant_frequency_hz": 14.85,
        "rms_displacement_px": 0.185,
        "peak_to_median_db": 16.4,
        "second_harmonic_ratio": 0.042,
        "signal_quality": "VALID"
      }
    },
    "screening_assessment": {
      "status": "Normal",
      "max_z_score": 1.42,
      "trigger_features": []
    }
  }
  ```

---

### 10.3 Monitoring Session Lifecycle State Machine
```mermaid
stateDiagram-v2
    [*] --> Idle: Initialize Service
    Idle --> Connecting: Client triggers Start Monitoring
    Connecting --> Calibrating: Stream connected & warm frames flushed
    Connecting --> ConnectionFailed: Stream unreachable / Auth error
    ConnectionFailed --> Idle: Report error to UI

    Calibrating --> QualityRejected: ROI texture std < 2.0 or Overlap
    QualityRejected --> Idle: Prompt user to adjust ROIs

    Calibrating --> Buffering: Target & Anchor ROIs verified
    Buffering --> ContinuousTracking: Buffer filled (N >= 256 samples)
    
    state ContinuousTracking {
        [*] --> ProcessFrame: Arrival of frame t
        ProcessFrame --> ComputeCorrelation: Phase Correlation (OpenCV)
        ComputeCorrelation --> PushRingBuffer: Append dx, dy to Ring Buffer
        PushRingBuffer --> PeriodicWelch: Timer tick (every 250ms)
        PeriodicWelch --> EvaluateBaseline: Compute z-scores vs Baseline
        EvaluateBaseline --> BroadcastWebSocket: Emit telemetry update
        BroadcastWebSocket --> ProcessFrame
    }

    ContinuousTracking --> StreamLost: RTSP timeout / Frame drop > 2.5s
    StreamLost --> Connecting: Automatic Reconnect Loop
    ContinuousTracking --> Stopping: Client sends Stop or Tab Closes
    Stopping --> Persisting: Flush final summary to SQLite & NPZ
    Persisting --> Idle: Session Completed
```

---

### 10.4 Worker Process Architecture
* **Single vs. Dedicated Process:**
  * Running OpenCV video capture loops directly inside async FastAPI request handlers will **block the Python asyncio event loop**, freezing REST requests for all other users.
  * *Architecture Recommendation:* Each continuous monitoring session runs in an independent **`multiprocessing.Process`** or dedicated worker thread communicating with FastAPI via a lock-free `multiprocessing.Queue`.
  * *Hackathon Vertical Slice:* For single-stream evaluation, a background worker thread (`threading.Thread`) with an atomic ring buffer is sufficient. For multi-camera factory monitoring, dedicated worker processes managed by Celery/Redis or asyncio subprocesses are required.

---

# SECTION 11 — MIGRATION MAP

The following table provides the exhaustive component migration mapping from the existing monolithic repository to the decoupled Next.js + FastAPI target architecture:

| Existing Module & Function | Current Responsibility | New Architectural Location | Migration Classification | Required Modifications |
|---|---|---|---|---|
| `tracker.py:ROI` | Rectangular bounding box geometry | `core/domain/roi.py` | **REUSE AS-IS** | None. Zero external dependencies. |
| `tracker.py:PhaseCorrelationTracker` | Sub-pixel phase correlation tracking | `core/tracking/phase_correlation.py` | **EXTRACT TO DOMAIN CORE** | Clean separation from any UI helpers. |
| `tracker.py:validate_rois` | Pre-flight bounds, overlap, texture validation | `core/tracking/validation.py` | **REUSE AS-IS** | None. |
| `analysis.py:analyse_displacement` | Welch PSD, peak finding, 2X harmonic extraction | `core/spectral/welch.py` | **EXTRACT TO DOMAIN CORE** | Keep mathematical parameters identical. |
| `analysis.py:is_anchor_contaminated` | Static anchor contamination audit | `core/spectral/quality.py` | **REFACTOR** | Fix DEF-01 to evaluate secondary anchor peaks. |
| `analysis.py:classify_signal_quality` | Prominence & phase response gate | `core/spectral/quality.py` | **REUSE AS-IS** | None. |
| `baseline.py:build_baseline` | Robust baseline aggregation (Median, MAD) | `core/baseline/engine.py` | **EXTRACT TO DOMAIN CORE** | Decouple from local filesystem JSON writes. |
| `baseline.py:evaluate_run_against_baseline` | Two-stage screening (Confidence & Review) | `core/baseline/evaluator.py` | **REUSE AS-IS** | None. |
| `capture.py:calculate_timestamp_stability` | Quantitative jitter and dropped frame audit | `core/timing/stability.py` | **EXTRACT TO DOMAIN CORE** | None. Pure mathematical evaluation. |
| `capture.py:MockVideoCapture` | Deterministic synthetic video stream | `core/adapters/mock_camera.py` | **REUSE AS-IS** | Reusable for backend test suites and mocks. |
| `capture.py:capture_live_clip` | Bounded clip acquisition to disk | `services/acquisition/bounded_capture.py` | **WRAP WITH SERVICE** | Expose via FastAPI `/api/v1/capture/clip`. |
| `video.py:analyse_video` | Batch offline video analysis orchestration | `services/analysis/batch_video.py` | **WRAP WITH SERVICE** | Adapt to accept streaming file uploads in FastAPI. |
| `storage.py:StorageManager` | SQLite relational CRUD and NPZ arrays | `infrastructure/persistence/` | **REFACTOR** | Split SQLite tables into SQLAlchemy/SQLModel models. |
| `synthetic.py:make_scene` | Synthetic video generator | `core/simulation/synthetic_scene.py` | **REUSE AS-IS** | Preserved for automated testing and CI/CD. |
| `cli.py` | Command-line interface subcommands | `interfaces/cli/` | **REFACTOR** | Update imports to call new service layers. |
| `app.py` | Streamlit graphical user interface | `frontend/ (Next.js 15)` | **REPLACE** | Replace with Next.js App Router & React components. |
| `ui_*.py` | Streamlit CSS, tokens, and viewport widgets | `frontend/src/components/` | **REPLACE** | Port Liquid Glass design system into Tailwind CSS / CSS Modules. |

---

# SECTION 12 — RECOMMENDED DEVELOPMENT SEQUENCE

To minimize risk and avoid regressions, the migration to Next.js + FastAPI should follow this strict phased sequence:

```mermaid
flowchart TD
    P1["Phase 1: Canonical Technical Specification<br/>(COMPLETE — This Document)"] --> P2["Phase 2: Core Algorithm Corrections<br/>(Fix DEF-01 Secondary Anchor Contamination)"]
    P2 --> P3["Phase 3: Decoupled Python Core Extraction<br/>(Clean package without UI dependencies)"]
    P3 --> P4["Phase 4: FastAPI Service Wrapper<br/>(REST Endpoints for Batch Upload, Baselines, SQLite)"]
    P4 --> P5["Phase 5: Next.js Upload & Inspection MVP<br/>(Replaces Streamlit offline analysis; Canvas ROI selection)"]
    P5 --> P6["Phase 6: In-Memory Ring Buffer & WebSocket Telemetry<br/>(Real-time tracking and rolling Welch PSD worker)"]
    P6 --> P7["Phase 7: Live Browser Camera & RTSP Adapters<br/>(getUserMedia WebSockets & Factory RTSP ingestion)"]
    P7 --> P8["Phase 8: Multi-Camera Enterprise Dashboard<br/>(PostgreSQL, long-term degradation trend charts)"]
```

### The Smallest Demonstrable Vertical Slice (Hackathon Milestone)
1. **FastAPI Backend:** Expose `POST /api/v1/runs/upload` and `POST /api/v1/baselines/build` using the extracted, verified Python domain core.
2. **Next.js Frontend:** A 2-screen application:
   * **Screen 1 (Interactive Viewport):** Upload video, view first frame, click and drag bounding boxes to set Target and Anchor ROIs, select 1-click presets (`Rotor Rig Preset`).
   * **Screen 2 (Spectral Results):** Display dominant frequency, RMS displacement, peak prominence, 2X harmonic ratio, and interactive Plotly spectrum.
   * **Screen 3 (Baseline Assessment):** Show statistical deviation card (`Normal`, `Review`, `Low confidence`).
3. **Validation Guarantee:** The vertical slice must produce identical numerical outputs to `phasesight inspect` across all 6 validation protocols (T1–T6).

---

# SECTION 13 — REQUIRED MATHEMATICAL REFERENCE

| Measurement Dimension | Mathematical Formulation | Variable Definitions | Engineering Units | Implementing Function | Code Agreement Status |
|---|---|---|---|---|---|
| **ROI Texture Standard Deviation** | $\sigma = \sqrt{\frac{1}{wh} \sum (I(u, v) - \mu)^2}$ | $w, h$: ROI dimensions<br/>$I(u, v)$: Grayscale intensity | Pixel intensity counts $[0, 255]$ | `tracker.py:check_roi_texture` | **Exact** |
| **Patch Normalization** | $\hat{I}(u, v) = \frac{I(u, v) - \mu}{\sigma + 10^{-6}}$ | $\mu$: Patch mean<br/>$\sigma$: Patch standard deviation | Dimensionless | `tracker.py:_normalise_patch` | **Exact** |
| **2D Hanning Window** | $W(u, v) = w_x(u) \cdot w_y(v)$ | $w_x(u) = 0.5(1 - \cos(\frac{2\pi u}{w-1}))$ | Dimensionless | `tracker.py:PhaseCorrelationTracker` | **Exact (OpenCV C++)** |
| **Phase Correlation** | $R(u, v) = \frac{F_1 \cdot F_2^*}{\|F_1 \cdot F_2^*\| + \epsilon}$ | $F_1, F_2$: 2D Fourier transforms | Dimensionless complex field | `tracker.py:PhaseCorrelationTracker` | **Exact (OpenCV C++)** |
| **Differential Displacement** | $x_{\text{rel}} = x_T - x_A$<br/>$y_{\text{rel}} = y_T - y_A$ | $x_T$: Target translation<br/>$x_A$: Anchor translation | Image pixels ($px$) | `tracker.py:PhaseCorrelationTracker` | **Exact** |
| **Inter-Frame Interval** | $\Delta t_i = t_i - t_{i-1}$ | $t_i$: Timestamp of frame $i$ | Seconds ($s$) | `capture.py:calculate_timestamp_stability` | **Exact** |
| **Sampling Rate** | $f_s = \frac{1}{\text{median}(\Delta t)}$ | $\Delta t$: Inter-frame intervals | Hertz ($\text{Hz}$) | `analysis.py:analyse_displacement` | **Exact** |
| **Timing Jitter Ratio** | $J = \frac{\text{std}(\Delta t)}{\text{median}(\Delta t)}$ | $\Delta t$: Inter-frame intervals | Dimensionless ratio | `capture.py:calculate_timestamp_stability` | **Exact** |
| **Robust Jitter Ratio** | $J_{\text{mad}} = \frac{1.4826 \cdot \text{MAD}(\Delta t)}{\text{median}(\Delta t)}$ | $\text{MAD}$: Median absolute deviation | Dimensionless ratio | `capture.py:calculate_timestamp_stability` | **Exact** |
| **Linear Detrending** | $x_{\text{detrended}} = x - (\alpha t + \beta)$ | $\alpha, \beta$: Least-squares linear fit | Image pixels ($px$) | `analysis.py:analyse_displacement` | **Exact (SciPy)** |
| **Displacement RMS** | $\text{RMS} = \sqrt{\frac{1}{N} \sum x_i^2}$ | $x_i$: Detrended displacement samples | Image pixels ($px$) | `analysis.py:analyse_displacement` | **Exact** |
| **Welch Frequency Resolution** | $\Delta f = \frac{f_s}{N_{\text{seg}}}$ | $f_s$: Sampling rate<br/>$N_{\text{seg}}$: Segment length | Hertz ($\text{Hz}$) | `analysis.py:analyse_displacement` | **Exact** |
| **Peak Prominence** | $P_{\text{dB}} = 10 \log_{10}\left(\frac{\text{PSD}_{\text{peak}}}{\text{PSD}_{\text{bg}}}\right)$ | $\text{PSD}_{\text{peak}}$: Peak bin power<br/>$\text{PSD}_{\text{bg}}$: Median background power | Decibels ($\text{dB}$) | `analysis.py:analyse_displacement` | **Exact** |
| **3-Bin Parabolic Peak** | $\delta = \text{clip}\left(\frac{0.5(y_0 - y_2)}{y_0 - 2y_1 + y_2}, -1, 1\right)$ | $y_k = \ln(\text{PSD}[k])$ | Sub-bin offset $[-1.0, 1.0]$ | `analysis.py:analyse_displacement` | **Exact** |
| **2X Harmonic Ratio** | $\text{Ratio}_{2X} = \frac{\sum_{\text{band } 2X} \text{PSD}}{\sum_{\text{band } 1X} \text{PSD}}$ | Spectral power sums in $\pm \Delta f$ bands | Dimensionless power ratio | `analysis.py:analyse_displacement` | **Exact** |
| **Scaled MAD** | $\text{MAD}_{\text{scaled}} = 1.4826 \cdot \text{med}(\|x - \tilde{x}\|)$ | $\tilde{x}$: Sample median | Same units as feature | `baseline.py:compute_robust_stats` | **Exact** |
| **Robust Z-Score** | $z = \frac{x_{\text{curr}} - \text{med}}{1.4826 \cdot \text{MAD} + \epsilon}$ | $\epsilon$: Floor regularization constant | Dimensionless ($z$-score) | `baseline.py:_compute_feature_deviation` | **Exact** |

---

# SECTION 14 — ARCHITECTURAL CONCLUSION & VERDICT

PhaseSight possesses a mathematically sound, reproducible, and thoroughly verified sub-pixel vibration screening engine in the 2D image pixel domain.

### Summary of Architectural Realities
1. **The Math is Valid:** The phase correlation tracking, Welch PSD estimation, 3-bin parabolic peak interpolation, camera shake differential cancellation, and robust statistical baseline screening (Median/MAD) are fully implemented, verified across 129 automated tests, and validated against physical rotor rig benchmarks.
2. **The Output is Uncalibrated:** PhaseSight is strictly a **screening tool operating in pixels ($px$)**. It does not output millimeters or ISO vibration severity levels ($mm/s$), and does not diagnose named mechanical failure modes or compute Remaining Useful Life.
3. **The Current Implementation is Batch:** There is no continuous real-time streaming engine in the current codebase. Live camera capture is currently implemented as bounded clip recording to disk followed by offline batch processing.
4. **The Migration Path is Clear:** Because the core Python scientific engine (`tracker.py`, `analysis.py`, `baseline.py`, `capture.py`) has zero dependencies on Streamlit, it can be extracted cleanly into an independent Python domain core. A modern Next.js frontend with HTML5 Canvas mouse-drawn ROI selection and a FastAPI REST/WebSocket backend will eliminate current macOS camera permission friction and provide a production-grade industrial monitoring workstation.
