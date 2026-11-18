---
phase: 03-statistical-baseline-engine
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - phasesight/baseline.py
  - tests/test_baseline.py
  - phasesight/cli.py
  - phasesight/app.py
autonomous: true
requirements:
  - REQ-BASE-01
  - REQ-BASE-02
  - REQ-BASE-03
  - REQ-BASE-04
  - REQ-BASE-05
  - REQ-BASE-06
  - REQ-BASE-07
  - REQ-BASE-08
  - REQ-BASE-09

estimate:
  tokens: 45000
  raw_tokens: 22000
  tasks: 5
  confidence: high

must_haves:
  truths:
    - "Ingestion of fewer than 3 runs raises a ValueError enforcing quorum."
    - "Robust statistics compute Median and MAD scaled by 1.4826 with physical noise floor epsilon preventing division by zero."
    - "Confidence Gate classifies low signal or contaminated anchor runs as Low confidence with explicit reasons."
    - "Review Gate computes standardized robust z-scores across dominant frequency, RMS displacement, peak-to-median dB, and harmonic ratio, triggering Review if any |z| >= 3.0."
    - "BaselineRecord and BaselineEvaluation serialize cleanly to JSON casting NumPy scalars to native Python floats."
    - "CLI provides build-baseline and assess subcommands producing formatted summaries and JSON output."
    - "Streamlit Workbench Tab 2 renders statistical baseline selection, status badges, z-score charts, and feature deviation tables."
    - "Strict technical boundaries are respected: pixel domain only, 2D translation only, screening without fault diagnosis."
  artifacts:
    - phasesight/baseline.py
    - tests/test_baseline.py
    - phasesight/cli.py
    - phasesight/app.py
  key_links:
    - "phasesight/baseline.py consumes summary dictionaries produced by phasesight/video.py and phasesight/analysis.py"
    - "phasesight/cli.py invokes build_baseline and evaluate_run_against_baseline from phasesight/baseline.py"
    - "phasesight/app.py renders BaselineRecord and BaselineEvaluation from phasesight/baseline.py"
    - "tests/test_baseline.py verifies all 15 deterministic scenarios specified in 03-RESEARCH.md"
---

<objective>
Implement the Phase 3 Statistical Baseline Engine for PhaseSight. Transition the system from pairwise single-video comparison to industrial-grade robust statistical screening. Aggregate multiple healthy baseline captures ($N \ge 3$) using Median and Median Absolute Deviation (MAD) scaled by $1.4826$, implement feature-specific physical noise floors ($\epsilon$), execute a two-stage screening architecture (Confidence Gate followed by Review Gate), provide comprehensive automated tests, and integrate with both the CLI and Streamlit Operator Workbench.

Purpose: Eliminate false positives and false negatives caused by ambient fluctuations, operator presence, and discrete frequency bin quantization, delivering reliable statistical change screening in the pixel domain.
Output: `phasesight/baseline.py`, `tests/test_baseline.py`, enhanced `phasesight/cli.py`, and enhanced `phasesight/app.py`.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/03-statistical-baseline-engine/03-RESEARCH.md
@phasesight/analysis.py
@phasesight/video.py
@phasesight/cli.py
@phasesight/app.py
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Core Dataclasses, Math, and Statistics Engine</name>
  <files>phasesight/baseline.py</files>
  <action>
