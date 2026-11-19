---
phase: 05-workbench-history
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - phasesight/app.py
  - phasesight/ui_helpers.py
  - tests/test_ui.py
autonomous: true
requirements:
  - HIST-01
  - HIST-02
  - HIST-03
  - HIST-04
  - HIST-05
  - HIST-06

estimate:
  tokens: 52000
  raw_tokens: 26000
  tasks: 5
  confidence: high

must_haves:
  truths:
    - "StorageManager is initialized and cached in st.session_state['storage_manager'] supporting dependency injection of in-memory StorageManager(db_path=':memory:') in headless tests."
    - "Global sidebar provides an Active Machine Asset selector (st.sidebar.selectbox) and details card displaying configured Target ROI, Anchor ROI, expected FPS, baseline status, and storage diagnostics."
    - "Selecting an asset in the sidebar automatically synchronizes its saved Target ROI, Anchor ROI, and expected FPS into Video Inspection tab input widgets without Streamlit session state collision warnings."
    - "Post-analysis in Video Inspection tab offers a 1-click Auto-Assessment card if the active asset has a stored baseline, and provides a 'Save Run to Asset History' button persisting the InspectionRunRecord and compressed NPZ RunArrays."
    - "Asset Management tab provides a complete asset catalog table, asset registration form with a 'Copy ROIs from current inspection' shortcut, parameter editor, and deletion with cascading options."
    - "Baseline Recording Wizard tab guides operators through selecting candidate runs (from history or uploaded JSONs), executes live validation (quorum N >= 3, spatial ROI consistency +/- 2 px, sampling rate consistency +/- 2%), displays a robust Median + MAD statistical preview, and persists StoredBaseline to the database."
    - "Inspection History tab renders a filterable historical run log for the active asset with colored status badges (Normal, Review, Low confidence, Unassessed), deep-dive on-demand NPZ array exploration with 2-panel displacement and Welch PSD plots, and an operator review event logging form that atomically synchronizes parent run status."
    - "Headless automated UI test suite in tests/test_ui.py uses streamlit.testing.v1.AppTest with injected in-memory storage to verify all asset synchronization, baseline wizard validation, history display, review event logging, and auto-assessment workflows."
  artifacts:
    - phasesight/app.py
    - phasesight/ui_helpers.py
    - tests/test_ui.py
  key_links:
    - "phasesight/app.py imports StorageManager, AssetRecord, StoredBaseline, InspectionRunRecord, ReviewEventRecord, and RunArrays from phasesight/storage.py"
    - "phasesight/app.py imports build_baseline, evaluate_run_against_baseline, and _rois_match from phasesight/baseline.py"
    - "phasesight/ui_helpers.py provides run_arrays_from_csv, plot_run_arrays, and status_badge helpers supporting app.py"
    - "tests/test_ui.py injects StorageManager(db_path=':memory:') into AppTest.from_file('phasesight/app.py').session_state['storage_manager']"
---

<objective>
Implement Phase 5: Workbench History & Asset Integration for PhaseSight. Transition the Streamlit operator workbench (`phasesight/app.py`) from ad-hoc single-video analysis into an integrated, asset-centric vibration screening system. Integrate the local persistence layer (`StorageManager`, SQLite `phasesight.db`, and compressed `.npz` arrays), establish a Global Sidebar Asset Anchor, enhance the Video Inspection tab with active asset ROI auto-population and 1-click auto-assessment, build a dedicated Asset Management tab with CRUD operations, create an interactive multi-run Baseline Recording Wizard enforcing quorum and spatial consistency, implement an Inspection History tab with deep-dive NPZ spectral exploration and operator review event logging, and deliver a comprehensive headless automated UI test suite in `tests/test_ui.py` using `streamlit.testing.v1.AppTest`.

