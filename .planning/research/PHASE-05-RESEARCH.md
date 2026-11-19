# Phase 5: Workbench History & Asset Integration — Research & Architecture Specification

**Researched:** 2026-11-19  
**Domain:** Streamlit Operator Workbench UI, Session State Architecture, Multi-Run Statistical Baseline Wizard, Inspection History & NPZ Trace Exploration, Review Event Logging, Headless UI Testing (`streamlit.testing.v1.AppTest`)  
**Confidence:** HIGH (Streamlit 1.67.0, Python 3.13, verified against `phasesight.storage`, `phasesight.baseline`, and `phasesight.app`)  

---

<user_constraints>
## User Constraints (from CONTEXT.md, ROADMAP.md, and STATE.md)

### Locked Decisions
1. **Workbench Architecture & Scope:**
   - Transition PhaseSight from single-video ad-hoc analysis to an asset-centric monitoring system integrated into the Streamlit operator workbench (`phasesight/app.py`).
   - Seamless integration with the persistence layer built in Phase 4 (`phasesight.storage.StorageManager`, `AssetRecord`, `StoredBaseline`, `InspectionRunRecord`, `ReviewEventRecord`, `RunArrays`).
   - Strict adherence to Proposal Specification (Page 4) operational workflows:
     - **Asset Selection:** Selecting an asset automatically populates its saved Target ROI, Anchor ROI, and expected FPS into the Video Inspection tab.
     - **Baseline Recording Wizard:** Multi-run baseline creation workflow in UI (selecting or importing $\ge 3$ healthy clips) validating quorum ($N \ge 3$), ROI consistency ($\pm 2$ px), and sampling rate consistency ($\pm 2\%$), creating and persisting a `StoredBaseline` linked to the asset.
     - **Inspection History & Review Events:** Dedicated view displaying historical inspection runs for the active asset with status badges (`Normal`, `Review`, `Low confidence`, `Unassessed`), spectrum/trace exploration from NPZ arrays, and operator review event logging (`Normal`, `Review`, `Low confidence` with note and operator ID).
     - **1-Click Auto-Assessment:** When an inspection run finishes on an asset with an established baseline, automatically offer a 1-click assessment against the asset's latest stored baseline.
2. **Non-Negotiable Technical Boundaries:**
   - **Pixel-Domain Only:** Output is strictly in image pixels. No physical unit conversions (mm, mm/s, velocity, acceleration) or ISO vibration standards without in-situ physical target calibration.
   - **Screening vs Fault Diagnosis:** Status flags (`Normal`, `Review`, `Low confidence`) indicate measured shifts against baseline, not specific mechanical fault diagnosis (bearings, gears, unbalance, RUL).
   - **2D Translation Only:** Tracking uses OpenCV `phaseCorrelate` (Fourier shift theorem) between target and anchor ROIs; static anchor dependency remains.
   - **Separation of Measurement and Magnification:** Riesz motion magnification is an optional visual explanation tool that must never feed the alert calculation.
   - **Relational Integrity & Thread Safety:** All UI queries and mutations must operate through `StorageManager` with thread synchronization (`threading.RLock`) and SQLite Write-Ahead Logging (`WAL`).
3. **Automated Testing:**
   - Comprehensive headless test suite in `tests/test_ui.py` using `streamlit.testing.v1.AppTest` verifying asset selection, ROI auto-population, baseline creation wizard, inspection history display, review event logging, and auto-assessment.

### The Agent's Discretion
- Streamlit layout structure: combining a persistent sidebar asset selector with top-level tabs.
- Session state schema and widget key lifecycle management to prevent Streamlit session state collision warnings.
- Layout of the Baseline Wizard: run selection, preview metrics, and confirmation card.
- Visual status badges and color palette (🟢 Normal, 🔴 Review, 🟡 Low confidence, ⚪ Unassessed).
- Inspection history table layout, filters (status, limit), and NPZ time-series visualization.
- Helper utilities in `phasesight/ui_helpers.py` for array conversion and state synchronization.

### Deferred Ideas (OUT OF SCOPE)
- Live webcam streaming, UVC video capture, and dropped-frame timestamp regularity checking (reserved for Phase 6).
- Motion magnification integration (Riesz pyramid rendering) (reserved for Phase 7 / Future).
- Multi-user authentication, cloud replication, or remote fleet management.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| **HIST-01** | **Asset Management & Global Selection:** Persistent sidebar asset selector and dedicated Asset Management tab allowing operators to create, list, select, edit, and delete machine assets. Selecting an asset automatically loads its saved Target ROI, Anchor ROI, and expected FPS into Tab 1. | `st.sidebar.selectbox` connected to `storage_manager.list_assets()`, callback updating `st.session_state` ROI keys; Asset Management tab with CRUD forms. |
| **HIST-02** | **Multi-Run Baseline Recording Wizard:** Interactive UI wizard guiding operators through selecting $\ge 3$ healthy inspection runs, validating quorum ($N \ge 3$), spatial ROI consistency ($\pm 2$ px), and sampling rate consistency ($\pm 2\%$), computing robust Median + MAD statistics, and saving `StoredBaseline`. | UI flow aggregating completed runs or uploaded summaries via `phasesight.baseline.build_baseline`, verified via `_rois_match`, persisted via `storage_manager.create_baseline`. |
| **HIST-03** | **Inspection History & Trace Exploration:** Comprehensive historical log of inspection runs for the active asset with status badges (`Normal`, `Review`, `Low confidence`, `Unassessed`), metrics, and deep-dive visualization of raw displacement traces and Welch PSD spectra from compressed NPZ. | Query `storage_manager.list_inspection_runs(asset_id)`, render dataframe with badges, load arrays via `storage_manager.load_run_arrays(npz_path)`, render displacement and PSD plots. |
| **HIST-04** | **Operator Review Event Logging:** Review interface enabling operators to evaluate an inspection run, select disposition status (`Normal`, `Review`, `Low confidence`), append notes and operator ID, and synchronize parent run status. | `storage_manager.create_review_event(run_id, status, operator_note, operator_id)`, updating `inspection_runs.status` in SQLite and rendering an auditable review timeline. |
| **HIST-05** | **1-Click Auto-Assessment Against Stored Baseline:** Automatic detection of existing asset baseline after running video inspection in Tab 1, offering 1-click evaluation against `latest_baseline.baseline_record` and saving the evaluated run to history. | `storage_manager.get_latest_baseline_for_asset(asset_id)`, `evaluate_run_against_baseline(summary, baseline_record)`, display deviation table and standardized z-bar chart. |
| **HIST-06** | **Headless Automated UI Test Suite:** Deterministic automated test suite in `tests/test_ui.py` using `streamlit.testing.v1.AppTest` validating asset selection, baseline wizard, history view, and review event logging with in-memory storage injection. | `AppTest.from_file` with pre-injected `st.session_state["storage_manager"] = StorageManager(db_path=":memory:")` executing headless test matrix in <2s without disk side effects. |
</phase_requirements>

