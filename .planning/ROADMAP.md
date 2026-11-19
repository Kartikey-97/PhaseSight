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

### Phase 5: Workbench History & Asset Integration (CURRENT MILESTONE)
- **Status:** IN PROGRESS 🚀
- **Deliverables:** Streamlit UI tabs for Asset Management, Baseline Recording Wizard, and Inspection Run History with status badges and notes.
- **Plans:** 1 plan (`05-PLAN.md` / `05-01-PLAN.md`)
  - [ ] `05-01-PLAN.md` — Workbench history, asset management, baseline wizard, inspection history with NPZ trace exploration, review event logging, and headless UI testing
- **Exit Check:** Operator can create an asset, record 3 baselines, inspect a new video, and view the comparison log.

### Phase 6: Live Webcam Stream & Dropped Frame Handling
- **Status:** PLANNED
- **Deliverables:** Support `camera_id` in video capture, fixed-duration live buffer, dropped frame and timestamp regularity verification.
- **Exit Check:** Live webcam preview and capture with constant-frame-rate verification.

### Phase 7: Final Validation & Demonstration Package
- **Status:** PLANNED
- **Deliverables:** Synthetic test matrix T1–T6 verification, benchmark dataset evaluation, screenshots, user guide, and demo walkthrough.