Purpose: Provide industrial facility operators and test engineers with a repeatable, persistent, and auditable vibration screening workbench for physical machine assets without requiring command-line tools or loose JSON file handling.
Output: Enhanced `phasesight/app.py`, updated `phasesight/ui_helpers.py`, and comprehensive headless test suite in `tests/test_ui.py`.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/05-workbench-history/05-RESEARCH.md
@phasesight/storage.py
@phasesight/baseline.py
@phasesight/tracker.py
@phasesight/video.py
@phasesight/ui_helpers.py
@phasesight/app.py
@tests/test_ui.py
@tests/test_storage.py
</context>

<tasks>

<task type="tracer">
  <name>Task 1: StorageManager Session Caching, Global Sidebar Asset Selector, and Inspection Tab Auto-Sync & Auto-Assessment</name>
  <files>phasesight/app.py, phasesight/ui_helpers.py</files>
  <action>
Implement the core end-to-end tracer connecting the persistence layer to the Streamlit UI per D-01, D-02, D-03, D-04, HIST-01, and HIST-05.

1. In `phasesight/ui_helpers.py`:
   - Implement `run_arrays_from_csv(csv_path: str | Path, fps: float = 60.0, compute_spectra: bool = True) -> RunArrays` to convert the motion CSV generated during video analysis into a typed `RunArrays` object, extracting timestamps, relative dx/dy, target dx/dy, anchor dx/dy, and phase correlation responses. If `compute_spectra` is True, compute Welch PSD for X and Y using `phasesight.analysis.compute_welch_spectrum` and populate `x_frequencies_hz`, `x_psd_px2_per_hz`, `y_frequencies_hz`, and `y_psd_px2_per_hz`.
   - Implement `status_badge(status: str) -> str` returning standardized markdown status badges: green circle for 'Normal', red circle for 'Review', yellow circle for 'Low confidence', and white circle for 'Unassessed'.
   - Implement `sync_active_asset_rois(asset: AssetRecord | None) -> None` that updates `st.session_state` keys `tx_input`, `ty_input`, `tw_input`, `th_input`, `ax_input`, `ay_input`, `aw_input`, `ah_input`, and `fps_override_val` when an asset is selected, or falls back to default sample ROIs when no asset is selected.

2. In `phasesight/app.py`:
   - Configure Matplotlib headless config directory at the top of the file: set `os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())` before importing `matplotlib.pyplot` to eliminate permission warnings in sandboxed/headless environments.
   - Implement `get_storage_manager() -> StorageManager`: check `if "storage_manager" not in st.session_state`, initialize `st.session_state["storage_manager"] = StorageManager()`. Return `st.session_state["storage_manager"]`. This enables unit tests to inject `at.session_state["storage_manager"] = StorageManager(db_path=":memory:")` prior to `at.run()`.
   - Implement `init_session_state(sm: StorageManager) -> None`: initialize default session keys if not present (`selected_asset_id = None`, `prev_selected_asset_id = None`, and default ROI coordinate keys `tx_input`, `ty_input`, etc. using `.setdefault()`).
   - Implement `render_sidebar(sm: StorageManager) -> AssetRecord | None`:
     - Render sidebar header and machine asset selection selectbox: options include '-- None (Ad-hoc Analysis) --' followed by all assets from `sm.list_assets()` formatted as '{name} ({asset_id})'.
     - When asset selection changes, invoke `sync_active_asset_rois(active_asset)` to immediately update session state ROI coordinates and `fps_override_val`.
     - Render Active Asset Details Card: display target ROI dimensions and coordinates, anchor ROI dimensions and coordinates, expected FPS, and baseline status badge (e.g. 'bsl_01 (N=3)' or 'None').
     - Render Storage Diagnostics section: display database path, SQLite version, and count of registered assets, baselines, and runs from `sm.get_db_info()`.
   - Update `render_inspection_tab()`:
     - Update ROI coordinate widgets (`tx`, `ty`, `tw`, `th`, `ax`, `ay`, `aw`, `ah`) and FPS override widget to bind directly to session state keys (`key="tx_input"`, etc.) without passing explicit `value=` arguments, preventing Streamlit session state collision warnings.
     - Display active asset configuration badge: if an asset is active, display an info banner indicating configuration is loaded from the active asset.
     - In `display_inspection_results(summary)`:
       - If an active asset is selected and has a stored baseline via `sm.get_latest_baseline_for_asset(active_asset.asset_id)`:
         - Render a '1-Click Auto-Assessment Card' displaying reference baseline ID, healthy run count, and an assessment action button.
         - When clicked, evaluate the current run against the stored baseline using `phasesight.baseline.evaluate_run_against_baseline()`, render the verdict banner ('Normal', 'Review', 'Low confidence'), failure reasons, trigger features, and the detailed feature deviation table.
       - Render 'Save Run to Asset History' button (and an 'Auto-save runs to history' checkbox):
         - On save: convert output CSV to `RunArrays` via `run_arrays_from_csv()`, persist run via `sm.create_inspection_run(asset_id=active_asset.asset_id, video_path=summary['video'], measured_fps=summary['fps_used'], duration_s=summary['duration_s'], frames_analysed=summary['frames_analysed'], summary=summary, baseline_id=latest_base_id, arrays=arrays, status=verdict_status)`. Display confirmation with created `run_id`.
   - Update main tabs structure to render 6 tabs:
     1. Video Inspection
     2. Asset Management
     3. Baseline Wizard
     4. Inspection History
     5. Baseline Comparison
     6. Technical Boundaries & Notes
  </action>
  <verify>
    <automated>./.venv/bin/python -c "from phasesight.app import get_storage_manager; from phasesight.storage import StorageManager; import streamlit as st; sm = StorageManager(db_path=':memory:'); assert sm.get_db_info()['foreign_keys'] == 1; print('Task 1 tracer import and storage init verified') status=OK"</automated>
  </verify>
  <done>
