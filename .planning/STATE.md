# PhaseSight Project State

## Active Milestone
**Phase 4: Local Persistence Layer (SQLite + NumPy NPZ)**

## Completed Milestones
- Phase 1: Core Signal & Tracking Pipeline (COMPLETED ✅)
- Phase 2: Local Operator Workbench MVP (COMPLETED ✅)
- Phase 3: Statistical Baseline Engine (COMPLETED ✅)
  - `phasesight/baseline.py`: `build_baseline`, `evaluate_run_against_baseline`, `compute_robust_stats`, `serialize_baseline`, `deserialize_baseline`.
  - Quorum check ($N \ge 3$), Median + MAD scaled by 1.4826, physical noise floor $\epsilon$.
  - Two-stage screening: Confidence Gate -> Review Gate ($|z| \ge 3.0$) -> `Normal` / `Review` / `Low confidence`.
  - 16 dedicated unit tests in `tests/test_baseline.py` (all 40 tests passing).
  - CLI subcommands: `phasesight build-baseline` and `phasesight assess`.
  - Streamlit Tab 2 enhanced with statistical baseline mode, interactive $z$-score bar charts, and feature deviation tables.

## Next Up
Phase 4: Local Persistence Layer (SQLite schema for Assets, Baselines, Runs, and Review Events; NPZ storage for time series and PSD arrays).
