# PhaseSight Development Roadmap (Prasunex Innovathon 2026)

## Milestone Overview

### Phase 1: Core Signal & Tracking Pipeline
- **Status:** COMPLETED ✅
- **Deliverables:** `phasesight/tracker.py`, `phasesight/analysis.py`, `phasesight/video.py`, synthetic test harness, CLI.
- **Exit Check:** 14 automated tests pass, 8.5 Hz recovered with <0.005 Hz error and r > 0.90 under camera shake.

### Phase 2: Local Operator Workbench MVP
- **Status:** COMPLETED ✅
- **Deliverables:** `phasesight/app.py`, `phasesight/ui_helpers.py`, real-time ROI validation, spectra visualization, CSV/PNG/JSON downloads, 1-to-1 comparison.
- **Exit Check:** 24 automated tests pass (including headless `AppTest`), baseline vs changed returns WARNING_CHANGE, null returns CONTAMINATED.

### Phase 3: Statistical Baseline Engine
- **Status:** COMPLETED ✅
- **Deliverables:** `phasesight/baseline.py`, multi-run aggregation ($\ge 3$ captures), Median + MAD statistics, robust deviation score $z_{\text{robust}} = \frac{x - \text{median}}{1.4826 \times \text{MAD} + \epsilon}$, Normal / Review / Low confidence classification.
- **Plans:** 1 plan (`03-PLAN.md` / `03-01-PLAN.md`)
  - [x] `03-01-PLAN.md` — Statistical Baseline Engine core, unit test matrix, CLI, and Workbench UI
- **Exit Check:** Automated tests for single-run vs multi-run baseline, zero-MAD edge cases, and confidence gating (16 tests in `tests/test_baseline.py`, 40/40 passing).

### Phase 4: Local Persistence Layer (SQLite + NumPy NPZ)
- **Status:** COMPLETED ✅
- **Deliverables:** `phasesight/storage.py`, SQLite schema for Assets, Baselines, Inspection Runs, and Review Events; NPZ storage for displacement and PSD time series.
- **Plans:** 1 plan (`04-PLAN.md` / `04-01-PLAN.md`)
  - [x] `04-01-PLAN.md` — Local persistence layer, SQLite schema, NPZ array storage, CRUD operations, test suite, and CLI
- **Exit Check:** 15 unit tests in `tests/test_storage.py` (55/55 tests passing across codebase), foreign key cascades verified, and CLI storage commands verified.

### Phase 5: Workbench History & Asset Integration
- **Status:** COMPLETED ✅
- **Deliverables:** Streamlit UI tabs for Asset Management, Baseline Recording Wizard, and Inspection Run History with status badges and notes.
- **Plans:** 1 plan (`05-PLAN.md` / `05-01-PLAN.md`)
  - [x] `05-01-PLAN.md` — Workbench history, asset management, baseline wizard, inspection history with NPZ trace exploration, review event logging, and headless UI testing
- **Exit Check:** 12 tests in `tests/test_ui.py` (63/63 tests passing across codebase), operator can create assets, record baselines, inspect new videos, and view comparison logs.

### Phase 6: Live Webcam Stream & Dropped Frame Handling
- **Status:** COMPLETED ✅
- **Deliverables:** `phasesight/capture.py`, monotonic time acquisition, empirical FPS $f_s = 1.0 / \text{median}(\Delta t)$, robust timing jitter $\text{std}(\Delta t) / \text{median}(\Delta t)$, dropped frame counting, status classification (`STABLE`, `WARNING_JITTER`, `REJECTED_UNSTABLE`), `MockVideoCapture` virtual streams, CLI `capture` command, and Streamlit Workbench Tab 1 live capture interface with stability card and analysis gate.
- **Plans:** 1 plan (`06-PLAN.md` / `06-01-PLAN.md`)
  - [x] `06-01-PLAN.md` — Live webcam capture engine, dropped frame & jitter stability quantification, CLI capture command, and Streamlit operator workbench integration
- **Exit Check:** 13 unit tests in `tests/test_capture.py` and 15 tests in `tests/test_ui.py` (79/79 passing across codebase), live webcam preview and capture with constant-frame-rate verification and gating.

### Phase 7: Final Validation & Demonstration Package
- **Status:** COMPLETED ✅
- **Deliverables:** `phasesight/validation.py` implementing Protocols T1 through T6 and `run_full_validation_matrix()`, extended CLI `phasesight validate` with `--test`, `--legacy`, and `--json`, `tests/test_validation_matrix.py` (89 total tests passing), `DEMO_GUIDE.md` 8-stage interactive evaluator walkthrough, hardened `README.md` and `TEST_REPORT.md` with complete empirical evidence, public benchmark dataset evaluation protocols (Mendeley Rotor at 500 FPS + eddy-current displacement sensors), and non-negotiable boundaries.
- **Plans:** 1 plan (`07-PLAN.md` / `07-01-PLAN.md`)
  - [x] `07-01-PLAN.md` — Proposal Page 5 validation matrix (T1–T6), CLI validate extension, DEMO_GUIDE.md 8-stage walkthrough, and documentation hardening (README.md, TEST_REPORT.md)
- **Exit Check:** 89 passing tests in pytest across all 9 modules (100% pass rate), 6/6 proposal validation protocols passing with verified numerical criteria, CLI validate outputting structured table and JSON, DEMO_GUIDE.md walkthrough ready for evaluators, and hardened README.md and TEST_REPORT.md.
