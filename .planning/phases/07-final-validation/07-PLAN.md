---
phase: 07-final-validation
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - phasesight/validation.py
  - phasesight/cli.py
  - tests/test_validation_matrix.py
  - DEMO_GUIDE.md
  - README.md
  - TEST_REPORT.md
autonomous: true
requirements:
  - REQ-T1
  - REQ-T2
  - REQ-T3
  - REQ-T4
  - REQ-T5
  - REQ-T6
  - REQ-CLI
  - REQ-DEMO
  - REQ-DOCS

estimate:
  tokens: 48000
  raw_tokens: 24000
  tasks: 3
  confidence: high

must_haves:
  truths:
    - "phasesight/validation.py implements modular validation protocols T1 to T6 and run_full_validation_matrix() while maintaining 100% backward compatibility with run_validation_suite() per D-01, D-02, REQ-T1 through REQ-T6."
    - "CLI subcommand phasesight validate executes the T1 to T6 matrix, prints a structured ASCII summary table, and exports machine-readable JSON reports per D-02 and REQ-CLI."
    - "tests/test_validation_matrix.py provides comprehensive automated test coverage for T1 to T6 protocols and CLI validation integration per D-01, D-02, REQ-T1 through REQ-T6, and REQ-CLI."
    - "DEMO_GUIDE.md provides an 8-stage interactive demonstration walkthrough covering environment setup, CLI validation, pre-packaged clip inspection, 6-tab Streamlit UI, asset registration, baseline wizard, mock/live webcam capture with stability card, history exploration, and review event logging per D-03 and REQ-DEMO."
    - "README.md and TEST_REPORT.md document complete prototype architecture, all 10 CLI subcommands, 6 UI tabs, full numerical evidence from 85+ unit tests and T1 to T6 matrix, public benchmark dataset evaluation protocols (Mendeley Rotor at 500 FPS + eddy current sensors), and non-negotiable boundaries per D-04, D-05, and REQ-DOCS."
  artifacts:
    - phasesight/validation.py
    - phasesight/cli.py
    - tests/test_validation_matrix.py
    - DEMO_GUIDE.md
    - README.md
    - TEST_REPORT.md
  key_links:
    - "phasesight/validation.py imports PhaseCorrelationTracker and validate_rois from phasesight.tracker, analyse_displacement and classify_signal_quality from phasesight.analysis, build_baseline and evaluate_run_against_baseline from phasesight.baseline, and calculate_timestamp_stability from phasesight.capture"
    - "phasesight/cli.py imports run_full_validation_matrix from phasesight.validation for the extended validate subcommand"
    - "tests/test_validation_matrix.py imports validation protocols and run_full_validation_matrix from phasesight.validation"
    - "DEMO_GUIDE.md guides evaluators through phasesight validate, phasesight inspect, phasesight compare, and phasesight ui"
    - "TEST_REPORT.md reports exact empirical metrics matching run_full_validation_matrix() results and pytest test suite execution"
---

<objective>
Implement Phase 7: Final Validation & Demonstration Package for the PhaseSight prototype (Prasunex Innovathon 2026). Deliver the complete Proposal Page 5 validation matrix (Protocols T1 through T6) covering synthetic known motion recovery, static negative control & noise floor quantification, camera-motion control with quantitative before-and-after anchor subtraction efficacy, portable baseline repeatability, controlled change detection with non-diagnostic disclosure, and image-quality stress testing across four environmental failure modes. Extend the validation engine in `phasesight/validation.py` and the CLI in `phasesight/cli.py` with structured table rendering and JSON export while maintaining 100% backward compatibility with `run_validation_suite()`. Provide automated test coverage in `tests/test_validation_matrix.py`. Author an end-to-end, reproducible 8-stage demonstration walkthrough script in `DEMO_GUIDE.md` for hackathon evaluators. Harden `README.md` and `TEST_REPORT.md` with complete numerical evidence from all 85+ passing tests, public benchmark dataset evaluation protocols (Mendeley Rotor at 500 FPS + eddy-current sensors), and strict disclosure of non-negotiable technical boundaries.