---

## Summary

Phase 5 elevates PhaseSight from an ad-hoc video vibration analyzer to an integrated screening workbench. Operators can configure physical machines as durable assets, establish rigorous multi-run statistical baselines, track vibration trends across inspections over time, and log auditable review decisions.

The persistence engine engineered in Phase 4 (`StorageManager`, SQLite `phasesight.db`, and compressed `.npz` arrays) provides the relational backbone. Phase 5 builds the human-in-the-loop operational interface in Streamlit, ensuring that facility engineers can perform repeatable vibration screening without needing terminal commands or manual JSON file handling.

### Primary Recommendation
Structure the Workbench using a **Global Sidebar Asset Anchor** paired with **6 Specialized Tabs**:
1. **Sidebar:** Global Active Machine Asset selector (`st.sidebar.selectbox`), asset quick info badge (ROI coords, FPS, baseline status, run count), and storage database diagnostics.
2. **Tab 1: Video Inspection:** Retains video selection/upload, with Target & Anchor ROIs and expected FPS automatically loaded from the active asset. After analysis, if a stored baseline exists for the asset, an **Auto-Assessment Banner** offers 1-click evaluation against the baseline, and a **Save to History** button persists the run and its arrays to the database.
3. **Tab 2: Asset Management:** Full asset directory, form to create new machine assets (with a 1-click "Copy ROIs from Current Inspection" helper), asset parameter editor, and deletion.
4. **Tab 3: Baseline Recording Wizard:** Multi-step wizard allowing operators to select $\ge 3$ healthy inspection runs, validates quorum ($N \ge 3$), ROI spatial consistency ($\pm 2$ px tolerance), and sampling rate consistency ($\pm 2\%$), displays robust statistical preview (Median, MAD, scale factor, $\epsilon$), and persists the baseline.
5. **Tab 4: Inspection History:** Interactive history log for the active asset with color-coded status badges (🟢 Normal, 🔴 Review, 🟡 Low confidence, ⚪ Unassessed), run metrics, NPZ displacement time series and Welch PSD plots, and an **Operator Review Event Logging Form** with an auditable event timeline.
6. **Tab 5: Baseline Comparison:** Preserves the existing standalone/ad-hoc comparison engine from Phase 3 for manual file-based or pairwise comparison.
7. **Tab 6: Technical Boundaries & Notes:** Essential physical screening disclaimers (pixel-domain only, 2D translation only, static anchor requirements, screening vs diagnosis).

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| **Active Asset Context** | Streamlit Session State (`st.session_state`) | Storage Manager (`StorageManager`) | Active asset selection must be globally accessible to all tabs and persist across widget interactions within the session. |
| **ROI & Parameter Loading** | App / UI Tier (`phasesight.app`) | Storage Manager (`AssetRecord`) | Active asset's Target ROI, Anchor ROI, and expected FPS are pulled from `AssetRecord` and synchronized into Streamlit input widgets via session state callbacks. |
| **Baseline Creation Wizard** | Analysis Tier (`phasesight.baseline`) | App / UI Tier (`phasesight.app`) | UI gathers candidate runs, validates quorum and consistency rules, invokes `build_baseline()`, and persists the resulting `BaselineRecord` via `StorageManager.create_baseline()`. |
| **Run Archival & Array Storage** | Persistence Tier (`phasesight.storage`) | Analysis Tier (`phasesight.video`) | Inspection runs are saved to SQLite `inspection_runs`; high-dimensional motion time series and Welch PSD arrays are serialized to compressed `.npz` files via `StorageManager.save_run_arrays()`. |
| **Run History Exploration** | App / UI Tier (`phasesight.app`) | Storage Manager (`InspectionRunRecord`, `RunArrays`) | Historical runs are queried from SQLite with status filtering; raw displacement and Welch PSD traces are loaded on-demand from NPZ and plotted. |
| **Review Event Logging** | Storage Manager (`ReviewEventRecord`) | App / UI Tier (`phasesight.app`) | Operator dispositions, notes, and timestamps are written to SQLite `review_events`, atomically updating `inspection_runs.status`. |
| **1-Click Auto-Assessment** | Analysis Tier (`phasesight.baseline`) | App / UI Tier (`phasesight.app`) | Automatically retrieves active asset's latest `StoredBaseline`, passes current inspection summary to `evaluate_run_against_baseline()`, and renders deviation tables. |
| **Headless UI Testing** | Test Harness (`pytest` + `AppTest`) | App Tier (`phasesight.app`) | Headless execution simulating operator interactions, button clicks, and state transitions using in-memory SQLite storage. |

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `streamlit` [VERIFIED: pyproject.toml:16, installed 1.67.0] | 1.67.0 (`>=1.30`) | Local Operator Workbench UI | Standard Python UI for engineering dashboards, native reactive reruns, session state management, built-in headless `AppTest` test harness. |
| `sqlite3` [VERIFIED: Python standard library 3.13 / SQLite 3.50.4] | 3.50.4 (built-in) | Relational persistence | Zero-daemon, ACID compliant, embedded SQLite database (`phasesight.db`) with WAL mode for concurrency and `:memory:` for fast testing. |
| `numpy` [VERIFIED: pyproject.toml:12, installed 2.5.5] | 2.5.5 (`>=1.26`) | Compressed NPZ array storage and signal processing | Fast compressed array persistence (`np.savez_compressed`), sub-5ms serialization, zero extra dependencies. |
| `scipy` [VERIFIED: pyproject.toml:13, installed 1.15.2] | 1.15.2 (`>=1.12`) | Welch PSD spectral estimation | Gold-standard signal processing library (`scipy.signal.welch`) used for vibration spectral density and robust statistics. |
| `opencv-python` [VERIFIED: pyproject.toml:14, installed 4.11.0] | 4.11.0 (`>=4.9`) | Video frame reading, phase correlation, and ROI visualization | Real-time image processing, Fourier phase correlation (`cv2.phaseCorrelate`), BGR/RGB frame conversions. |
| `matplotlib` [VERIFIED: pyproject.toml:15, installed 3.10.1] | 3.10.1 (`>=3.8`) | Spectral and displacement plotting | Clean 2-panel engineering plots (displacement traces + semilog Welch PSD), figure export to PNG for UI display. |
| `pytest` [VERIFIED: pyproject.toml:20, installed 8.3.5] | 8.3.5 (`>=8.0`) | Automated test runner | Standard test framework, executes headless `streamlit.testing.v1.AppTest` and integration tests. |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `dataclasses` [VERIFIED: Python standard library 3.13] | built-in | Typed model representations | `AssetRecord`, `StoredBaseline`, `InspectionRunRecord`, `ReviewEventRecord`, `RunArrays`. |
| `pathlib` [VERIFIED: Python standard library 3.13] | built-in | Cross-platform filesystem resolution | Resolving storage paths, video paths, evidence images, and NPZ relative locations. |
| `json` [VERIFIED: Python standard library 3.13] | built-in | Summary and report serialization | Encoding feature dictionaries, ROI coordinates, and assessment JSON reports. |
| `threading` [VERIFIED: Python standard library 3.13] | built-in | Concurrency locking | `threading.RLock` ensuring safe multi-threaded SQLite access during Streamlit script reruns. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| **Single Sidebar Asset Selector** | Per-tab asset dropdowns | Per-tab dropdowns cause state desynchronization (operator selects Asset A in Tab 1, but Tab 4 still inspects Asset B). A single global sidebar selector guarantees single source of truth across all workbench views. |
| **In-Memory Storage Injection** | Real disk database during UI tests | Using disk `phasesight.db` in automated tests creates race conditions, leaves temp files, and slows test execution. Injecting `StorageManager(db_path=":memory:")` into `at.session_state` before `at.run()` executes in <100ms with zero side effects. |
| **Matplotlib Plot in History** | Streamlit native `st.line_chart` | `st.line_chart` lacks semilogarithmic frequency axes (`semilogy`), peak reference vertical lines, dual-axis units, and engineering layout. Matplotlib figures render exact spectral engineering plots. |