StorageManager is cached in session state, global sidebar renders active asset selection and diagnostics, Tab 1 synchronizes ROIs and FPS from active asset without widget warnings, post-analysis offers 1-click auto-assessment against stored baseline, and runs can be saved to SQLite and NPZ.
  </done>
</task>

<task type="auto">
  <name>Task 2: Asset Management Tab — Catalog, Registration Form, Editor, and Cascading Deletion</name>
  <files>phasesight/app.py</files>
  <action>
Implement Tab 2 ('Asset Management') in `phasesight/app.py` providing complete lifecycle management for physical machine assets per D-05 and HIST-01.

1. Implement `render_asset_management_tab(sm: StorageManager) -> None`:
   - Add tab header and description explaining asset-based vibration monitoring and ROI repeatability.

2. Registered Assets Catalog:
   - Query all assets via `sm.list_assets()`.
   - If no assets exist, display an empty-state guidance card inviting the operator to register their first machine asset.
   - If assets exist, display a structured overview table showing: Asset ID, Name, Expected FPS, Nominal RPM, Target ROI (x, y, w, h), Anchor ROI (x, y, w, h), Baselines Count, Runs Count, and Updated At.
   - Include a quick 'Set as Active Asset' button or selector to switch active asset directly from the catalog.

3. Asset Registration Form:
   - Provide an expandable or container form '➕ Register New Machine Asset':
     - Text inputs: Asset Name (required), Asset ID (optional, auto-generated if blank), Description (optional).
     - Numeric input: Nominal Speed RPM (optional, float or None).
     - Numeric input: Expected FPS (default 60.0, min 1.0, max 1000.0).
     - Target ROI inputs: X, Y, Width, Height (integers >= 0, width/height >= 32).
     - Anchor ROI inputs: X, Y, Width, Height (integers >= 0, width/height >= 32).
     - Shortcut button: '📋 Copy ROIs from Current Inspection': reads current `tx_input`, `ty_input`, `tw_input`, `th_input`, `ax_input`, `ay_input`, `aw_input`, `ah_input`, and `fps_override_val` from session state and populates the form fields.
     - Validation: verify name is non-empty, ROI widths and heights are >= 32, coordinates do not overlap, and expected FPS is positive.
     - On submit: call `sm.create_asset()`, display success alert with created `asset_id`, automatically select the new asset as active in `st.session_state["selected_asset_id"]`, and call `st.rerun()`.