Create phasesight/baseline.py providing foundational mathematical constants, feature noise floors, dataclasses, robust estimators, and serialization functions per D-01, D-03, D-05, D-06, REQ-BASE-02, REQ-BASE-03, and REQ-BASE-07.
Define NORMAL_SCALE_FACTOR as 1.482602218505602.
Define DEFAULT_FEATURE_EPSILONS dictionary with feature-specific physical noise floors: dominant_frequency_hz = 0.020 Hz, rms_displacement_px = 0.005 px, peak_to_median_db = 1.000 dB, second_harmonic_ratio = 0.010 per REQ-BASE-03.
Define frozen dataclasses:
- FeatureStats: median (float | None), mad (float | None), scale_factor (float), epsilon (float), sample_count (int), raw_values (list[float]).
- AxisBaseline: dominant_frequency_hz (FeatureStats), rms_displacement_px (FeatureStats), peak_to_median_db (FeatureStats), second_harmonic_ratio (FeatureStats | None = None).
- BaselineRecord: baseline_id (str), asset_id (str), created_at (str), run_count (int), target_roi (dict[str, int]), anchor_roi (dict[str, int]), sampling_rate_hz (float), x_axis (AxisBaseline), y_axis (AxisBaseline), baseline_run_ids (list[str]), notes (str), version (str = "1.0").
- FeatureDeviation: feature_name (str), axis (str), current_value (float | None), baseline_median (float | None), baseline_mad (float | None), z_robust (float | None), is_trigger (bool), notes (str).
- BaselineEvaluation: status (str), confidence_passed (bool), reasons (list[str]), trigger_features (list[str]), deviations (dict[str, FeatureDeviation]), z_threshold (float), baseline_id (str), asset_id (str), evaluated_at (str), interpretation (str).
Implement compute_robust_stats(values, epsilon, scale_factor=NORMAL_SCALE_FACTOR) -> FeatureStats using numpy.median to calculate sample median and Median Absolute Deviation around the median, filtering out None and non-finite values per D-01.
Implement to_dict, from_dict, to_json, and from_json methods on BaselineRecord and BaselineEvaluation, plus module-level serialize_baseline and deserialize_baseline functions, ensuring all NumPy floating-point types are explicitly cast to native Python floats to prevent JSON serialization errors per REQ-BASE-07.
Include default non-diagnostic interpretation text in BaselineEvaluation emphasizing that Review indicates a statistical shift against reference baseline and not a diagnosed mechanical fault per D-05.
Avoid physical unit conversions (mm, velocity, acceleration); all metrics remain strictly in pixel domain per D-06.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from phasesight.baseline import BaselineRecord, FeatureStats, compute_robust_stats, DEFAULT_FEATURE_EPSILONS; stats = compute_robust_stats([8.50, 8.51, 8.52], epsilon=DEFAULT_FEATURE_EPSILONS['dominant_frequency_hz']); assert stats.sample_count == 3; assert abs(stats.median - 8.51) < 1e-6; print('Task 1 math verified') status=OK"</automated>
  </verify>
  <done>
All dataclasses defined as frozen dataclasses, compute_robust_stats accurately calculates median and MAD with normal scale factor 1.4826, and JSON serialization roundtrips successfully with native Python types.
  </done>
</task>

<task type="auto">
  <name>Task 2: Ingestion, Validation, Confidence Gating, and Two-Stage Review Engine</name>
  <files>phasesight/baseline.py</files>
  <action>
Implement multi-run aggregation and two-stage screening evaluation functions in phasesight/baseline.py per D-01, D-02, D-03, D-04, D-05, D-06, REQ-BASE-01, REQ-BASE-02, REQ-BASE-03, REQ-BASE-04, REQ-BASE-05, and REQ-BASE-06.
Implement build_baseline(runs, *, asset_id="default_asset", min_runs=3, feature_epsilons=None, notes="") -> BaselineRecord:
- Enforce quorum check: if len(runs) < min_runs, raise ValueError with clear message citing quorum requirement per D-02 and REQ-BASE-01.
- Validate dictionary schema of each run (presence of x_axis, y_axis, target_roi or target_roi_xywh, anchor_roi or anchor_roi_xywh, and sampling_rate_hz or fps).
- Validate ROI consistency: verify target_roi and anchor_roi across all runs match within 2 pixels tolerance; raise ValueError on spatial mismatch per REQ-BASE-01.
- Validate sampling rate consistency: verify sampling rate across all runs matches within plus or minus 2 percent tolerance.
- Check baseline signal quality: verify signal_quality is VALID across all baseline runs; raise ValueError or record warning if any baseline run exhibits contamination or insufficient signal per REQ-BASE-04.
- Extract feature vectors across runs for dominant_frequency_hz, rms_displacement_px, peak_to_median_db, and second_harmonic_ratio for both x_axis and y_axis per D-03, compute FeatureStats via compute_robust_stats, and return an immutable BaselineRecord.
Implement evaluate_run_against_baseline(current, baseline, *, z_threshold=3.0, axis=None) -> BaselineEvaluation:
- Execute Stage 1 Confidence Gate per D-04 and REQ-BASE-04: check if current run signal_quality is not VALID (such as LOW_SIGNAL or CONTAMINATED), or if current ROIs differ from baseline ROIs. If confidence fails, return BaselineEvaluation with status 'Low confidence', confidence_passed=False, and explicit human-readable reasons in reasons list.
- Execute Stage 2 Review Gate per D-04, REQ-BASE-05, and REQ-BASE-06: for each evaluated axis ('x' and/or 'y') and tracked feature, calculate standardized robust deviation z = (x_curr - median) / (1.4826 * MAD + epsilon).
- Handle second_harmonic_ratio tri-state conditions cleanly per REQ-BASE-06: if both baseline and current are None, omit deviation; if baseline is None and current has valid float, calculate emergence z = x_curr / epsilon_harm; if baseline is valid and current is None, calculate drop deviation z = -median / (1.4826 * MAD + epsilon_harm).
- If any tracked feature on any evaluated axis has absolute z >= z_threshold (default 3.0), classify status as 'Review' and add feature name to trigger_features; if all absolute z < z_threshold, classify status as 'Normal'.
- Populate FeatureDeviation dictionary for every evaluated feature with axis, values, z_score, trigger flag, and explanatory notes.
- Attach non-diagnostic screening disclaimer to interpretation per D-05.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from phasesight.baseline import build_baseline, evaluate_run_against_baseline; import json; run = json.load(open('data/portable/out_baseline/baseline_summary.json')); base = build_baseline([run, run, run]); eval_res = evaluate_run_against_baseline(run, base); assert eval_res.status == 'Normal'; assert eval_res.confidence_passed is True; print('Task 2 engine verified') status=OK"</automated>
  </verify>
  <done>