Purpose: Provide undeniable empirical proof of PhaseSight's sub-pixel vibration screening accuracy, camera shake cancellation efficacy, baseline repeatability, and failure-mode resilience, packaged in a frictionless walkthrough that enables evaluators to verify the prototype in under 10 minutes.
Output: Updated `phasesight/validation.py`, updated `phasesight/cli.py`, new test suite `tests/test_validation_matrix.py`, new walkthrough guide `DEMO_GUIDE.md`, updated `README.md`, and updated `TEST_REPORT.md`.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/07-final-validation/07-RESEARCH.md
@phasesight/validation.py
@phasesight/cli.py
@phasesight/synthetic.py
@phasesight/tracker.py
@phasesight/analysis.py
@phasesight/baseline.py
@phasesight/capture.py
@tests/test_validation_suite.py
@TEST_REPORT.md
@README.md
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Proposal Validation Matrix Engine (T1–T6 Protocols), CLI Extension, and Test Harness</name>
  <files>phasesight/validation.py, phasesight/cli.py, tests/test_validation_matrix.py</files>
  <action>
Implement the full Proposal Page 5 validation test matrix (T1–T6) in phasesight/validation.py, wire it to the CLI in phasesight/cli.py, and build comprehensive automated tests in tests/test_validation_matrix.py per D-01, D-02, REQ-T1, REQ-T2, REQ-T3, REQ-T4, REQ-T5, REQ-T6, and REQ-CLI.

1. In phasesight/validation.py:
   - Maintain 100% backward compatibility for validate_synthetic_case() and run_validation_suite() so tests/test_validation_suite.py continues to pass with len(results) == 4 and identical structure per D-02.
   - Implement validate_t1_synthetic_motion() -> dict[str, Any] per D-01 and REQ-T1:
     - Case T1a (Clean Target Vibration): SyntheticConfig(vibration_frequency_hz=8.5, vibration_amplitude_px=0.35, camera_amplitude_px=0.0, noise_sigma=0.5, seed=1). Recover measured dominant frequency via analyse_displacement(times, m_x, min_frequency_hz=1.0, max_frequency_hz=20.0), calculate frequency error (|f_meas - 8.5| <= 0.05 Hz), displacement RMSE (<= 0.10 px), Pearson correlation (r >= 0.90), and signal quality ("VALID").
     - Case T1b (Harmonic Target with Camera Shake): SyntheticConfig(vibration_frequency_hz=8.5, vibration_amplitude_px=0.25, second_harmonic_amplitude_px=0.08, camera_amplitude_px=0.40, noise_sigma=1.0, seed=4). Recover dominant frequency (|f_meas - 8.5| <= 0.05 Hz), displacement RMSE (<= 0.15 px), Pearson correlation (r >= 0.90), second harmonic ratio (> 0.04), and signal quality ("VALID").
     - Set status to "PASS" if both clean and harmonic criteria are met, else "FAIL".
   - Implement validate_t2_static_negative_control() -> dict[str, Any] per D-01 and REQ-T2:
     - Case T2a (Pure Static): SyntheticConfig(vibration_amplitude_px=0.0, camera_amplitude_px=0.0, noise_sigma=1.0, seed=10). Track relative displacement; assert residual noise floor RMS <= 0.08 px (empirically ~0.032 px), peak-to-median spectral prominence < 10.0 dB (empirically ~7.1 dB), and signal quality classified as "LOW_SIGNAL".
     - Case T2b (Camera Shake Only Null Control): SyntheticConfig(vibration_amplitude_px=0.0, camera_amplitude_px=0.65, camera_y_amplitude_px=0.25, lighting_flicker_depth=0.08, noise_sigma=1.5, seed=3). Track relative displacement; assert residual noise floor RMS <= 0.08 px (empirically ~0.052 px), peak-to-median prominence < 10.0 dB, and signal quality classified as "LOW_SIGNAL".
     - Screen both null runs against healthy baseline; assert zero false reviews triggered (review_triggers == 0).
     - Set status to "PASS" if noise floor, low-signal, and zero false review criteria pass.
   - Implement validate_t3_camera_shake_cancellation() -> dict[str, Any] per D-01 and REQ-T3:
     - SyntheticConfig(vibration_frequency_hz=8.5, vibration_amplitude_px=0.35, camera_amplitude_px=0.65, camera_y_amplitude_px=0.25, camera_frequency_hz=0.7, noise_sigma=1.5, seed=2).
     - Process frames with PhaseCorrelationTracker; record uncorrected target_dx_px and corrected relative_dx_px for each frame.
     - Compute uncorrected RMSE vs ground truth and uncorrected Pearson correlation.
     - Compute corrected RMSE vs ground truth and corrected Pearson correlation.
     - Calculate shake error attenuation percentage: (1.0 - rmse_corr / rmse_uncorr) * 100.0.
     - Calculate shake suppression in decibels: 20.0 * log10(rmse_uncorr / rmse_corr).
     - Verify attenuation >= 60.0% (empirically 71.0%), decibel suppression >= 10.0 dB (empirically 10.8 dB), and correlation improvement from < 0.60 to >= 0.90 (empirically 0.512 to 0.906). Status: "PASS".
   - Implement validate_t4_baseline_repeatability() -> dict[str, Any] per D-01 and REQ-T4:
     - Ingest >= 3 healthy capture runs (using deterministic synthetic repeats with distinct seeds or data/portable/baseline.mp4).
     - Aggregate into BaselineRecord via build_baseline(runs, min_runs=3).
     - Verify feature spread: dominant_frequency_hz MAD < 0.01 Hz (empirically 0.000 Hz) and rms_displacement_px MAD < 0.01 px (empirically 0.000 px).
     - Evaluate each constituent healthy run against the baseline using evaluate_run_against_baseline(run, baseline); assert status is "Normal", confidence_passed is True, and review trigger count is 0 (zero false alarms, |z_robust| < 3.0). Status: "PASS".
   - Implement validate_t5_controlled_change_detection() -> dict[str, Any] per D-01 and REQ-T5:
     - Use reference healthy baseline from T4 (or data/portable/out_baseline/baseline_summary.json).
     - Evaluate changed inspection run (data/portable/out_changed/changed_summary.json or synthetic changed run with +50% RMS and 2x harmonic).
     - Evaluate using evaluate_run_against_baseline(changed_run, baseline).
     - Assert evaluation status is "Review", confidence_passed is True, and triggers isolate "RMS Displacement" and "2x Harmonic Ratio" with |z_robust| >= 3.0 (empirically z_rms=+22.54, z_harm=+4.77).
     - Assert evaluation interpretation matches NON_DIAGNOSTIC_INTERPRETATION ("A Review status indicates a measured statistical shift relative to the reference baseline, not a diagnosed machine fault or failure mode."). Status: "PASS".
   - Implement validate_t6_image_quality_stress() -> dict[str, Any] per D-01 and REQ-T6:
     - Sub-case T6a (Low Texture / Flat Patch): Uniform flat target patch (std < 2.0). Validate via check_roi_texture and validate_rois; assert is_valid is False and error list contains insufficient texture warning.
     - Sub-case T6b (Severe Blur): Apply Gaussian blur (sigma=25.0) to frame; process with PhaseCorrelationTracker; assert mean phase correlation response drops below 0.15 (empirically ~0.065), and classify_signal_quality returns "LOW_SIGNAL".
     - Sub-case T6c (Illumination Flicker): Simulate 100 Hz lighting flicker at 60 FPS creating aliased 20 Hz peak in target and anchor; analyse displacement traces; assert is_anchor_contaminated returns True and status is "CONTAMINATED".
     - Sub-case T6d (Dropped Frames / Acquisition Jitter): Generate timestamp series with dropped frame intervals (> 1.5x median dt) and timing jitter (> 15%); evaluate via calculate_timestamp_stability; assert status is "REJECTED_UNSTABLE" with dropped frames > 3 and jitter >= 15%.
     - Set status to "PASS" if all 4 stress conditions are intercepted and gated correctly.
   - Implement master matrix runner run_full_validation_matrix() -> dict[str, Any]:
     - Execute T1 through T6; compile metadata (timestamp_utc, runtime_seconds, python_version, platform); structure protocols dictionary with T1..T6 results; calculate summary (total_protocols=6, passed_protocols, overall_status="PASS" if all pass else "FAIL").