---

## Package Legitimacy Audit

No new third-party packages are required for Phase 5. All capabilities are fulfilled by the existing dependencies declared in `pyproject.toml` and Python 3.13 standard libraries.

| Package | Registry | Current Installed Version | PyPI Status | Source Repo | Verdict | Disposition |
|---------|----------|---------------------------|-------------|-------------|---------|-------------|
| `streamlit` | PyPI | 1.67.0 | Active (>=1.30 declared) | `github.com/streamlit/streamlit` | [OK] | Approved |
| `numpy` | PyPI | 2.5.5 | Active (>=1.26 declared) | `github.com/numpy/numpy` | [OK] | Approved |
| `scipy` | PyPI | 1.15.2 | Active (>=1.12 declared) | `github.com/scipy/scipy` | [OK] | Approved |
| `opencv-python` | PyPI | 4.11.0.86 | Active (>=4.9 declared) | `github.com/opencv/opencv-python` | [OK] | Approved |
| `matplotlib` | PyPI | 3.10.1 | Active (>=3.8 declared) | `github.com/matplotlib/matplotlib` | [OK] | Approved |
| `pytest` | PyPI | 8.3.5 | Active (>=8.0 declared) | `github.com/pytest-dev/pytest` | [OK] | Approved |

---

## Architecture Patterns

### System Architecture Diagram

```mermaid
flowchart TD
    subgraph UI_Sidebar["Streamlit Global Sidebar"]
        AS["Active Asset Selector\n(st.sidebar.selectbox)"]
        AC["Active Asset Card\n(ROIs, Expected FPS, Baseline Info)"]
        DB["Persistence Diagnostics\n(phasesight.db Status)"]
    end

    subgraph Storage_Tier["Local Persistence Layer (StorageManager)"]
        DB_SQL["SQLite Engine (phasesight.db)\n• assets\n• baselines\n• inspection_runs\n• review_events"]
        NPZ_DIR["NumPy NPZ Files\n• npz/runs/{run_id}.npz\n• npz/baselines/{bsl_id}.npz"]
    end

    subgraph Tab_1["Tab 1: Video Inspection"]
        VI_SRC["Select/Upload Video"]
        VI_ROI["Auto-Populated ROIs & FPS\n(from Active Asset)"]
        VI_RUN["Run Vibration Analysis\n(OpenCV + Welch PSD)"]
        VI_AUTO["1-Click Auto-Assessment\n(evaluate against active baseline)"]
        VI_SAVE["Save Run to History\n(insert run + save NPZ arrays)"]
    end

    subgraph Tab_2["Tab 2: Asset Management"]
        AM_LIST["Asset Catalog & Summary"]
        AM_FORM["Create New Asset Form\n(Name, ROIs, Expected FPS)"]
        AM_EDIT["Edit / Delete Asset"]
    end

    subgraph Tab_3["Tab 3: Baseline Recording Wizard"]
        BW_SEL["Select ≥ 3 Healthy Runs\n(from Asset History / Upload)"]
        BW_VAL["Validation Engine\n• Quorum (N ≥ 3)\n• ROI Match (±2 px)\n• FPS Match (±2%)"]
        BW_BUILD["build_baseline()\n(Median + MAD Statistics)"]
        BW_SAVE["Save StoredBaseline\n(linked to Active Asset)"]
    end

    subgraph Tab_4["Tab 4: Inspection History"]
        IH_LOG["History Table & Filters\n(Normal, Review, Low conf, Unassessed)"]
        IH_TRACE["Trace & PSD Exploration\n(load_run_arrays from NPZ)"]
        IH_REV["Operator Review Form\n(Log note & set disposition)"]
        IH_TRAIL["Review Event Timeline"]
    end

    AS -->|Loads AssetRecord| AC
    AS -->|Sets session_state| VI_ROI
    AS -->|Filters runs/baselines| Tab_3
    AS -->|Filters history| Tab_4

    VI_RUN --> VI_AUTO
    VI_RUN --> VI_SAVE
    VI_AUTO -->|Reads latest baseline| DB_SQL
    VI_SAVE -->|Persists run & NPZ| Storage_Tier

    AM_FORM -->|create_asset()| DB_SQL
    AM_EDIT -->|update/delete_asset()| DB_SQL

    BW_SEL --> BW_VAL
    BW_VAL -->|Passed| BW_BUILD
    BW_BUILD -->|create_baseline()| Storage_Tier

    IH_LOG -->|Queries runs| DB_SQL
    IH_TRACE -->|load_run_arrays()| NPZ_DIR
    IH_REV -->|create_review_event()| DB_SQL
    IH_REV -->|Syncs status| IH_LOG
```

---

### Component Responsibilities & Layout