4. Asset Parameter Editor:
   - Provide an expandable editor '✏️ Edit Asset Parameters':
     - Select an existing asset to edit.
     - Load current parameters into form inputs (Name, Description, Nominal RPM, Expected FPS, Target ROI, Anchor ROI).
     - On submit: call `sm.update_asset()`, show confirmation, and refresh view.

5. Asset Deletion with Cascading Options:
   - Provide a collapsible danger zone '🗑️ Delete Machine Asset':
     - Select asset to delete.
     - Checkbox: 'Cascade delete all associated baselines, inspection runs, and NPZ files from disk' (default True).
     - Confirmation button with warning: 'Permanently Delete Asset'.
     - On confirmation: call `sm.delete_asset(asset_id, delete_files=cascade)`.
     - If the deleted asset was the active asset, reset `st.session_state["selected_asset_id"] = None`.
     - Display success message and call `st.rerun()`.
  </action>
  <verify>
    <automated>./.venv/bin/python -c "from phasesight.storage import StorageManager; sm = StorageManager(db_path=':memory:'); a = sm.create_asset(name='Test Fan', target_roi={'x':10,'y':10,'width':50,'height':50}, anchor_roi={'x':100,'y':100,'width':50,'height':50}); assert sm.get_asset(a.asset_id).name == 'Test Fan'; sm.update_asset(a.asset_id, name='Updated Fan'); assert sm.get_asset(a.asset_id).name == 'Updated Fan'; assert sm.delete_asset(a.asset_id); print('Task 2 asset CRUD logic verified') status=OK"</automated>
  </verify>
  <done>
Asset Management tab renders full asset directory table, registration form with 'Copy ROIs from inspection' helper, parameter editor, and cascading asset deletion with active asset safety resets.
  </done>
</task>

<task type="auto">
  <name>Task 3: Baseline Recording Wizard Tab — Multi-Run Selection, Validation Engine, Statistical Preview, and Commit</name>
  <files>phasesight/app.py</files>
  <action>
Implement Tab 3 ('Baseline Wizard') in `phasesight/app.py` providing an interactive multi-step wizard to aggregate >= 3 healthy inspection runs into a durable `StoredBaseline` per D-06 and HIST-02.

1. Implement `render_baseline_wizard_tab(sm: StorageManager) -> None`:
   - Active Asset Header: check `st.session_state.get("selected_asset_id")`. If no asset is selected, display an informative warning: 'Please select an Active Machine Asset in the sidebar to create a baseline for it.' and return early.
   - Fetch active asset record via `sm.get_asset(asset_id)`. Display asset summary header (Asset Name, Target ROI, Anchor ROI, Expected FPS, and existing baseline count).

2. Step 1: Candidate Runs Selection:
   - Provide two input sources for candidate healthy runs:
     - Source Mode A: 'Select from Active Asset Run History': query `sm.list_inspection_runs(asset_id=active_asset.asset_id)`. Render a multi-select widget allowing operator to select runs by run_id/timestamp. Extract summary dictionaries from selected run records.
     - Source Mode B: 'Upload Healthy Inspection Summary JSON Files': provide a multi-file uploader (`accept_multiple_files=True`, type=['json']). Parse uploaded files into summary dictionaries.
   - Display a preview table of candidate runs: Run index, timestamp/filename, measured FPS, duration, X RMS displacement, Y RMS displacement, signal qualities.

3. Step 2: Live Validation Engine:
   - Evaluate candidate runs against proposal consistency criteria:
     - Quorum Check: verify `len(candidate_runs) >= 3`. Display status indicator (✅ Quorum met: N >= 3, or ⚠️ Quorum failure: at least 3 runs required).
     - Spatial ROI Consistency Check: for each run, check that its Target ROI and Anchor ROI match the active asset's configured ROIs within +/- 2 pixels using `phasesight.baseline._rois_match`. Display status indicator with pass/fail count and details for any divergent run.
     - Sampling Rate Consistency Check: for each run, check that its measured/used FPS matches the asset's expected FPS within +/- 2%. Display status indicator with pass/fail count.
     - Signal Quality Gate: verify that each candidate run has at least one axis with 'VALID' signal quality (no mutual anchor contamination across both axes).
   - If any validation check fails, display descriptive warning messages and disable the 'Save Stored Baseline' button.

