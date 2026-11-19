# PhaseSight Project State

## Active Milestone
**Phase 6: Live Webcam Stream & Dropped Frame Handling**

## Completed Milestones
- Phase 1: Core Signal & Tracking Pipeline (COMPLETED ✅)
- Phase 2: Local Operator Workbench MVP (COMPLETED ✅)
- Phase 3: Statistical Baseline Engine (COMPLETED ✅)
- Phase 4: Local Persistence Layer (COMPLETED ✅)
- Phase 5: Workbench History & Asset Integration (COMPLETED ✅)
  - Integrated `StorageManager` session caching in `phasesight/app.py`.
  - Global Sidebar Asset Anchor: asset selector, details card, and storage diagnostics.
  - Tab 1: Active asset ROI/FPS synchronization without widget collision warnings, 1-click Auto-Assessment card against stored baseline, and 'Save Run to Asset History' persisting `InspectionRunRecord` and compressed NPZ `RunArrays`.
  - Tab 2: Asset Management (directory catalog, registration form with 'Copy ROIs from inspection' shortcut, parameter editor, and cascading deletion).
  - Tab 3: Baseline Recording Wizard (quorum $N \ge 3$, spatial ROI consistency $\pm 2$ px, sampling rate consistency $\pm 2\%$, Median + MAD preview, commit to SQLite).
  - Tab 4: Inspection History (filterable run log with status badges, on-demand NPZ array exploration with 2-panel engineering plots, operator review event logging form, and review audit trail).
  - 12 comprehensive unit tests in `tests/test_ui.py` (63/63 tests passing across entire codebase).

## Next Up
Phase 6: Live Webcam Stream & Dropped Frame Handling (Support `camera_id` in video capture, fixed-duration live buffer, dropped frame and timestamp regularity verification).