2. In phasesight/cli.py:
   - Extend phasesight validate subparser per D-02 and REQ-CLI:
     - Add argument --test with choices ["all", "T1", "T2", "T3", "T4", "T5", "T6"], default "all".
     - Add argument --legacy (flag) to execute legacy 4-case validation suite.
     - Add argument --json with default Path("data/validation_results.json").
   - Update validate subcommand handler:
     - If --legacy: run run_validation_suite(), print legacy table, export JSON, return.
     - Else: run run_full_validation_matrix() (or single protocol if --test != "all").
     - Format and print structured ASCII console table:
       - Header banner: PhaseSight Proposal Validation Matrix (T1–T6) — Innovathon 2026.
       - T1 summary: Clean & Harmonic recovery metrics (f, err, RMSE, r, 2x_ratio).
       - T2 summary: Static & Null noise floor (RMS, peak prominence, signal quality, false reviews).
       - T3 summary: Uncorrected vs corrected RMSE, shake error attenuation %, suppression dB.
       - T4 summary: Multi-run Median + MAD values, nominal screening status (Normal, 0 triggers).
       - T5 summary: Changed clip status (Review, z-scores, non-diagnostic disclosure confirmation).
       - T6 summary: Interception verification for T6a (texture), T6b (blur), T6c (flicker), T6d (drops).
       - Footer banner: Overall Verdict (ALL 6 PROPOSAL VALIDATION PROTOCOLS PASSED 100%).
     - Save complete machine-readable report to args.json, creating parent directories safely.