4. Step 3: Statistical Preview:
   - When all validation checks pass:
     - Compute preview baseline using `phasesight.baseline.build_baseline(candidate_runs, asset_id=active_asset.asset_id)`.
     - Render statistical preview metrics: Run count (N), Degrees of Freedom (N-1), Scale Factor (1.4826), and Feature Statistics Table.
     - Table columns: Monitored Feature, Median, MAD (Median Absolute Deviation), Epsilon Floor, and Normal Variation Range [Median - 3*MAD, Median + 3*MAD].
     - Cover all monitored features: X & Y RMS displacement, dominant frequency, spectral prominence (peak-to-median dB), and second harmonic ratio.

5. Step 4: Commit Baseline:
   - Notes input: text area for baseline recording conditions (e.g. 'Commissioning baseline at 100% nominal speed, ambient temp 22C').
   - Button: '💾 Save Stored Baseline to Asset'.
   - On click: call `sm.create_baseline(asset_id=active_asset.asset_id, baseline_record=baseline_record, notes=notes)`.
   - Display success message with assigned `baseline_id`, update sidebar baseline indicator, and invoke `st.rerun()`.
  </action>
  <verify>
    <automated>./.venv/bin/python -c "from phasesight.baseline import build_baseline, _rois_match; r = {'target_roi_xywh': {'x':10,'y':10,'width':50,'height':50}, 'anchor_roi_xywh': {'x':100,'y':100,'width':50,'height':50}, 'fps_used': 60.0, 'x_axis': {'rms_displacement_px': 0.05, 'dominant_frequency_hz': 8.5, 'peak_to_median_db': 15.0, 'second_harmonic_ratio': None, 'signal_quality': 'VALID'}, 'y_axis': {'rms_displacement_px': 0.02, 'dominant_frequency_hz': 8.5, 'peak_to_median_db': 12.0, 'second_harmonic_ratio': None, 'signal_quality': 'VALID'}}; assert _rois_match(r['target_roi_xywh'], {'x':11,'y':10,'width':50,'height':50}); b = build_baseline([r, r, r], asset_id='ast_test'); assert b.run_count == 3; print('Task 3 wizard validation logic verified') status=OK"</automated>
  </verify>
  <done>
Baseline Wizard enforces quorum (N >= 3), spatial ROI consistency (+/- 2 px), and sampling rate consistency (+/- 2%), renders robust Median + MAD preview table, and commits StoredBaseline to SQLite linked to the active asset.
  </done>
</task>

<task type="auto">
  <name>Task 4: Inspection History Tab — Status Badges, On-Demand NPZ Spectra Exploration, and Operator Review Event Logging</name>
  <files>phasesight/app.py, phasesight/ui_helpers.py</files>
  <action>
Implement Tab 4 ('Inspection History') in `phasesight/app.py` and supporting plot helpers in `phasesight/ui_helpers.py` per D-07, HIST-03, and HIST-04.

1. In `phasesight/ui_helpers.py`:
   - Implement `plot_run_arrays(arrays: RunArrays, title: str | None = None) -> matplotlib.figure.Figure`:
     - Create a clean 2-panel Matplotlib figure (constrained layout, dpi=160):
       - Panel 1: Relative displacement time series: plot `timestamps_s` vs `relative_dx_px` (solid blue) and `relative_dy_px` (solid orange/alpha). Label axes 'Time (s)' and 'Displacement (pixels)'. Add subtle grid.
       - Panel 2: Welch Power Spectral Density: plot `x_frequencies_hz` vs `x_psd_px2_per_hz` (semilog, blue) and `y_frequencies_hz` vs `y_psd_px2_per_hz` (semilog, orange). If dominant peaks exist, add vertical dashed reference lines. Label axes 'Frequency (Hz)' and 'PSD (px²/Hz)'. Add legend and grid.
     - Return the Figure object for Streamlit display.