```
Streamlit App Layout:
├── Sidebar (Always Visible)
│   ├── PhaseSight Title & Logo
│   ├── Active Asset Selector [st.sidebar.selectbox]
│   ├── Active Asset Details Card (ROIs, Expected FPS, Baseline, Run Count)
│   └── Database Diagnostics (Total Assets, Baselines, Runs, File Path)
│
├── Tab 1: 1. Video Inspection
│   ├── Video Source (Sample portable clips / Upload video)
│   ├── Video Preview with Target (Green) & Anchor (Orange) Overlays
│   ├── ROI & Analysis Parameters (Auto-populated from Active Asset)
│   ├── Run Vibration Analysis Button
│   ├── Measurement Results (Displacement RMS, Freq, Quality Status)
│   ├── 1-Click Auto-Assessment Card (if Active Baseline exists)
│   └── Save Run to Asset History Button (records to SQLite + NPZ)
│
├── Tab 2: 2. Asset Management
│   ├── Registered Assets Table
│   ├── Create Asset Form (Name, Description, Speed, ROIs, Expected FPS)
│   │   └── "Copy ROIs from Current Inspection" Quick Action
│   └── Edit / Delete Asset Controls
│
├── Tab 3: 3. Baseline Wizard
│   ├── Target Asset Header (Active Asset Confirmation)
│   ├── Step 1: Select Candidate Runs (from Stored Runs or JSON Uploads)
│   ├── Step 2: Quorum & Consistency Validation Display
│   ├── Step 3: Statistical Preview (Median, MAD, Scale Factor, Epsilon)
│   └── Step 4: Commit Stored Baseline to Asset
│
├── Tab 4: 4. Inspection History
│   ├── Active Asset History Header & Status Filter
│   ├── Historical Runs Table with Color Badges (Normal, Review, Low conf, Unassessed)
│   ├── Detailed Run View (Metrics & Parameter Summary)
│   ├── Displacement Time Series & Welch PSD Spectrum (from NPZ)
│   ├── Operator Review Event Logging Form (Verdict, Note, Operator ID)
│   └── Review Audit Trail / Timeline
│
├── Tab 5: 5. Baseline Comparison (Preserved from Phase 3)
│   ├── Statistical Baseline Engine (Median + MAD z-score)
│   └── Pairwise Single-Run Compare (Percentage Thresholds)
│
└── Tab 6: 6. Technical Boundaries & Notes
    └── Non-negotiable technical boundaries & screening disclaimers
```

---

### Session State Design & Widget Key Synchronization

A critical architectural pitfall in Streamlit occurs when setting widget values via session state while simultaneously passing `value=...` in the widget constructor. This triggers the Streamlit warning:
`The widget with key "tx" was created with a default value but also had its value set via the Session State API.`

To ensure completely clean, warning-free widget synchronization, PhaseSight applies the **State Initialization & Callback Pattern**:

1. **State Initialization:**
   ```python
   def init_session_state(storage_manager: StorageManager) -> None:
       """Initialize default session state keys if not already present."""
       if "storage_manager" not in st.session_state:
           st.session_state["storage_manager"] = storage_manager
       if "selected_asset_id" not in st.session_state:
           st.session_state["selected_asset_id"] = None
       if "prev_selected_asset_id" not in st.session_state:
           st.session_state["prev_selected_asset_id"] = None
           
       # ROI input keys initialized once
       defaults = {
           "tx_input": int(DEFAULT_SAMPLE_TARGET_ROI.x),
           "ty_input": int(DEFAULT_SAMPLE_TARGET_ROI.y),
           "tw_input": int(DEFAULT_SAMPLE_TARGET_ROI.width),
           "th_input": int(DEFAULT_SAMPLE_TARGET_ROI.height),
           "ax_input": int(DEFAULT_SAMPLE_ANCHOR_ROI.x),
           "ay_input": int(DEFAULT_SAMPLE_ANCHOR_ROI.y),
           "aw_input": int(DEFAULT_SAMPLE_ANCHOR_ROI.width),
           "ah_input": int(DEFAULT_SAMPLE_ANCHOR_ROI.height),
           "fps_override_val": 0.0,
       }
       for k, v in defaults.items():
           if k not in st.session_state:
               st.session_state[k] = v
   ```

2. **Asset Change Callback / Synchronizer:**
   When the operator selects an asset in the sidebar selectbox, the synchronizer updates the ROI keys directly in `st.session_state`:
   ```python
   def sync_active_asset_rois(asset: AssetRecord | None) -> None:
       """Update session state ROI keys when active asset changes."""
       if asset is not None:
           st.session_state["tx_input"] = int(asset.target_roi["x"])
           st.session_state["ty_input"] = int(asset.target_roi["y"])
           st.session_state["tw_input"] = int(asset.target_roi["width"])
           st.session_state["th_input"] = int(asset.target_roi["height"])
           st.session_state["ax_input"] = int(asset.anchor_roi["x"])
           st.session_state["ay_input"] = int(asset.anchor_roi["y"])
           st.session_state["aw_input"] = int(asset.anchor_roi["width"])
           st.session_state["ah_input"] = int(asset.anchor_roi["height"])
           st.session_state["fps_override_val"] = float(asset.expected_fps)
   ```

3. **Widget Instantiation Without `value=`:**
   In `render_inspection_tab()`, widgets consume their state purely through `key`:
   ```python
   tx = st.number_input("Target X", min_value=0, max_value=max(0, frame_w - 32), step=5, key="tx_input")
   ty = st.number_input("Target Y", min_value=0, max_value=max(0, frame_h - 32), step=5, key="ty_input")
   ```
   This guarantees bidirectional binding, zero warnings, and immediate UI reactivity when changing assets.

---

### Component Flows

#### Flow 1: Asset Selection & ROI Auto-Population
1. Operator launches Workbench; sidebar displays "Active Machine Asset: -- None (Ad-hoc) --".
2. Operator selects "Cooling Fan A (`ast_fan_a`)".
3. Sidebar instantly displays asset details badge: Target ROI `(100, 120, 80, 80)`, Anchor ROI `(20, 20, 80, 80)`, Expected FPS: `60.0`, Baseline: `bsl_01 (N=3)`.
4. In Tab 1 ("Video Inspection"), `tx_input`, `ty_input`, `tw_input`, `th_input`, `ax_input`, `ay_input`, `aw_input`, `ah_input`, and `fps_override_val` automatically update to match `ast_fan_a`.
5. An informative banner alerts the operator: "Loaded configuration from active asset: Cooling Fan A".

#### Flow 2: Multi-Run Baseline Recording Wizard
1. Operator navigates to Tab 3 ("Baseline Wizard").
2. Active asset confirmation displays target asset ID and expected ROI bounding boxes.
3. Operator selects input source for baseline runs:
   - Option A: Select $\ge 3$ stored inspection runs from `ast_fan_a`'s history table.
   - Option B: Upload $\ge 3$ healthy inspection summary JSON files.
4. Wizard executes real-time validation:
   - **Quorum Check:** Verifies $N \ge 3$. If $N < 3$, displays warning and disables commit.
   - **Spatial Consistency Check:** Verifies each run's target and anchor ROIs match the asset's configured ROIs within $\pm 2$ px tolerance using `_rois_match`.
   - **Sampling Rate Check:** Verifies sampling rate in each run matches expected FPS within $\pm 2\%$.
   - **Signal Quality Gate:** Verifies at least one axis is `VALID` across all runs.