3. In tests/test_validation_matrix.py:
   - Author comprehensive automated test suite covering:
     - test_t1_synthetic_motion: assert T1 status == "PASS", frequency error < 0.05 Hz, clean RMSE < 0.10 px, harmonic RMSE < 0.15 px, correlation >= 0.90, harmonic ratio > 0.04.
     - test_t2_negative_control: assert T2 status == "PASS", pure static RMS < 0.08 px, null RMS < 0.08 px, signal_quality == "LOW_SIGNAL", false reviews == 0.
     - test_t3_camera_shake_cancellation: assert T3 status == "PASS", uncorrected RMSE > 0.40 px, corrected RMSE < 0.16 px, attenuation >= 60.0%, suppression >= 10.0 dB, correlation jump >= 0.30.
     - test_t4_baseline_repeatability: assert T4 status == "PASS", frequency MAD < 0.01 Hz, RMS MAD < 0.01 px, constituent runs evaluated as "Normal", 0 false triggers.
     - test_t5_change_detection: assert T5 status == "PASS", evaluation status == "Review", z_rms >= 3.0, z_harm >= 3.0, interpretation matches NON_DIAGNOSTIC_INTERPRETATION.
     - test_t6_image_quality_stress: assert T6 status == "PASS", all 4 sub-cases pass (texture rejected, blur low-signal, flicker contaminated, drops rejected-unstable).
     - test_run_full_validation_matrix: assert overall_status == "PASS", total_protocols == 6, passed_protocols == 6.
     - test_cli_validate_matrix_stdout_and_json: run cli main with validate --json, verify table printed to stdout, verify JSON report written and valid.
     - test_cli_validate_single_test: verify --test T3 runs only T3 protocol.
     - test_cli_validate_legacy_flag: verify --legacy runs original 4-case suite.
  </action>
  <verify>
    <automated>./.venv/bin/pytest tests/test_validation_matrix.py tests/test_validation_suite.py -v && ./.venv/bin/python -m phasesight.cli validate --json data/validation_results.json</automated>
  </verify>
  <done>
All 6 Proposal validation protocols (T1–T6) are implemented in phasesight/validation.py and pass with verified numerical criteria; run_validation_suite() maintains 100% backward compatibility; phasesight validate prints structured console table and exports JSON; and all unit tests in tests/test_validation_matrix.py pass.
  </done>
</task>

<task type="auto">
  <name>Task 2: Comprehensive Evaluator Demonstration Guide (`DEMO_GUIDE.md`)</name>
  <files>DEMO_GUIDE.md</files>
  <action>
Author an interactive, end-to-end 8-stage demonstration walkthrough script in DEMO_GUIDE.md per D-03 and REQ-DEMO, enabling hackathon evaluators to replicate and inspect every capability of PhaseSight in under 10 minutes.

Structure DEMO_GUIDE.md with clear Markdown formatting, Mermaid diagrams, callout blocks, reproducible terminal commands, and expected screen outputs:

1. Title & Executive Overview:
   - PhaseSight Evaluator Demonstration Guide (Prasunex Innovathon 2026).
   - High-level workflow diagram (Mermaid flowchart from acquisition -> phase correlation tracker -> Welch PSD -> baseline -> screening -> workbench UI).
   - Estimated completion time: 8–10 minutes.

2. Prerequisites & Quickstart:
   - System requirements: Python 3.13+, macOS / Linux / Windows.
   - Activating virtual environment: source .venv/bin/activate.
   - Automated test suite check: pytest -q (verifying all 85+ tests pass in ~18 seconds).

3. Stage 1: Automated Proposal Validation Matrix (CLI):
   - Command: phasesight validate --json data/validation_results.json.
   - Explanation of all 6 protocols (T1: Known motion, T2: Static noise floor, T3: Camera shake cancellation, T4: Baseline repeatability, T5: Change detection, T6: Image quality stress).
   - Reproduction of the structured ASCII table output and guidance on inspecting data/validation_results.json.