2. In `phasesight/app.py`:
   - Implement `render_history_tab(sm: StorageManager) -> None`:
     - Active Asset Confirmation: if no active asset is selected in the sidebar, prompt operator to select an asset or choose from available assets.
     - Header: display active asset name, ID, and total recorded inspection runs.
     - Filter Bar:
       - Status Filter: selectbox ['All', 'Normal', 'Review', 'Low confidence', 'Unassessed'].
       - Limit Filter: selectbox [10, 25, 50, 100, 'All'].
     - History Table Rendering:
       - Query runs via `sm.list_inspection_runs(asset_id=active_asset.asset_id, status=status_filter, limit=limit)`.
       - Render dataframe / table showing: Status Badge (🟢 Normal, 🔴 Review, 🟡 Low confidence, ⚪ Unassessed), Timestamp (UTC), Run ID, Video Name, Measured FPS, Duration (s), X Dominant Freq (Hz), X RMS (px), Baseline ID, and Actions.

3. Deep-Dive Run Inspector:
   - Select a specific run from the history table using a selectbox or radio button.
   - Run Details Summary: display full run metadata, target/anchor ROI coordinates recorded during inspection, and signal quality metrics.
   - On-Demand NPZ Array Loading & Visualization:
     - Check if `run.npz_rel_path` is present.
     - Load `RunArrays` on-demand using `sm.load_run_arrays(run.npz_rel_path)`. Do not load arrays for all runs simultaneously (mitigates memory bloat Pitfall 5).
     - Render the 2-panel engineering plot using `plot_run_arrays(arrays)` via `st.pyplot()`.
     - Provide download button for the compressed NPZ file.

4. Operator Review Event Logging Form:
   - Form container '📝 Log Operator Review Event':
     - Disposition Status: radio button ['Normal', 'Review', 'Low confidence'].
     - Operator ID: text input (default 'operator').
     - Operator Note: text area (e.g. 'Elevated 8.5 Hz vibration observed; mechanical looseness suspected. Work order #402 opened.').
     - Button: 'Submit Review Event'.
     - On submit: call `sm.create_review_event(run_id=selected_run.run_id, status=disposition, operator_note=note, operator_id=op_id)`.
     - Confirm that `create_review_event` atomically updates `inspection_runs.status` in SQLite.
     - Display success notification and call `st.rerun()` to immediately reflect the new status in the history table.

5. Historical Review Event Timeline / Audit Trail:
   - Query all review events for the selected run via `sm.list_review_events_for_run(selected_run.run_id)`.
   - Render an auditable chronological timeline of past reviews: Timestamp, Operator ID, Status badge, and Operator Notes.
  </action>
  <verify>
    <automated>./.venv/bin/python -c "from phasesight.storage import StorageManager, RunArrays; import numpy as np; sm = StorageManager(db_path=':memory:'); a = sm.create_asset(name='Pump'); arr = RunArrays(timestamps_s=np.array([0.0, 0.1]), relative_dx_px=np.array([0.1, 0.2]), relative_dy_px=np.array([0.0, 0.0])); run = sm.create_inspection_run(asset_id=a.asset_id, video_path='test.mp4', measured_fps=60.0, duration_s=1.0, frames_analysed=60, summary={}, arrays=arr); assert run.status == 'Unassessed'; ev = sm.create_review_event(run.run_id, status='Review', operator_note='Check motor'); updated_run = sm.get_inspection_run(run.run_id); assert updated_run.status == 'Review'; print('Task 4 history & review sync verified') status=OK"</automated>
  </verify>
  <done>
Inspection History tab displays filterable run log with status badges, decompressing NPZ arrays on-demand for 2-panel plotting, and provides an operator review event form that atomically synchronizes parent run status with a full audit timeline.
  </done>
</task>

<task type="auto">
  <name>Task 5: Comprehensive Headless Automated UI Test Suite in tests/test_ui.py</name>
  <files>tests/test_ui.py</files>
  <action>
Expand `tests/test_ui.py` to provide a comprehensive automated headless test suite using `streamlit.testing.v1.AppTest` and in-memory `StorageManager(db_path=":memory:")` per D-08 and HIST-06.