build_baseline enforces N >= 3, validates ROI/FPS consistency, and builds valid BaselineRecord; evaluate_run_against_baseline correctly executes Confidence Gate and Review Gate yielding Normal, Review, or Low confidence.
  </done>
</task>

<task type="tdd">
  <name>Task 3: Unit Test Suite</name>
  <files>tests/test_baseline.py</files>
  <behavior>
    - test_build_baseline_rejects_fewer_than_3_runs: Ingesting 0, 1, or 2 runs raises ValueError citing quorum (D-02).
    - test_build_baseline_valid_3_runs: Ingesting 3 valid runs returns valid BaselineRecord with accurate medians and MADs (REQ-BASE-01, REQ-BASE-02).
    - test_zero_mad_numerical_stability: Ingesting 3 identical runs (MAD=0) with sub-noise-floor jitter (0.001 Hz) produces z ~ 0.05 and status Normal without false review (REQ-BASE-03).
    - test_outlier_resilience_breakdown_point: Ingesting [8.50, 8.51, 15.00] yields median 8.51 and MAD 0.01; outlier has zero leverage (REQ-BASE-02).
    - test_confidence_gate_low_signal: Current run with signal_quality LOW_SIGNAL yields Low confidence status with prominence reason (REQ-BASE-04, D-04).
    - test_confidence_gate_anchor_contaminated: Current run with signal_quality CONTAMINATED yields Low confidence status with anchor reason (REQ-BASE-04, D-04).
    - test_confidence_gate_baseline_contaminated: Baseline with contaminated run yields Low confidence or raises ValueError (REQ-BASE-04).
    - test_review_gate_rms_trigger: Changed RMS 0.345 px vs Baseline 0.232 px yields |z| >= 3.0 and status Review (REQ-BASE-05, D-04).
    - test_review_gate_frequency_shift: Frequency shift from 8.50 Hz to 8.80 Hz yields |z| >= 3.0 and status Review (REQ-BASE-05).
    - test_review_gate_harmonic_emergence: Harmonic ratio jump from 0.003 to 0.051 yields |z| >= 3.0 and status Review (REQ-BASE-05).
    - test_normal_run_within_bounds: Run with metrics close to baseline yields all |z| < 1.0 and status Normal (D-04).
    - test_missing_harmonic_both_none: Both baseline and current have second_harmonic_ratio None; runs cleanly without error (REQ-BASE-06).
    - test_missing_harmonic_emergence: Baseline has None and current has float ratio; evaluates as emergence triggering Review (REQ-BASE-06).
    - test_json_roundtrip_serialization: BaselineRecord and BaselineEvaluation serialize to JSON and reload identically (REQ-BASE-07).
    - test_roi_mismatch_rejection: Baseline runs with divergent target ROIs raise ValueError (REQ-BASE-01).
    - test_real_portable_data_evaluation: Baseline created from out_baseline/baseline_summary.json evaluated against out_changed/changed_summary.json and out_camera_only/camera_only_summary.json.
  </behavior>
  <action>