4. Stage 2: Command-Line Inspection of Pre-Packaged Clips:
   - Ingesting data/portable/baseline.mp4, data/portable/changed.mp4, and data/portable/camera_only.mp4.
   - Command: phasesight inspect data/portable/baseline.mp4 --target 360,110,160,160 --anchor 60,100,160,160 --out data/portable/out_baseline.
   - Command: phasesight compare data/portable/out_baseline/baseline_summary.json data/portable/out_changed/changed_summary.json --out comparison_change.json (observing WARNING_CHANGE badge, +48.5% RMS change, dominant frequency 8.5 Hz).
   - Command: phasesight compare data/portable/out_baseline/baseline_summary.json data/portable/out_camera_only/camera_only_summary.json (observing INSUFFICIENT_SIGNAL rejection due to anchor contamination at 20.1 Hz).

5. Stage 3: Launching the Local Operator Workbench:
   - Command: phasesight ui --port 8501.
   - Navigating browser to http://localhost:8501.
   - Overview of the 6-tab interface architecture:
     - Tab 1: Video Inspection & Live Acquisition
     - Tab 2: Asset Management & ROI Profiles
     - Tab 3: Baseline Recording Wizard
     - Tab 4: 1-to-1 Comparison
     - Tab 5: Inspection History & Trend Exploration
     - Tab 6: About & System Boundaries

6. Stage 4: Asset Registration & Real-Time Texture Validation (Tab 2):
   - Registering Centrifugal Pump P-101.
   - Setting Target ROI: 360, 110, 160, 160; Anchor ROI: 60, 100, 160, 160; Expected FPS: 60.
   - Demonstrating the interactive ROI bounding box overlay (green target, orange anchor).
   - Showing live standard deviation badge (std >= 2.0 px) and explaining why low-texture surfaces are rejected.
   - Committing asset to SQLite persistence.

7. Stage 5: Baseline Recording Wizard (Tab 3):
   - Ingesting 3 healthy baseline runs for Centrifugal Pump P-101.
   - Reviewing the Median + Scaled MAD feature table (dominant frequency 8.509 Hz with MAD 0.000 Hz, RMS displacement 0.233 px with MAD 0.000 px).
   - Highlighting zero-MAD epsilon protection and explaining the confidence gate.
   - Committing the baseline to SQLite database and NPZ array storage.

8. Stage 6: Live Webcam Stream & Mock Capture with Frame-Rate Stability Card (Tab 1):
   - Selecting Live Webcam Stream mode.
   - Entering source: mock:0 (deterministic virtual camera) or physical hardware index 0.
   - Clicking Grab Preview Frame to inspect ROI placement.
   - Clicking Record Live Capture (5.0s recording buffer with real-time progress bar).
   - Deep-dive into the Frame-Rate Stability Card:
     - Status Badge: [🟢 STABLE]
     - Measured Empirical FPS: 1.0 / median(dt)
     - Timing Jitter: std(dt) / median(dt) (< 5% for mock:0)
     - Robust Jitter: 1.4826 * MAD / median(dt)
     - Dropped Frames Count: 0 missing
     - Large Stalls: 0 gaps
   - Showing automated quality gating: how a stable capture automatically unlocks the Run Full Video Analysis pipeline.

9. Stage 7: Statistical Screening & Inspection History Exploration (Tabs 4 & 5):
   - Screening the changed clip against the established pump baseline.
   - Observing robust z-score calculation and the Review status badge (z_rms = +22.54, z_harm = +4.77).
   - Verifying the non-diagnostic interpretation callout.
   - Navigating to Tab 5 (Inspection History): filtering by Centrifugal Pump P-101, inspecting the interactive Plotly/Matplotlib displacement and Welch PSD traces loaded on-demand from NPZ storage.
   - Logging an operator Review Event with notes ("Inspected pump coupling; scheduled routine alignment") and verifying the immutable audit trail in SQLite.

10. Stage 8: Non-Negotiable System Boundaries & Technical Disclosures (Tab 6):
    - Explicit review of all five technical boundaries per D-05:
      - 1. Pixel-Domain Only: All measurements and baselines are strictly in image pixels. No physical millimetres without in-situ calibration.
      - 2. 2D Planar Translation Only: OpenCV phase correlation measures in-plane translation; no 3D motion, rotation, zoom, or rolling shutter claims.
      - 3. Anchor Dependency: Static textured anchor is mandatory for camera shake cancellation.
      - 4. Screening vs Diagnosis: Status flags represent measured statistical shifts against baseline, not specific mechanical fault diagnosis.
      - 5. Separation of Measurement and Magnification: Riesz motion magnification is an optional visual branch that never feeds numerical alert gates.

11. Troubleshooting & FAQ:
    - Camera access permissions (macOS TCC).
    - Port collisions and overriding with --port.
    - Headless operation fallback via CLI.
  </action>
  <verify>
    <automated>test -f DEMO_GUIDE.md && python -c "content = open('DEMO_GUIDE.md').read(); assert all(f'Stage {i}' in content for i in range(1, 9)), 'Missing walkthrough stages'"</automated>
  </verify>
  <done>