1. Implement test fixtures and helpers in `tests/test_ui.py`:
   - Fixture creating an in-memory `StorageManager` populated with sample assets (e.g. 'Cooling Fan A' with configured Target & Anchor ROIs and 60.0 expected FPS), a 3-run `StoredBaseline`, and sample inspection runs with `RunArrays`.

2. Test Case 1: `test_ui_asset_selection_updates_rois_and_fps`:
   - Launch headless `AppTest.from_file(APP_PATH)`.
   - Inject in-memory `StorageManager` with 'Cooling Fan A' (`target_roi={'x': 250, 'y': 140, 'width': 120, 'height': 120}`, `expected_fps=59.94`).
   - Run initial script.
   - Select 'Cooling Fan A' in sidebar selectbox.
   - Verify `at.session_state["selected_asset_id"] == "ast_fan_a"`.
   - Verify session state ROI keys update: `tx_input == 250`, `ty_input == 140`, `tw_input == 120`, `th_input == 120`, and `fps_override_val == approx(59.94)`.
   - Verify sidebar info card contains asset details.
   - Verify no Streamlit exceptions occur (`assert not at.exception`).

3. Test Case 2: `test_ui_asset_management_crud`:
   - Launch `AppTest` with in-memory storage.
   - Navigate to Asset Management tab.
   - Create a new asset via `sm.create_asset()`.
   - Verify the asset appears in `sm.list_assets()`.
   - Delete the asset and verify removal from storage.

4. Test Case 3: `test_ui_baseline_wizard_quorum_and_validation`:
   - Create asset in storage.
   - Test Quorum Validation: provide 2 candidate runs; verify validation fails with quorum warning message.
   - Test Spatial Consistency: provide 3 runs where one run has Target ROI shifted by 10 px; verify validation fails with spatial divergence message.
   - Test Sampling Rate Consistency: provide 3 runs where one run has FPS differing by 10%; verify validation fails with sampling rate warning.
   - Test Successful Creation: provide 3 valid matching runs; call baseline creation; verify `StoredBaseline` is created and stored in SQLite.

5. Test Case 4: `test_ui_inspection_history_table_and_npz_traces`:
   - In-memory storage with active asset having 2 inspection runs (one with NPZ `RunArrays`).
   - Navigate to Inspection History tab.
   - Verify runs table displays runs with correct status badges.
   - Select run with NPZ arrays; verify `load_run_arrays()` succeeds and plot generates without errors.

6. Test Case 5: `test_ui_review_event_logging_and_status_sync`:
   - Create an inspection run with status 'Unassessed'.
   - Submit review event with disposition 'Review' and operator note 'Bearing tone observed'.
   - Verify review event is persisted in `review_events` table.
   - Verify parent inspection run status is atomically updated to 'Review'.
   - Verify review audit timeline displays the logged note.

7. Test Case 6: `test_ui_auto_assessment_against_stored_baseline`:
   - Set up active asset with a stored baseline.
   - Simulate completed analysis in `at.session_state["latest_summary"]`.
   - Verify 1-click auto-assessment card renders.
   - Execute auto-assessment; verify evaluation produces valid status ('Normal' or 'Review') and feature deviation table.

8. Run full test suite: execute `./.venv/bin/pytest` ensuring all 55 existing tests plus all new UI tests pass with zero failures.
  </action>
  <verify>
    <automated>./.venv/bin/pytest tests/test_ui.py -v && ./.venv/bin/pytest</automated>
  </verify>
  <done>