Create tests/test_baseline.py implementing all 16 deterministic unit tests specified in PHASE-03-RESEARCH.md Section 10 per REQ-BASE-09, D-01, D-02, D-03, D-04, D-05, and D-06.
Construct synthetic summary dictionaries using helper functions that provide realistic signal metrics matching data/portable/out_baseline/baseline_summary.json schema.
Verify edge cases including zero-MAD stability, 50 percent breakdown point with extreme single-run outlier, Confidence Gate rejections, Review Gate deviations across X and Y axes, tri-state harmonic ratio handling, JSON serialization fidelity, ROI mismatch checks, and evaluation against real portable sample outputs.
Run tests via pytest to verify all test cases pass without regressions.
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_baseline.py -v</automated>
  </verify>
  <done>
All 16+ unit tests in tests/test_baseline.py pass cleanly with 100 percent assertion pass rate.
  </done>
</task>

<task type="auto">
  <name>Task 4: CLI Integration</name>
  <files>phasesight/cli.py</files>
  <action>
Extend phasesight/cli.py with subcommands build-baseline and assess (with evaluate-baseline support) per REQ-BASE-08, D-02, D-04, D-05, and D-06.
In _build_parser(), add build-baseline parser accepting:
- runs: nargs='+', list of paths to inspection summary JSON files.
- --asset-id: str, default 'default_asset'.
- --out: Path, default Path('baseline.json').
- --min-runs: int, default 3.
- --notes: str, default ''.
In _build_parser(), add assess parser accepting:
- current: Path, path to current inspection summary JSON.
- baseline: Path, path to BaselineRecord JSON file.
- --threshold: float, default 3.0.
- --axis: choices=['x', 'y', 'both'], default 'both'.
- --out: Path, default Path('assessment_report.json').
In main(), implement build-baseline handler:
- Load JSON summary files, call build_baseline from phasesight.baseline.
- Serialize the resulting BaselineRecord to the target file.
- Print formatted CLI summary table showing asset ID, run count, ROI coordinates, and feature medians/MADs for X and Y axes.
In main(), implement assess handler:
- Load current summary JSON and baseline JSON, invoke evaluate_run_against_baseline from phasesight.baseline.
- Serialize BaselineEvaluation report to target output file.
- Display formatted terminal summary with prominent status banner: NORMAL in green, REVIEW in yellow/red, or LOW CONFIDENCE in gray/cyan.
- List confidence failure reasons or triggered feature deviations with z-scores.
- Print standard disclaimer reminding operator that screening flags indicate statistical shifts and not mechanical fault diagnosis per D-05.
  </action>
  <verify>
    <automated>.venv/bin/python -m phasesight.cli --help && .venv/bin/python -m phasesight.cli build-baseline --help && .venv/bin/python -m phasesight.cli assess --help</automated>
  </verify>
  <done>
CLI subcommands build-baseline and assess are registered, parse arguments correctly, produce serialized JSON output files, and print structured terminal banners.
  </done>
</task>

<task type="auto">
  <name>Task 5: Workbench UI Integration</name>
  <files>phasesight/app.py</files>
  <action>
Enhance Streamlit Workbench UI Tab 2 in phasesight/app.py to support statistical multi-run baselines alongside single-run comparison per REQ-BASE-08, D-04, D-05, and D-06.
In render_comparison_tab(), add radio or segment selector for baseline comparison mode: 'Pairwise (Single-Run vs Baseline)' vs 'Statistical Engine (Multi-Run Baseline, Robust z-score)'.
For Statistical Engine mode, provide options to:
- Load an existing BaselineRecord JSON file (from pre-computed sample or file uploader).
- Build a new baseline dynamically by uploading 3 or more summary JSON files.
For current inspection selection:
- Allow using latest analysis from Tab 1 session state, uploading an inspection summary JSON, or choosing a sample clip summary.
Provide parameter controls for robust z-threshold (slider or number input, default 3.0) and axis selection ('both', 'x', 'y').
When evaluated, invoke evaluate_run_against_baseline from phasesight.baseline and render prominent status banner matching design tokens:
- NORMAL (green success banner): 'Status: NORMAL — All vibration metrics within expected statistical bounds.'
- REVIEW (orange warning banner): 'Status: REVIEW — Significant deviation detected against baseline.' with alert listing triggering features and deviation magnitudes.
- LOW CONFIDENCE (neutral info banner): 'Status: LOW CONFIDENCE — Measurement quality insufficient for screening.' with clear reasons (low prominence or anchor contamination).
Render interactive Altair or Streamlit bar chart of z_robust scores across features with horizontal dashed threshold lines at +3.0 and -3.0.
Render detailed feature metrics table comparing Baseline Median, MAD, Current Value, z_robust, and Screening Flag for all tracked features on both axes.
Include standard disclaimer emphasizing that Review indicates a measured statistical shift and does not constitute a mechanical fault diagnosis per D-05.
Add download button for assessment_report.json.
Verify tests in tests/test_ui.py continue to pass cleanly without exceptions.
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_ui.py -v</automated>
  </verify>
  <done>