DEMO_GUIDE.md is created with complete 8-stage interactive walkthrough, reproducible CLI and UI commands, expected outputs, troubleshooting advice, and explicit non-negotiable boundary statements.
  </done>
</task>

<task type="auto">
  <name>Task 3: Technical Documentation Hardening & Benchmark Dataset Report (`README.md`, `TEST_REPORT.md`)</name>
  <files>README.md, TEST_REPORT.md</files>
  <action>
Update and harden README.md and TEST_REPORT.md per D-04, D-05, and REQ-DOCS, documenting complete numerical evidence, public benchmark dataset protocols, and non-negotiable boundaries.

1. In README.md:
   - Update project title, badges, and headline to reflect complete PhaseSight Prototype v0.1.0 across Phases 1 through 7.
   - Prominently feature the Non-Negotiable Boundaries callout in the executive summary per D-05 (Pixel-Domain Only, 2D Translation Only, Anchor Dependency, Screening vs Diagnosis, Separation of Measurement and Magnification).
   - Add Demonstration Quickstart section pointing directly to DEMO_GUIDE.md with 3-line quickstart instructions.
   - Update System Architecture section with high-level component diagram (Acquisition Engine, Phase Correlation Tracker, Welch PSD Signal Engine, Statistical Baseline Engine, Local Persistence Layer, Streamlit Operator Workbench).
   - Provide complete CLI Reference documenting all 10 subcommands with syntax, arguments, and usage examples:
     - phasesight validate (with --json, --test, --legacy)
     - phasesight generate-synthetic
     - phasesight inspect
     - phasesight compare
     - phasesight build-baseline
     - phasesight assess
     - phasesight db-info
     - phasesight asset (create, list)
     - phasesight capture (with --duration, --fps, --out, --json)
     - phasesight ui (with --port, --host)
   - Document Streamlit Workbench 6 tabs and operator workflows.
   - Document Test Suite execution instructions (pytest, phasesight validate).