All headless AppTest UI test cases pass cleanly in tests/test_ui.py, covering asset selection, baseline wizard validation, history display, review event logging, and auto-assessment with full regression suite passing across the codebase.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Operator UI Inputs → SQLite Engine | Untrusted text strings, coordinates, and parameters entered in Streamlit forms passed to StorageManager. |
| Video Upload / NPZ Serialization → Filesystem | User-uploaded video files and compressed NumPy NPZ array files written to disk. |
| Streamlit Session State → Multi-Threaded Workers | Session state variables and widget keys shared across reactive script reruns and threads. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-05-01 | Tampering / SQL Injection | `phasesight/app.py` → `phasesight/storage.py` | high | mitigate | Mandate that all database queries and updates flow strictly through `StorageManager` methods using parameterized SQL queries (`?` placeholders). Forbid raw SQL interpolation in UI code. |
| T-05-02 | Tampering / Path Traversal | `phasesight/app.py:render_inspection_tab` | high | mitigate | Sanitize uploaded video filenames using `Path(uploaded_file.name).name` and write strictly to `output/uploads/`. Validate all relative NPZ paths through `StorageManager.resolve_path()` to prevent directory traversal outside `storage_root`. |
| T-05-03 | Denial of Service / Memory Bloat | `phasesight/app.py:render_history_tab` | medium | mitigate | Decompress and load `RunArrays` from disk on-demand only for the single currently inspected run; avoid bulk loading or decompressing NPZ files during history table rendering. |
| T-05-04 | Integrity / State Collision | `phasesight/app.py:init_session_state` | medium | mitigate | Use the single global sidebar asset selector as source of truth. Initialize session state keys once with `.setdefault()`, and omit explicit `value=` arguments on number input widgets to prevent Streamlit widget state collisions. |
| T-05-SC | Tampering / Supply Chain | `pyproject.toml` | high | mitigate | Strictly use verified, pre-installed dependencies (`streamlit==1.67.0`, `sqlite3`, `numpy==2.5.5`, `scipy==1.15.2`, `opencv-python==4.11.0`, `matplotlib==3.10.1`, `pytest==8.3.5`). No new third-party dependencies are introduced. |
</threat_model>

<verification>
Automated verification commands:
1. UI Helpers & App Import: `./.venv/bin/python -c "from phasesight.app import get_storage_manager; from phasesight.ui_helpers import run_arrays_from_csv, plot_run_arrays, status_badge; print('Imports verified')"`
2. App Test Suite: `./.venv/bin/pytest tests/test_ui.py -v`
3. Storage & Baseline Unit Tests: `./.venv/bin/pytest tests/test_storage.py tests/test_baseline.py -v`
4. Full Test Suite (Zero Regressions): `./.venv/bin/pytest -v` (60+ tests passing)
</verification>

<success_criteria>
1. `phasesight/app.py` initializes and caches `StorageManager` in `st.session_state["storage_manager"]`, enabling seamless in-memory `:memory:` dependency injection during tests.
2. Global sidebar provides an active machine asset selector and details card displaying ROIs, expected FPS, baseline status, and storage diagnostics.
3. Selecting an asset in the sidebar auto-populates Target ROI, Anchor ROI, and expected FPS into Tab 1 widgets without Streamlit state warnings.
4. Video Inspection tab offers a 1-click Auto-Assessment card when an asset baseline exists, and provides a 'Save Run to Asset History' button persisting the run to SQLite and compressed NPZ.
5. Asset Management tab supports the complete asset lifecycle: directory catalog, registration form with 'Copy ROIs from inspection' shortcut, parameter editor, and cascading deletion.
6. Baseline Wizard tab enforces quorum ($N \ge 3$), spatial ROI consistency ($\pm 2$ px), and sampling rate consistency ($\pm 2\%$), rendering a Median + MAD preview and saving `StoredBaseline`.
7. Inspection History tab renders a filterable run table with color badges, on-demand NPZ array exploration with 2-panel engineering plots, and an operator review logging form that atomically updates run status with an auditable timeline.
8. Comprehensive headless test suite in `tests/test_ui.py` passes 100% of cases using `streamlit.testing.v1.AppTest`.
9. All 55+ existing tests across the codebase continue to pass with zero regressions.
10. Non-negotiable technical boundaries (pixel domain only, 2D translation only, screening vs diagnosis, separation of measurement and magnification) are strictly upheld throughout.
</success_criteria>

<output>
Create `.planning/phases/05-workbench-history/05-01-SUMMARY.md` when execution is complete.
</output>