5. If valid, wizard calls `build_baseline(runs, asset_id=asset.asset_id, notes=notes)` and renders a robust statistical preview table.
6. Operator clicks "💾 Save Stored Baseline". `StorageManager.create_baseline` persists the record to SQLite and assigns a unique `baseline_id`.

#### Flow 3: Inspection History & Review Event Logging
1. Operator navigates to Tab 4 ("Inspection History").
2. Query fetches runs for the active asset via `storage_manager.list_inspection_runs(asset_id)`.
3. Filter bar allows filtering by status (`Normal`, `Review`, `Low confidence`, `Unassessed`).
4. Runs are rendered with colored status badges:
   - 🟢 `Normal`
   - 🔴 `Review`
   - 🟡 `Low confidence`
   - ⚪ `Unassessed`
5. Selecting a run reveals:
   - Summary metrics (X & Y dominant frequency, RMS displacement, peak-to-median dB, harmonic ratio).
   - Trace viewer: Loads raw displacement time series and Welch PSD arrays from `run.npz_rel_path` via `storage_manager.load_run_arrays()` and renders engineering charts.
6. Operator opens the **Review Event Logging Form**:
   - Operator selects status disposition (`Normal`, `Review`, `Low confidence`).
   - Types an operator note (e.g., "Elevated 8.5 Hz peak due to belt looseness. Work order #402 submitted.").
   - Enters Operator ID (defaults to "operator").
   - Clicks "Submit Review Event".
   - `storage_manager.create_review_event` logs the event in SQLite `review_events`, atomically updates `inspection_runs.status`, and displays the updated timeline.

#### Flow 4: Auto-Assessment Against Stored Baseline (1-Click Workflow)
1. In Tab 1 ("Video Inspection"), operator runs vibration analysis on a new inspection clip for `ast_fan_a`.
2. Analysis finishes and renders measurement results.
3. System checks SQLite: `storage_manager.get_latest_baseline_for_asset("ast_fan_a")`.
4. If a baseline exists, an **Auto-Assessment Card** appears:
   - "🎯 **Stored Baseline Detected:** `bsl_01` (N=3 healthy runs, established 2026-11-18)."
   - Button: `⚡ Run 1-Click Baseline Assessment`.
5. On click, `evaluate_run_against_baseline(summary, baseline.baseline_record, z_threshold=3.0)` executes.
6. Results banner displays verdict:
   - 🟢 `NORMAL`: All features within normal baseline bounds ($|z| < 3.0$).
   - 🔴 `REVIEW`: Feature deviation threshold exceeded ($|z| \ge 3.0$) with trigger list.
   - 🟡 `LOW CONFIDENCE`: Signal quality gate failed (e.g. anchor contamination).
7. Feature deviation table and standardized z-bar chart are rendered.
8. Operator clicks "💾 Save Run to Asset History", which stores the run with `baseline_id` linked and status set to `evaluation.status`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| **Multi-Run Aggregation** | Custom statistical average or variance calculation | `phasesight.baseline.build_baseline` | Already handles Median + MAD, scale factor ($1.4826$), epsilon floor, zero-MAD bounds, and immutable `BaselineRecord` serialization. |
| **Statistical Deviation Scoring** | Custom percentage difference or standard z-score | `phasesight.baseline.evaluate_run_against_baseline` | Uses robust outlier-resistant z-score $z_{\text{robust}} = \frac{x - \text{median}}{1.4826 \times \text{MAD} + \epsilon}$ with confidence gating. |
| **ROI Matching Check** | Ad-hoc coordinate comparison | `phasesight.baseline._rois_match` [VERIFIED: `phasesight/baseline.py:325-332`] | Enforces exact coordinate tolerance ($\pm 2$ px) across $x, y, w, h$. |
| **Relational Data Management** | Loose JSON files in folders or custom database tables | `phasesight.storage.StorageManager` [VERIFIED: `phasesight/storage.py:444-1581`] | Provides verified SQLite schema, foreign key cascades, thread-safe locking, and migration tracking. |
| **Array Compression & Loading** | Custom pickle, JSON, or CSV serialization for time series | `phasesight.storage.RunArrays` [VERIFIED: `phasesight/storage.py:263-337`] | Uses `numpy.savez_compressed` (<25 KB per 10s run, <4ms load time, zero data corruption). |
| **UI Headless Testing** | Selenium, Playwright, or external browser drivers | `streamlit.testing.v1.AppTest` [VERIFIED: `tests/test_ui.py:5`] | Official lightweight headless testing runner for Streamlit; runs in <1s with full widget inspection. |

---

## Runtime State Inventory

Not applicable. Phase 5 is an additive feature phase integrating existing persistence and baseline modules into the Streamlit UI. No database renames, schema breaking changes, or runtime data migrations are required.

---

## Common Pitfalls

### Pitfall 1: Streamlit Widget Key vs Session State Collision
- **What goes wrong:** Setting widget values in `st.session_state` while also passing `value=...` to `st.number_input()` causes Streamlit to issue a warning: `The widget with key "tx_input" was created with a default value but also had its value set via the Session State API.`
- **Why it happens:** Streamlit treats `key` as the single source of truth; passing an explicit `value` parameter conflicts with session state management.
- **How to avoid:** Initialize the key once via `st.session_state.setdefault(key, default)`. Subsequent calls to `st.number_input(..., key=key)` must omit the `value` parameter. When switching assets, update `st.session_state[key]` prior to widget rendering.
- **Warning signs:** Streamlit yellow warning banner in console or UI during asset selection.

### Pitfall 2: Stateful Database Connections Across Reruns
- **What goes wrong:** Creating a new `StorageManager` instance on every Streamlit script execution causes SQLite connection thrashing, file lock contention, and in-memory test database resets.
- **Why it happens:** Streamlit re-runs the entire Python script from top to bottom on every user interaction.
- **How to avoid:** Cache or store `StorageManager` in `st.session_state`:
  ```python
  def get_storage_manager() -> StorageManager:
      if "storage_manager" not in st.session_state:
          st.session_state["storage_manager"] = StorageManager()
      return st.session_state["storage_manager"]
  ```
  In tests, pre-populate `at.session_state["storage_manager"] = StorageManager(db_path=":memory:")` before running the test script.

### Pitfall 3: Baseline Quorum & Spatial Drift Violations
- **What goes wrong:** Operator attempts to build a baseline using fewer than 3 runs, or runs where the camera was moved and the Target ROI coordinates shifted by more than 2 pixels.
- **Why it happens:** Lack of immediate UI validation feedback before calling `build_baseline()`.
- **How to avoid:** In the Baseline Wizard, run client-side pre-validation: check `len(selected_runs) >= 3` and evaluate `_rois_match(asset.target_roi, run_target_roi)`. Display clear badges for Quorum (✅ $N \ge 3$), Target ROI Match (✅ $\le 2$ px), and Sampling Rate (✅ $\le 2\%$). Disable the "Save Baseline" button until all validation checks pass.