2. In TEST_REPORT.md:
   - Update test report header: Run date (19 November 2026), environment (Python 3.13.15, OpenCV 4.13.0, NumPy 2.3.5, SciPy 1.17.0, Streamlit 1.67.0, pytest 9.2.0), overall status (85+ automated tests passing, 6/6 proposal validation protocols passing).
   - Add Comprehensive Automated Test Suite summary detailing test breakdown across all 9 test modules:
     - tests/test_tracker.py (sub-pixel accuracy, anchor subtraction, reference protection, ROI texture)
     - tests/test_analysis.py (Welch PSD, quadratic interpolation, harmonic ratio, signal quality, anchor contamination)
     - tests/test_video_pipeline.py (MP4 encode/decode, synthetic end-to-end analysis)
     - tests/test_baseline.py (multi-run aggregation, Median + MAD, robust z-scores, zero-MAD epsilon, confidence gate)
     - tests/test_storage.py (SQLite schema, assets, baselines, inspection runs, review events, NPZ arrays)
     - tests/test_capture.py (monotonic timing, empirical FPS, jitter ratio, dropped frame detection, MockVideoCapture)
     - tests/test_ui.py (headless AppTest for tabs 1-5, asset creation, baseline wizard, mock live capture)
     - tests/test_validation_suite.py (legacy 4-case backward compatibility)
     - tests/test_validation_matrix.py (T1-T6 proposal protocols and CLI integration)
   - Add Quantitative Proposal Validation Matrix Table (T1–T6):
     - Protocol T1 (Synthetic Known Motion): Clean case f=8.503 Hz (err=0.003 Hz), RMSE=0.055 px, r=0.991; Harmonic case f=8.504 Hz, RMSE=0.111 px, 2x_ratio=0.061, r=0.935. Status: PASS.
     - Protocol T2 (Static Negative Control): Pure static RMS=0.032 px, peak=7.1 dB, LOW_SIGNAL, 0 false reviews; Camera shake only RMS=0.052 px, peak=7.2 dB, LOW_SIGNAL, 0 false reviews. Status: PASS.
     - Protocol T3 (Camera-Motion Control): Uncorrected RMSE=0.466 px (r=0.512) vs Corrected RMSE=0.135 px (r=0.906); 71.0% error reduction (10.8 dB shake suppression). Status: PASS.
     - Protocol T4 (Baseline Repeatability): >= 3 healthy runs, frequency MAD=0.000 Hz, RMS MAD=0.000 px, screening nominal runs yields 100% Normal status (0 false triggers, |z_robust| < 3.0). Status: PASS.
     - Protocol T5 (Controlled Change Detection): Changed clip screening triggers status Review (z_rms=+22.54, z_harm=+4.77); non-diagnostic disclosure string verified. Status: PASS.
     - Protocol T6 (Image-Quality Stress): T6a low texture rejected (std < 2.0); T6b severe blur degraded (response 0.065 < 0.15 -> LOW_SIGNAL); T6c flicker contaminated (shared peak 20.1 Hz -> CONTAMINATED); T6d dropped frames rejected (jitter 32.4% > 15%, 8 drops -> REJECTED_UNSTABLE). Status: PASS.
   - Add Public Benchmark Dataset Evaluation Protocol:
     - Document official public datasets for physical validation:
       1. Mendeley High-Speed Rotor Video Dataset: 500 FPS video synchronized with 1 kHz eddy-current displacement sensors (URL: https://data.mendeley.com/datasets/47y7rwc2yg/1, DOI: 10.17632/47y7rwc2yg.1).
       2. DMD Lab Structural Motion Dataset: 240 FPS high-speed video of vibrating cantilever beam with accelerometer ground truth (URL: https://zenodo.org/records/18021913).
       3. MIT CSAIL Phase-Based Video Processing Dataset: Sub-harmonic and subtle motion benchmarks (URL: https://people.csail.mit.edu/nwadhwa/phase-video/).
     - Provide protocol for downloading Mendeley dataset, extracting target and anchor ROIs from rotor housing, running phasesight inspect with --fps 500.0, and comparing computed Welch PSD against eddy-current displacement sensor PSD.
   - Formal Statement of Capabilities and Boundaries:
     - Explicit enumeration of what the results prove and what they do NOT claim per D-05.
  </action>
  <verify>
    <automated>python -c "r = open('README.md').read(); t = open('TEST_REPORT.md').read(); assert 'Mendeley' in t and '71.0%' in t and 'DEMO_GUIDE.md' in r and 'Pixel-Domain Only' in r, 'Documentation verification failed'" && ./.venv/bin/pytest -v</automated>
  </verify>
  <done>
README.md and TEST_REPORT.md are completely updated and hardened with full prototype architecture, all 10 CLI commands, 6 UI tabs, verified numerical results for all 85+ tests and T1–T6 matrix, Mendeley rotor benchmark protocols, and explicit non-negotiable boundaries.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Evaluator / CLI Input → Validation Suite Engine | Untrusted command-line arguments (e.g. `--test`, `--json` file path) passed to validation runners in `phasesight/validation.py` and `phasesight/cli.py`. |
| Synthetic Frame Generator → Image Processing Pipeline | Deterministic mathematical frame generation in `phasesight/synthetic.py` feeding phase correlation and spectral analysis. |
| Pre-Packaged Video Files → Video Ingestion & Gating | Encoded MP4 containers (`baseline.mp4`, `changed.mp4`, `camera_only.mp4`) decoded by OpenCV `VideoCapture` and processed through ROI validation and signal gating. |
| Benchmark Sensor Data → Frequency Comparison | Public external sensor datasets (Mendeley Rotor eddy-current sensor CSVs) compared against video-derived Welch PSD. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-07-01 | Tampering / Path Traversal | `phasesight/cli.py:validate` | medium | mitigate | Sanitize and resolve the `--json` output file path using `Path(json_path).resolve()`, ensuring parent directories are created safely (`mkdir(parents=True, exist_ok=True)`) and preventing directory traversal or arbitrary file writes. |
| T-07-02 | Denial of Service / CPU Exhaustion | `phasesight/validation.py:run_full_validation_matrix` | medium | mitigate | Bound synthetic clip duration to 10.0 seconds and frame resolution to $640\times 360$ across all synthetic matrix protocols (T1, T2, T3, T6), guaranteeing the entire T1–T6 matrix completes in under 20 seconds on standard laptop hardware without exhausting memory or thread pools. |
| T-07-03 | Repudiation / Diagnostic Misrepresentation | `phasesight/baseline.py`, `phasesight/validation.py:validate_t5_controlled_change_detection`, `DEMO_GUIDE.md`, `README.md`, `TEST_REPORT.md` | high | mitigate | Strictly enforce the non-diagnostic disclosure policy (`NON_DIAGNOSTIC_INTERPRETATION` string) across T5 verification, CLI reports, walkthrough scripts, and technical documentation. Reject any wording claiming specific mechanical fault diagnosis (bearing, gear, unbalance, RUL). |
| T-07-04 | Integrity / Non-Deterministic Numerical Failures | `phasesight/synthetic.py`, `phasesight/validation.py` | medium | mitigate | Use explicit seeded random number generators (`np.random.default_rng(config.seed)`) in all synthetic generation calls, ensuring 100% deterministic, cross-platform reproducible numerical results across macOS, Linux, and Windows. |
| T-07-05 | Denial of Service / Matplotlib Sandbox Permission Denial | `phasesight/ui_helpers.py`, test harnesses | low | mitigate | Set `MPLCONFIGDIR` to a temporary writable directory (`tempfile.gettempdir()`) prior to Matplotlib initialization, preventing sandbox permission errors when generating static plots. |
| T-07-SC | Tampering / Supply Chain | `pyproject.toml` | high | mitigate | Rely exclusively on verified, locally installed dependencies (`opencv-python==4.13.0`, `numpy==2.3.5`, `scipy==1.17.0`, `streamlit==1.67.0`, `pytest==9.2.0`). Zero new external packages or network dependencies are introduced in Phase 7. |
</threat_model>

<verification>
Automated verification commands:
1. Full Automated Test Suite: `./.venv/bin/pytest -v` (85+ tests passing across all 9 test modules with zero regressions).
2. Proposal Validation Matrix Test Suite: `./.venv/bin/pytest tests/test_validation_matrix.py -v`.
3. Legacy Validation Suite Regression: `./.venv/bin/pytest tests/test_validation_suite.py -v` (confirming 100% backward compatibility).
4. CLI Validation Matrix Execution & JSON Export: `./.venv/bin/python -m phasesight.cli validate --json data/validation_results.json`.
5. Walkthrough Script Completeness: `python -c "content = open('DEMO_GUIDE.md').read(); assert all(f'Stage {i}' in content for i in range(1, 9)), 'Missing walkthrough stages'"`.
6. Documentation Evidence & Boundary Audit: `python -c "r = open('README.md').read(); t = open('TEST_REPORT.md').read(); assert 'Mendeley' in t and '71.0%' in t and 'DEMO_GUIDE.md' in r and 'Pixel-Domain Only' in r, 'Documentation verification failed'"`.
</verification>

<success_criteria>
1. `phasesight/validation.py` implements modular runners `validate_t1_synthetic_motion`, `validate_t2_static_negative_control`, `validate_t3_camera_shake_cancellation`, `validate_t4_baseline_repeatability`, `validate_t5_controlled_change_detection`, `validate_t6_image_quality_stress`, and `run_full_validation_matrix()`.
2. All 6 Proposal Page 5 validation protocols pass with rigorous numerical criteria:
   - T1: Freq error <= 0.05 Hz, RMSE <= 0.10 px clean / <= 0.15 px noisy, correlation r >= 0.90, harmonic ratio > 0.04.
   - T2: Residual noise RMS <= 0.08 px, prominence < 10 dB, status LOW_SIGNAL, zero false reviews.
   - T3: Anchor subtraction achieves >= 60% error reduction (empirically 71.0%), >= 10 dB shake suppression, and correlation jump to >= 0.90.
   - T4: Multi-run baseline aggregation (>= 3 captures) yields MAD < 0.01 Hz and MAD < 0.01 px; screening nominal captures yields 100% Normal status (0 false triggers).
   - T5: Screening changed clip triggers Review status (|z_robust| >= 3.0), isolates deviant features, and verifies non-diagnostic disclosure.
   - T6: Intercepts low texture (std < 2.0), severe blur (response < 0.15 -> LOW_SIGNAL), flicker (CONTAMINATED), and dropped frames (REJECTED_UNSTABLE).
3. `run_validation_suite()` maintains 100% backward compatibility for existing callers and legacy tests.
4. `phasesight validate` renders a structured ASCII console summary table and exports full machine-readable JSON reports.
5. `tests/test_validation_matrix.py` provides 100% automated coverage for T1–T6 protocols and CLI options.
6. `DEMO_GUIDE.md` delivers a comprehensive 8-stage interactive demonstration walkthrough executable in under 10 minutes.
7. `README.md` and `TEST_REPORT.md` are hardened with complete numerical evidence from 85+ tests and T1–T6 matrix, public benchmark dataset evaluation protocols (Mendeley Rotor at 500 FPS + eddy-current sensors), and non-negotiable boundaries.
8. Entire test suite passes cleanly (`pytest -v`) with zero regressions across the codebase.
</success_criteria>

<output>
Create `.planning/phases/07-final-validation/07-01-SUMMARY.md` when execution is complete.
</output>
