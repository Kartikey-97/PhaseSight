# Phase 5 Plan 01 Summary: Workbench History & Asset Integration

## Execution Overview
Phase 5 transitioned the Streamlit operator workbench (`phasesight/app.py`) from single-video ad-hoc analysis into a comprehensive, asset-centric vibration screening interface. Monitored physical machines can now be registered with configured Target and Anchor ROIs, expected frame rates, and nominal speeds. Multiple healthy runs can be recorded, validated, and aggregated into durable statistical baselines using the Baseline Recording Wizard. Inspection runs are persisted to SQLite (`phasesight.db`) alongside compressed numerical arrays (`numpy.savez_compressed` `.npz`). Operators can screen new videos with 1-click against stored baselines, view historical run trends with status badges, decompress NPZ arrays for deep-dive spectral analysis, and record auditable review events.

## Core Deliverables

### 1. Global Sidebar Asset Anchor & State Synchronization (`phasesight/app.py`)
- **Active Machine Asset Selector:** Selectbox with registered assets or `-- None (Ad-hoc Analysis) --`.
- **ROI & FPS Auto-Population:** Selecting an active asset automatically populates Target and Anchor ROI coordinates and expected FPS into Tab 1 input widgets without session state collisions.
- **Active Asset Details Card:** Displays configured Target ROI, Anchor ROI, expected FPS, and current baseline status (`✅ bsl_xxx (N=3)` or `⚠️ None`).
- **Database Diagnostics:** Displays database path, SQLite version, and counts of registered assets, baselines, and runs from `sm.get_db_info()`.

### 2. Video Inspection Tab Enhancements
- Configured widgets bind directly to session state keys (`tx_input`, `ty_input`, etc.) without passing explicit `value=` arguments, preventing Streamlit widget state warnings.
- **1-Click Auto-Assessment Card:** When an active asset has an established baseline, offers instant screening using `evaluate_run_against_baseline()`, displaying verdict badges (🟢 Normal, 🔴 Review, 🟡 Low confidence) and feature deviation tables.
- **Save Run to Asset History:** Converts analysis CSV output into `RunArrays`, persists `InspectionRunRecord` to SQLite, and writes compressed NPZ arrays to `data/storage/npz/runs/`.

### 3. Asset Management Tab (Tab 2)
- **Asset Catalog Table:** Displays all registered assets with coordinates, expected FPS, nominal RPM, baseline count, and run count.
- **Registration Form:** Form with "📋 Copy ROIs from Current Inspection" shortcut, input validation (min size 32x32, positive FPS), and automatic active selection upon creation.
- **Parameter Editor & Danger Zone:** In-place asset parameter updates and cascading deletion with optional disk file cleanup.

### 4. Baseline Recording Wizard Tab (Tab 3)
- Multi-step guided workflow for the active asset:
  - **Step 1:** Select candidate healthy runs (from asset run history or uploaded summary JSONs).
  - **Step 2:** Live validation engine enforcing Quorum ($N \ge 3$), spatial ROI consistency ($\pm 2$ px via `_rois_match`), and sampling rate consistency ($\pm 2\%$).
  - **Step 3:** Robust Median + MAD preview table showing median, MAD, and 3-MAD normal bounds for all monitored features.
  - **Step 4:** Notes input and commit button persisting `StoredBaseline` to SQLite.

### 5. Inspection History Tab (Tab 4)
- Filterable run log for the active asset with status badges (🟢 Normal, 🔴 Review, 🟡 Low confidence, ⚪ Unassessed).
- **Deep-Dive Run Inspector:** On-demand NPZ array loading and 2-panel plotting (`plot_run_arrays` displaying relative displacement time series and Welch PSD spectra).
- **Operator Review Event Logging Form:** Form allowing operators to record disposition status, operator ID, and notes, atomically synchronizing `inspection_runs.status`.
- **Review Audit Trail:** Chronological display of past review events for the inspected run.

### 6. Supporting Plot & Data Helpers (`phasesight/ui_helpers.py`)
- `status_badge(status)`: Standardized colored status badges.
- `sync_active_asset_rois(asset)`: Synchronizes ROI coordinates and FPS into session state.
- `run_arrays_from_csv(csv_path)`: Constructs `RunArrays` from motion CSV with Welch PSD calculations.
- `plot_run_arrays(arrays)`: Generates 2-panel Matplotlib figure for time series and PSD spectra.

### 7. Automated Headless Test Suite (`tests/test_ui.py`)
- 12 comprehensive unit tests using `streamlit.testing.v1.AppTest` and in-memory `StorageManager(db_path=":memory:")`:
  - `test_ui_helpers_get_metadata_and_frame`
  - `test_ui_helpers_reject_invalid_video`
  - `test_status_badge_formatting`
  - `test_run_arrays_from_csv_and_plot`
  - `test_streamlit_app_loads_and_renders_cleanly` (verifies 6 tabs render)
  - `test_streamlit_app_sample_clip_inspection`
  - `test_ui_asset_selection_updates_rois_and_fps`
  - `test_ui_asset_management_crud`
  - `test_ui_baseline_wizard_quorum_and_validation`
  - `test_ui_inspection_history_table_and_npz_traces`
  - `test_ui_review_event_logging_and_status_sync`
  - `test_ui_auto_assessment_against_stored_baseline`

## Verification Results
- **Full Test Suite:** 63 passed out of 63 tests in 15.43s (`pytest -v`). Zero regressions.
- **Synthetic Validation Suite:** 4 of 4 scenarios pass (`phasesight validate`).