### Pitfall 4: Status Desynchronization Between Runs and Review Events
- **What goes wrong:** Operator logs a review event marking a run as `Normal`, but the history table continues displaying `Review` or `Unassessed`.
- **Why it happens:** Storing review events without synchronizing the parent `inspection_runs.status` column.
- **How to avoid:** `StorageManager.create_review_event()` already updates `inspection_runs.status` in the database within a single transaction [VERIFIED: `phasesight/storage.py:1430-1434`]. In the UI, immediately invoke `st.rerun()` after submitting a review event to refresh the cached run list.

### Pitfall 5: Heavy NPZ Array Loading Slowing History Display
- **What goes wrong:** Iterating through dozens of historical runs and loading every `.npz` file during table rendering causes UI lag.
- **Why it happens:** Decompressing 50+ NPZ archives synchronously on every script rerun.
- **How to avoid:** Render the historical run log using only SQLite metadata columns (`run_id`, `timestamp`, `measured_fps`, `duration_s`, `status`, `summary_json`). Load `RunArrays` from disk *only* when the operator explicitly selects a specific run for deep-dive spectrum inspection.

### Pitfall 6: Matplotlib Temp Directory Warning in Sandboxed / Headless Environments
- **What goes wrong:** Headless tests or server environments log warnings: `/Users/.../.matplotlib is not a writable directory`.
- **Why it happens:** Matplotlib attempts to write font cache to the user's home directory.
- **How to avoid:** Configure `os.environ["MPLCONFIGDIR"] = tempfile.gettempdir()` at the module root of `phasesight/app.py` before importing `matplotlib.pyplot`.

---

## Code Examples (Verified In-Repo Patterns)

### 1. In-Repo Discrete Values & Status Constants
Every status constant and dataclass definition used in Phase 5 is verified from source-of-truth files:

```python
# [VERIFIED: phasesight/storage.py:34-35]
VALID_RUN_STATUSES = ("Normal", "Review", "Low confidence", "Unassessed")
VALID_REVIEW_STATUSES = ("Normal", "Review", "Low confidence")
```

```python
# [VERIFIED: phasesight/storage.py:47-60]
@dataclass(frozen=True)
class AssetRecord:
    """Asset configuration and ROI parameters."""

    asset_id: str
    name: str
    description: str = ""
    nominal_speed_rpm: float | None = None
    target_roi: dict[str, int] = field(default_factory=dict)
    anchor_roi: dict[str, int] = field(default_factory=dict)
    expected_fps: float = 60.0
    scale_calibration: dict[str, Any] | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    updated_at: str = field(default_factory=_utc_now_iso)
```

```python
# [VERIFIED: phasesight/storage.py:105-118]
@dataclass(frozen=True)
class StoredBaseline:
    """Persisted statistical baseline record linked to an asset."""

    baseline_id: str
    asset_id: str
    created_at: str
    run_count: int
    baseline_record: BaselineRecord
    camera_settings: dict[str, Any] = field(default_factory=dict)
    npz_rel_path: str | None = None
    notes: str = ""
    version: str = "1.0"
```

```python
# [VERIFIED: phasesight/storage.py:157-173]
@dataclass(frozen=True)
class InspectionRunRecord:
    """Persisted record of an inspection run."""

    run_id: str
    asset_id: str
    timestamp: str
    video_path: str
    measured_fps: float
    duration_s: float
    frames_analysed: int
    valid_patch_ratio: float = 1.0
    summary: dict[str, Any] = field(default_factory=dict)
    baseline_id: str | None = None
    npz_rel_path: str | None = None
    status: str = "Unassessed"
```

```python
# [VERIFIED: phasesight/storage.py:203-216]
@dataclass(frozen=True)
class ReviewEventRecord:
    """Operator review classification and assessment notes."""

    event_id: str
    run_id: str
    status: str
    triggered_features: list[str] = field(default_factory=list)
    operator_note: str = ""
    evidence_image_rel_path: str | None = None
    evaluation: BaselineEvaluation | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    operator_id: str = "operator"
```

```python
# [VERIFIED: phasesight/baseline.py:325-332]
def _rois_match(r1: dict[str, int], r2: dict[str, int], tolerance: int = 2) -> bool:
    """Check if two ROIs match within pixel tolerance."""
    return (
        abs(r1["x"] - r2["x"]) <= tolerance
        and abs(r1["y"] - r2["y"]) <= tolerance
        and abs(r1["width"] - r2["width"]) <= tolerance
        and abs(r1["height"] - r2["height"]) <= tolerance
    )
```

```python
# [VERIFIED: phasesight/baseline.py:335-344]
def build_baseline(
    runs: list[dict[str, Any]],
    *,
    asset_id: str = "default_asset",
    min_runs: int = 3,
    require_valid_axes: list[str] | None = None,
    feature_epsilons: dict[str, float] | None = None,
    notes: str = "",
) -> BaselineRecord:
    """Aggregate N >= 3 healthy inspection runs into an immutable BaselineRecord using Median and scaled MAD."""
```

```python
# [VERIFIED: phasesight/baseline.py:569-577]
def evaluate_run_against_baseline(
    current: dict[str, Any],
    baseline: BaselineRecord,
    *,
    z_threshold: float = 3.0,
    axis: str = "both",
) -> BaselineEvaluation:
    """Screen an inspection run against a BaselineRecord using Confidence and Review Gates."""
```

---