Workbench UI Tab 2 renders statistical baseline options, executes evaluation, visualizes z-scores and feature tables, and tests in test_ui.py pass cleanly without exceptions.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| File System / JSON Summaries -> CLI | Untrusted or corrupted JSON summary files parsed from disk by `build-baseline` and `assess` subcommands. |
| Browser Upload -> Streamlit UI | Operator-uploaded JSON summaries or video files crossing web interface into Python memory. |
| Ingestion -> Statistical Computation | Numerical inputs (frequencies, displacements, ratios) evaluated by Median, MAD, and division operations. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-03-01 | Tampering / Denial of Service | `phasesight/baseline.py:build_baseline` | medium | mitigate | Enforce input size constraints, validate presence of expected schema keys, and assert `np.isfinite` and non-negative bounds on numeric metrics. |
| T-03-02 | Denial of Service (Numerical) | `phasesight/baseline.py:evaluate_run_against_baseline` | high | mitigate | Implement feature-specific physical noise floor $\epsilon$ preventing division by zero or hypersensitive false reviews when $\text{MAD} = 0$. |
| T-03-03 | Repudiation / Information Integrity | `phasesight/baseline.py:BaselineEvaluation` | high | mitigate | Enforce strict non-diagnostic interpretation text; output flags are strictly `Normal`, `Review`, `Low confidence`. Reject any diagnostic failure attribution per D-05. |
| T-03-04 | Elevation of Privilege / Injection | `phasesight/cli.py` & `phasesight/app.py` | low | mitigate | Use standard library `json.loads` / `json.dumps` exclusively; avoid `eval`, `exec`, or `pickle`. Sanitize file paths with `Path`. |
| T-03-SC | Tampering | Python dependencies | high | mitigate | Package legitimacy gate verified; standard stack uses numpy and scipy already audited in pyproject.toml. |
</threat_model>

<verification>
Automated verification commands:
1. Math and Dataclasses: `.venv/bin/python -c "from phasesight.baseline import BaselineRecord, compute_robust_stats; print('Math verified')"`
2. Unit Test Matrix: `.venv/bin/pytest tests/test_baseline.py -v` (16+ passing tests)
3. CLI Verification: `.venv/bin/python -m phasesight.cli build-baseline --help && .venv/bin/python -m phasesight.cli assess --help`
4. UI Regression: `.venv/bin/pytest tests/test_ui.py -v`
5. Full Test Suite: `.venv/bin/pytest -v` (40+ passing tests across all test suites)
</verification>

<success_criteria>
1. `phasesight/baseline.py` exists with complete implementations of `BaselineRecord`, `FeatureStats`, `BaselineEvaluation`, `build_baseline`, and `evaluate_run_against_baseline`.
2. Multi-run quorum ($N \ge 3$) is strictly enforced with `ValueError`.
3. Feature-specific noise floor $\epsilon$ prevents false alarms when $\text{MAD} = 0$.
4. Two-stage screening cleanly separates Confidence Gate (`Low confidence`) from Review Gate (`Review` vs `Normal`).
5. All 16+ deterministic unit tests in `tests/test_baseline.py` pass cleanly.
6. CLI subcommands `build-baseline` and `assess` execute and save valid JSON outputs.
7. Workbench UI Tab 2 allows multi-run statistical evaluation with interactive $z$-score visualization.
8. Non-negotiable technical boundaries (pixel domain only, 2D translation only, screening not fault diagnosis) are strictly upheld throughout.
</success_criteria>

<output>
Create `.planning/phases/03-statistical-baseline-engine/03-01-SUMMARY.md` when execution is complete.
</output>
