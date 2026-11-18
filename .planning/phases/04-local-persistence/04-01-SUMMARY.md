# Phase 4 Plan 01 Summary: Local Persistence Layer (SQLite + NumPy NPZ)

## Execution Overview
Phase 4 transitioned PhaseSight from single-video ad-hoc analysis and loose JSON files to a local-first asset persistence architecture combining an ACID SQLite database (`phasesight.db`) with high-performance compressed array storage (`numpy.savez_compressed` `.npz`).

## Core Deliverables

### 1. Storage Engine (`phasesight/storage.py`)
- **Typed Dataclasses:**
  - `AssetRecord`: Asset configuration, description, nominal speed (RPM), target ROI, anchor ROI, expected FPS, scale calibration. Seamlessly round-trips to `phasesight.tracker.ROI`.
  - `StoredBaseline`: Persisted statistical baseline linked to an asset with `BaselineRecord`, camera settings, and reference arrays.
  - `InspectionRunRecord`: Persisted inspection run with measured FPS, duration, frames analysed, valid patch ratio, feature summary, and status (`Normal`, `Review`, `Low confidence`, `Unassessed`).
  - `ReviewEventRecord`: Operator review classification, note, evidence image relative path, and full `BaselineEvaluation`.
  - `RunArrays`: High-performance numerical arrays for timestamps, relative translations, raw target/anchor translations, correlation responses, and Welch PSD spectra.
- **SQLite Lifecycle & Pragmas:**
  - Mandatory execution of `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, and `PRAGMA synchronous = NORMAL;`.
  - Idempotent schema creation and migration tracked via `PRAGMA user_version`.
  - Reentrant thread lock (`threading.RLock`) synchronizing all database access to prevent multi-threaded SQLite interface errors.
- **Relational Integrity & Cascades:**
  - `assets` -> `baselines` (`ON DELETE CASCADE`)
  - `assets` -> `inspection_runs` (`ON DELETE CASCADE`)
  - `baselines` -> `inspection_runs` (`ON DELETE SET NULL`)
  - `inspection_runs` -> `review_events` (`ON DELETE CASCADE`)
  - Automatic filesystem cleanup when `delete_files=True`.
- **Path Security:**
  - `resolve_path()` guards against path traversal attacks outside `storage_root`.
  - In-memory isolation (`db_path=":memory:"`) with automatic temporary directory cleanup for headless testing.

### 2. Unit Test Matrix (`tests/test_storage.py`)
15 deterministic unit tests covering:
1. `test_asset_crud_and_duplicates` (PERSIST-01)
2. `test_roi_dataclass_roundtrip` (PERSIST-01)
3. `test_baseline_persistence_and_latest` (PERSIST-02)
4. `test_inspection_run_archival_and_status` (PERSIST-03)
5. `test_review_event_logging_and_constraints` (PERSIST-04)
6. `test_run_arrays_npz_fidelity_and_compression` (PERSIST-05)
7. `test_npz_missing_optional_arrays` (PERSIST-05)
8. `test_foreign_key_cascades_asset_deletion` (PERSIST-06)
9. `test_foreign_key_set_null_baseline_deletion` (PERSIST-06)
10. `test_foreign_key_cascades_run_deletion` (PERSIST-06)
11. `test_file_cleanup_on_record_deletion` (PERSIST-06)
12. `test_in_memory_isolation_and_tempdir` (PERSIST-06)
13. `test_thread_concurrency_safety` (PERSIST-06, 10 concurrent threads)
14. `test_schema_migration_idempotence` (PERSIST-06)
15. `test_path_traversal_prevention` (PERSIST-06)

### 3. CLI Subcommands (`phasesight/cli.py`)
- `phasesight db-info`: Storage root, database path, SQLite version, schema version, foreign key status, and row counts.
- `phasesight asset create`: Register asset with name, ROIs, expected FPS, nominal RPM, and description.
- `phasesight asset list`: Formatted table or JSON listing of registered assets.
- `phasesight asset show <asset_id>`: Detailed view of asset ROIs, baseline count, and inspection run history.

## Verification Results
- **Full Test Suite:** 55 passed out of 55 tests in 27.56s (`pytest -v`). Zero regressions.
- **Synthetic Validation Suite:** 4 of 4 scenarios pass (`phasesight validate`).
- **CLI Commands Verified:** `db-info`, `asset create`, `asset list`, `asset show` verified end-to-end.