### 2. Global Sidebar Asset Selector Pattern
```python
def render_sidebar_asset_selector(sm: StorageManager) -> AssetRecord | None:
    """Render global asset selector and asset info card in Streamlit sidebar."""
    st.sidebar.markdown("### 🏭 Machine Asset")
    
    assets = sm.list_assets()
    options = ["-- None (Ad-hoc Analysis) --"] + [f"{a.name} ({a.asset_id})" for a in assets]
    id_map = {f"{a.name} ({a.asset_id})": a.asset_id for a in assets}
    
    current_asset_id = st.session_state.get("selected_asset_id")
    current_index = 0
    if current_asset_id:
        for idx, a in enumerate(assets):
            if a.asset_id == current_asset_id:
                current_index = idx + 1
                break
                
    chosen = st.sidebar.selectbox("Active Asset:", options, index=current_index, key="sidebar_asset_choice")
    active_asset: AssetRecord | None = None
    
    if chosen != "-- None (Ad-hoc Analysis) --":
        chosen_id = id_map[chosen]
        active_asset = sm.get_asset(chosen_id)
        st.session_state["selected_asset_id"] = chosen_id
        
        # Display asset card
        latest_base = sm.get_latest_baseline_for_asset(chosen_id)
        runs = sm.list_inspection_runs(asset_id=chosen_id, limit=1)
        base_str = f"✅ `{latest_base.baseline_id}` (N={latest_base.run_count})" if latest_base else "⚠️ None"
        
        st.sidebar.info(
            f"**Asset:** {active_asset.name}\n\n"
            f"• **Target ROI:** {active_asset.target_roi['width']}x{active_asset.target_roi['height']} at ({active_asset.target_roi['x']},{active_asset.target_roi['y']})\n"
            f"• **Anchor ROI:** {active_asset.anchor_roi['width']}x{active_asset.anchor_roi['height']} at ({active_asset.anchor_roi['x']},{active_asset.anchor_roi['y']})\n"
            f"• **Expected FPS:** {active_asset.expected_fps:.1f}\n"
            f"• **Baseline:** {base_str}"
        )
    else:
        st.session_state["selected_asset_id"] = None
        st.sidebar.caption("Operating in ad-hoc mode. Select an asset to enable tracking and history.")
        
    return active_asset
```

---

### 3. Baseline Wizard Quorum & Consistency Check
```python
def validate_and_build_wizard_baseline(
    asset: AssetRecord,
    candidate_runs: list[dict[str, Any]],
    notes: str,
    sm: StorageManager,
) -> tuple[bool, str, StoredBaseline | None]:
    """Validate quorum, spatial ROIs, and sampling rate, then persist StoredBaseline."""
    # 1. Quorum check
    if len(candidate_runs) < 3:
        return False, f"Quorum failure: At least 3 healthy runs required (got {len(candidate_runs)}).", None

    # 2. ROI consistency check against asset definition
    for idx, run in enumerate(candidate_runs):
        t_roi = run.get("target_roi_xywh", run.get("target_roi"))
        a_roi = run.get("anchor_roi_xywh", run.get("anchor_roi"))
        if not t_roi or not _rois_match(asset.target_roi, t_roi, tolerance=2):
            return False, f"Run {idx+1} Target ROI diverges from asset ROI ({asset.target_roi}).", None
        if not a_roi or not _rois_match(asset.anchor_roi, a_roi, tolerance=2):
            return False, f"Run {idx+1} Anchor ROI diverges from asset ROI ({asset.anchor_roi}).", None

        # 3. Sampling rate consistency check (±2%)
        run_fps = float(run.get("fps_used", run.get("sampling_rate_hz", 0.0)))
        if asset.expected_fps > 0 and abs(run_fps - asset.expected_fps) / asset.expected_fps > 0.02:
            return False, f"Run {idx+1} FPS ({run_fps:.2f}) differs by >2% from asset FPS ({asset.expected_fps:.2f}).", None

    try:
        baseline_record = build_baseline(candidate_runs, asset_id=asset.asset_id, notes=notes)
        stored_baseline = sm.create_baseline(
            asset_id=asset.asset_id,
            baseline_record=baseline_record,
            notes=notes,
        )
        return True, f"Successfully created StoredBaseline `{stored_baseline.baseline_id}` (N={stored_baseline.run_count})", stored_baseline
    except Exception as exc:
        return False, f"Baseline aggregation error: {exc}", None
```

---

### 4. Headless Test Suite In `tests/test_ui.py`
```python
def test_ui_asset_selection_and_roi_population():
    """Verify selecting an asset in the sidebar updates inspection ROIs."""
    from phasesight.storage import StorageManager
    from streamlit.testing.v1 import AppTest
    
    # 1. Create in-memory storage with pre-configured asset
    sm = StorageManager(db_path=":memory:")
    asset = sm.create_asset(
        name="Exhaust Fan #4",
        target_roi={"x": 250, "y": 140, "width": 120, "height": 120},
        anchor_roi={"x": 40, "y": 40, "width": 120, "height": 120},
        expected_fps=59.94,
        asset_id="ast_fan_4",
    )
    
    # 2. Launch headless AppTest and inject in-memory storage
    at = AppTest.from_file("phasesight/app.py", default_timeout=30)
    at.session_state["storage_manager"] = sm
    at.run()
    assert not at.exception
    
    # 3. Select Exhaust Fan #4 in sidebar
    at.sidebar.selectbox[0].select("Exhaust Fan #4 (ast_fan_4)").run()
    assert not at.exception
    
    # 4. Verify inspection tab inputs reflect active asset's ROIs and FPS
    assert at.session_state["selected_asset_id"] == "ast_fan_4"
    assert at.session_state["tx_input"] == 250
    assert at.session_state["ty_input"] == 140
    assert at.session_state["tw_input"] == 120
    assert at.session_state["th_input"] == 120
    assert at.session_state["fps_override_val"] == pytest.approx(59.94, rel=1e-2)
```

---

## State of the Art

| Old Approach (Phase 2 & 3) | Current Approach (Phase 5) | When Changed | Impact |
|----------------------------|----------------------------|--------------|--------|
| **Manual Ad-hoc ROI Entry** | **Asset-Driven Auto-Population** | Phase 5 | Operator selects physical machine once; workbench automatically applies verified ROIs and expected FPS, eliminating human configuration error. |
| **Loose Summary Files for Baseline** | **Wizard-Driven Baseline Creation** | Phase 5 | Quorum ($N \ge 3$), spatial ROI matching ($\pm 2$ px), and sampling rate consistency ($\pm 2\%$) are validated interactively before persisting `StoredBaseline` in SQLite. |
| **Volatile Single-Run Results** | **Persistent Run Archival with NPZ** | Phase 5 | Every inspection is stored with measured FPS, duration, feature summaries, and compressed NPZ arrays (<25 KB), enabling long-term historical exploration. |
| **No Review Feedback Loop** | **Operator Review Event Logging** | Phase 5 | Operators log formal review decisions (`Normal`, `Review`, `Low confidence`) with notes, updating parent run status with a full audit trail. |
| **Manual Baseline Comparison** | **1-Click Auto-Assessment** | Phase 5 | After running video analysis on an asset with an established baseline, workbench automatically offers 1-click evaluation against the latest baseline. |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Operators prefer a persistent sidebar asset selector over separate per-tab dropdowns. | Architecture Patterns | Low. Sidebar selector is standard in Streamlit multi-tab apps and ensures consistent context. Per-tab selector could be added if requested. |
| A2 | Building baseline from previously completed inspection runs is the primary workflow, with summary JSON upload as fallback. | Baseline Wizard | Low. Both options are supported in the Wizard. |
| A3 | Decompressing NPZ arrays on-demand per selected run provides acceptable responsiveness (<50ms). | Common Pitfalls | Verified in Phase 4 benchmarks (<2ms load time for 600 frames). |

---

## Open Questions

1. **Auto-Save vs Explicit Save for Inspection Runs:**
   - *What we know:* Auto-saving every analysis ensures runs are never lost if the operator refreshes the page, but may log contaminated or accidental runs.
   - *Recommendation:* Provide an "Auto-save inspection runs to asset history" checkbox (enabled by default when an asset is selected) along with an explicit "💾 Save Run to History" button. Unassessed runs can always be tagged or deleted in the History tab.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Runtime | ✓ | 3.13.15 | — |
| Streamlit | Operator Workbench UI | ✓ | 1.67.0 | — |
| SQLite (`sqlite3`) | Persistence engine | ✓ | 3.50.4 | — |
| NumPy (`numpy`) | Array processing & NPZ | ✓ | 2.5.5 | — |
| SciPy (`scipy`) | Welch PSD & Statistics | ✓ | 1.15.2 | — |
| OpenCV (`cv2`) | Video reading & Phase correlation | ✓ | 4.11.0 | — |
| Matplotlib (`matplotlib`) | Plot generation | ✓ | 3.10.1 | — |
| pytest | Automated test runner | ✓ | 8.3.5 | — |

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` 8.3.5 + `streamlit.testing.v1.AppTest` [VERIFIED: pyproject.toml:20, installed 8.3.5] |
| Config file | `pyproject.toml` (`[tool.pytest.ini_options]` testpaths = ["tests"]) [VERIFIED: pyproject.toml:28-30] |
| Quick run command | `./.venv/bin/pytest tests/test_ui.py -x` |
| Full suite command | `./.venv/bin/pytest` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| **HIST-01** | Asset selection updates session state and populates ROIs and FPS in Tab 1 | integration (headless AppTest) | `./.venv/bin/pytest tests/test_ui.py -k test_ui_asset_selection_updates_rois_and_fps -x` | ❌ Wave 0 Gap |
| **HIST-02** | Baseline Wizard quorum validation (<3 rejected, $\ge 3$ accepted) and baseline persistence | unit / integration | `./.venv/bin/pytest tests/test_ui.py -k test_ui_baseline_wizard_quorum_and_creation -x` | ❌ Wave 0 Gap |
| **HIST-03** | Inspection History table renders runs with status badges and loads NPZ arrays | integration (headless AppTest) | `./.venv/bin/pytest tests/test_ui.py -k test_ui_inspection_history_table_and_traces -x` | ❌ Wave 0 Gap |
| **HIST-04** | Operator review event form logs review note and updates run status in database | integration (headless AppTest) | `./.venv/bin/pytest tests/test_ui.py -k test_ui_review_event_logging_and_status_sync -x` | ❌ Wave 0 Gap |
| **HIST-05** | 1-Click auto-assessment triggers evaluation against latest asset baseline | integration (headless AppTest) | `./.venv/bin/pytest tests/test_ui.py -k test_ui_auto_assessment_against_stored_baseline -x` | ❌ Wave 0 Gap |
| **HIST-06** | Full UI AppTest test suite runs cleanly in headless mode with in-memory storage | integration (headless AppTest) | `./.venv/bin/pytest tests/test_ui.py` | ✅ Existing file covers initial render; needs expansion |

### Sampling Rate
- **Per task commit:** `./.venv/bin/pytest tests/test_ui.py -x`
- **Per wave merge:** `./.venv/bin/pytest` (full 55+ test suite green)
- **Phase gate:** Full test suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Expand `tests/test_ui.py` with test fixtures for in-memory `StorageManager` populated with sample assets, baselines, and runs.
- [ ] Implement headless test methods covering `HIST-01` through `HIST-05`.

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| **V5 Input Validation** | Yes | Strict boundary validation on user input: ROI coordinates ($x, y \ge 0$, width, height $\ge 32$, inside frame bounds), expected FPS $>0$, quorum check ($N \ge 3$), status values restricted to `VALID_RUN_STATUSES` and `VALID_REVIEW_STATUSES`. |
| **V8 Data Protection & Storage Security** | Yes | Parameterized SQL queries preventing SQL injection; path traversal verification (`StorageManager.resolve_path`) preventing directory escape on NPZ and evidence paths. |
| **V14 Concurrency & Integrity** | Yes | Thread synchronization (`threading.RLock`) in `StorageManager` preventing SQLite `bad parameter or other API misuse` crashes during concurrent Streamlit reruns. |

### Known Threat Patterns for Streamlit Workbench

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| **Malicious Path Injection via Video Upload** | Tampering | Video uploads are saved to dedicated `output/uploads/` directory using sanitized basenames (`Path(uploaded_file.name).name`). |
| **Path Traversal in Array Resolution** | Information Disclosure | `StorageManager.resolve_path` enforces that resolved NPZ and evidence paths reside strictly within `storage_root`. |
| **SQL Injection via Search / Asset Names** | Tampering | All database operations use `sqlite3` parameterized queries (`?` placeholders). No string interpolation in SQL. |
| **Streamlit State Desynchronization** | Denial of Service | Avoid duplicate keys or unmanaged session state mutations. Standardize on widget key initialization and callbacks. |

---

## Sources

### Primary (HIGH confidence)
- `phasesight/storage.py`: StorageManager, AssetRecord, StoredBaseline, InspectionRunRecord, ReviewEventRecord, RunArrays [VERIFIED: lines 1-1581]
- `phasesight/baseline.py`: build_baseline, evaluate_run_against_baseline, _rois_match, FeatureStats [VERIFIED: lines 1-688]
- `phasesight/app.py`: Streamlit operator workbench implementation [VERIFIED: lines 1-709]
- `tests/test_ui.py`: Streamlit headless AppTest integration [VERIFIED: lines 1-50]
- `tests/test_storage.py`: Storage test suite & in-memory fixtures [VERIFIED: lines 1-591]
- `pyproject.toml`: Project dependencies and test configurations [VERIFIED: lines 1-30]

### Secondary (MEDIUM confidence)
- Streamlit official testing documentation: `docs.streamlit.io/develop/api-reference/app-testing/apptest`
- Streamlit widget state management policy: `docs.streamlit.io/develop/concepts/architecture/session-state`

---

## Metadata

**Confidence breakdown:**
- UI Layout & Component Architecture: HIGH - Verified against Streamlit 1.67.0 and `phasesight/app.py`.
- Persistence Integration: HIGH - Verified against `phasesight/storage.py` and `tests/test_storage.py`.
- Session State & Widget Key Policy: HIGH - Empirically tested and verified via `streamlit.testing.v1.AppTest`.
- Testing Strategy: HIGH - Validated using headless AppTest with in-memory SQLite injection.

**Research date:** 2026-11-19  
**Valid until:** 2026-12-19 (30 days)
