---
phase: 04-local-persistence
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - phasesight/storage.py
  - tests/test_storage.py
  - phasesight/cli.py
autonomous: true
requirements:
  - PERSIST-01
  - PERSIST-02
  - PERSIST-03
  - PERSIST-04
  - PERSIST-05
  - PERSIST-06

estimate:
  tokens: 48000
  raw_tokens: 24000
  tasks: 5
  confidence: high

must_haves:
  truths:
    - "SQLite connection initializes with PRAGMA foreign_keys = ON;, PRAGMA journal_mode = WAL;, and PRAGMA synchronous = NORMAL; on every opened connection."
    - "Database migrations use PRAGMA user_version to create and verify tables and indexes idempotently without external migration dependencies."
    - "StorageManager wraps database read/write operations with threading.RLock() preventing SQLite concurrent execution crashes in multi-threaded environments."
    - "Complete CRUD operations exist for Assets, Baselines, Inspection Runs, and Review Events with parameterised SQL queries."
    - "Deleting an asset cascades deletion to all associated baselines, runs, and review events via foreign key constraints."
    - "High-performance time series and PSD arrays are stored in compressed NumPy NPZ files (numpy.savez_compressed) with sub-5ms read/write latency."
    - "Evidence images are saved as PNG files with relative paths tracked in review events, supporting automatic filesystem cleanup on record deletion."
    - "StorageManager supports in-memory isolation (db_path=':memory:') with automatic temporary filesystem cleanup for headless unit tests."
    - "All storage models are typed dataclasses seamlessly round-tripping with BaselineRecord, BaselineEvaluation, ROI, and InspectionSummary."
    - "CLI provides db-info and asset management subcommands for administrative queries, asset creation, and listing."
  artifacts:
    - phasesight/storage.py
    - tests/test_storage.py
    - phasesight/cli.py
  key_links:
    - "phasesight/storage.py imports and round-trips BaselineRecord and BaselineEvaluation from phasesight/baseline.py"
    - "phasesight/storage.py imports and round-trips ROI from phasesight/tracker.py"
    - "phasesight/cli.py imports StorageManager and AssetRecord from phasesight/storage.py"
    - "tests/test_storage.py executes 15+ comprehensive unit tests covering PERSIST-01 through PERSIST-06"
---

<objective>
Implement the Phase 4 Local Persistence Layer for PhaseSight. Transition the platform from ad-hoc single-video analysis and loose JSON files to a robust, local-first asset persistence architecture combining an ACID SQLite database (`phasesight.db`) with high-performance compressed array storage (`numpy.savez_compressed` `.npz`). Implement complete CRUD operations and relational cascades for Assets, Baselines, Inspection Runs, and Review Events. Ensure thread safety via `threading.RLock`, provide seamless round-tripping with existing `phasesight.baseline` and `phasesight.tracker` models, supply a comprehensive test suite in `tests/test_storage.py`, and add administrative CLI subcommands to `phasesight/cli.py`.

Purpose: Enable long-term asset monitoring, multi-run history tracking, and durable baseline storage with sub-5ms array access and zero external database daemons.
Output: `phasesight/storage.py`, `tests/test_storage.py`, and enhanced `phasesight/cli.py`.
</objective>

<execution_context>
@~/.gemini/antigravity/gsd-core/workflows/execute-plan.md
@~/.gemini/antigravity/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/ROADMAP.md
@.planning/STATE.md
@.planning/phases/04-local-persistence/04-RESEARCH.md
@phasesight/tracker.py
@phasesight/analysis.py
@phasesight/video.py
@phasesight/baseline.py
@phasesight/cli.py
</context>

<tasks>

<task type="tracer">
  <name>Task 1: Core Dataclasses, Database Initialization, Pragmas, and StorageManager Skeleton</name>
  <files>phasesight/storage.py</files>
  <action>
Create phasesight/storage.py providing typed storage dataclasses, connection lifecycle management, strict pragmas, schema migrations, and the core StorageManager class per D-01, D-02, D-04, D-05, D-06, D-07, PERSIST-01, and PERSIST-06.

1. Implement typed frozen dataclasses with to_dict() and from_dict() methods:
   - AssetRecord: asset_id (str), name (str), description (str = ""), nominal_speed_rpm (float | None = None), target_roi (dict[str, int]), anchor_roi (dict[str, int]), expected_fps (float = 60.0), scale_calibration (dict[str, Any] | None = None), created_at (str ISO UTC), updated_at (str ISO UTC). Provide target_roi_obj() -> ROI and anchor_roi_obj() -> ROI converting to phasesight.tracker.ROI.
   - StoredBaseline: baseline_id (str), asset_id (str), created_at (str ISO UTC), run_count (int), baseline_record (BaselineRecord), camera_settings (dict[str, Any]), npz_rel_path (str | None = None), notes (str = ""), version (str = "1.0"). Ensure seamless round-trip with BaselineRecord.
   - InspectionRunRecord: run_id (str), asset_id (str), timestamp (str ISO UTC), video_path (str), measured_fps (float), duration_s (float), frames_analysed (int), valid_patch_ratio (float = 1.0), summary (dict[str, Any]), baseline_id (str | None = None), npz_rel_path (str | None = None), status (str = "Unassessed"). Status must default to 'Unassessed' and validate against ('Normal', 'Review', 'Low confidence', 'Unassessed').
   - ReviewEventRecord: event_id (str), run_id (str), status (str), triggered_features (list[str]), operator_note (str = ""), evidence_image_rel_path (str | None = None), evaluation (BaselineEvaluation | None = None), created_at (str ISO UTC), operator_id (str = "operator"). Status must validate against ('Normal', 'Review', 'Low confidence'). Ensure seamless round-trip with BaselineEvaluation.

2. Implement SQLite connection creation and migration helper functions:
   - create_connection(db_path: str | Path) -> sqlite3.Connection:
     - Connect with check_same_thread=False.
     - Set conn.row_factory = sqlite3.Row.
     - Always execute PRAGMA foreign_keys = ON; per D-05.
     - If db_path != ":memory:", execute PRAGMA journal_mode = WAL; and PRAGMA synchronous = NORMAL; per D-01.
   - init_schema(conn: sqlite3.Connection) -> None:
     - Check PRAGMA user_version. If version < 1, execute DDL schema:
       - Table assets (asset_id PK, name, description, nominal_speed_rpm, target_roi_json, anchor_roi_json, expected_fps, scale_calibration_json, created_at, updated_at).
       - Table baselines (baseline_id PK, asset_id FK -> assets ON DELETE CASCADE, created_at, run_count, camera_settings_json, baseline_record_json, npz_rel_path, notes, version).
       - Table inspection_runs (run_id PK, asset_id FK -> assets ON DELETE CASCADE, baseline_id FK -> baselines ON DELETE SET NULL, timestamp, video_path, measured_fps, duration_s, frames_analysed, valid_patch_ratio, npz_rel_path, summary_json, status).
       - Table review_events (event_id PK, run_id FK -> inspection_runs ON DELETE CASCADE, status, triggered_features_json, operator_note, evidence_image_rel_path, evaluation_json, created_at, operator_id).
       - Create indexes: idx_baselines_asset_id, idx_runs_asset_id, idx_runs_timestamp, idx_runs_baseline_id, idx_review_events_run_id, idx_review_events_created_at, idx_review_events_status.
       - Set PRAGMA user_version = 1.

3. Implement StorageManager class skeleton:
   - __init__(storage_root: str | Path | None = None, db_path: str | Path | None = None):
     - If storage_root is None, resolve from os.environ.get("PHASESIGHT_STORAGE_ROOT", "data/storage") per D-04.
     - If db_path is None, default to Path(storage_root) / "phasesight.db".
     - Handle db_path == ":memory:": if storage_root was not explicitly provided, allocate a tempfile.TemporaryDirectory() for filesystem artifacts per D-04.
     - Create self._lock = threading.RLock() to synchronize all database operations per D-01.
     - Create directories storage_root, storage_root/npz/runs, storage_root/npz/baselines, storage_root/evidence.
     - Open self._conn using create_connection(self.db_path) and run init_schema(self._conn).
   - Implement close() and context manager support (__enter__, __exit__): close connection and clean up temporary directory if present.
   - Implement get_db_info() -> dict[str, Any] returning schema version, foreign key status, db path, storage root, and row counts.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from phasesight.storage import StorageManager, AssetRecord; sm = StorageManager(db_path=':memory:'); info = sm.get_db_info(); assert info['foreign_keys'] == 1; assert info['schema_version'] == 1; sm.close(); print('Task 1 tracer verified') status=OK"</automated>
  </verify>
  <done>
All storage dataclasses defined, create_connection enforces foreign keys and WAL, init_schema executes idempotently, and StorageManager initializes cleanly in memory with thread safety.
  </done>
</task>

<task type="auto">
  <name>Task 2: High-Performance Compressed Array Persistence (RunArrays NPZ & Evidence Storage)</name>
  <files>phasesight/storage.py</files>
  <action>
Implement compressed numerical array serialization and evidence image filesystem handling in phasesight/storage.py per D-01, D-03, PERSIST-04, and PERSIST-05.

1. Implement RunArrays dataclass:
   - Attributes: timestamps_s (np.ndarray), relative_dx_px (np.ndarray), relative_dy_px (np.ndarray), target_dx_px (np.ndarray | None), target_dy_px (np.ndarray | None), anchor_dx_px (np.ndarray | None), anchor_dy_px (np.ndarray | None), target_response (np.ndarray | None), anchor_response (np.ndarray | None), x_frequencies_hz (np.ndarray | None), x_psd_px2_per_hz (np.ndarray | None), y_frequencies_hz (np.ndarray | None), y_psd_px2_per_hz (np.ndarray | None).
   - save_npz(filepath: str | Path) -> None:
     - Validate input arrays, cast to float64, and save using numpy.savez_compressed to the destination path.
     - Create parent directories automatically if missing.
   - @classmethod load_npz(filepath: str | Path) -> RunArrays:
     - Load using numpy.load(filepath) inside a context manager to prevent dangling file handles.
     - Construct and return RunArrays instance handling optional arrays gracefully.

2. Implement array persistence methods on StorageManager:
   - save_run_arrays(run_id: str, arrays: RunArrays) -> str:
     - Save to self.storage_root / "npz" / "runs" / f"{run_id}.npz".
     - Return relative POSIX path: f"npz/runs/{run_id}.npz".
   - load_run_arrays(run_id_or_rel_path: str) -> RunArrays:
     - Resolve relative or ID path against self.storage_root and load using RunArrays.load_npz.
     - Raise FileNotFoundError with clear diagnostic message if file does not exist.
   - save_baseline_arrays(baseline_id: str, arrays: RunArrays | dict[str, np.ndarray]) -> str:
     - Save reference spectra arrays to self.storage_root / "npz" / "baselines" / f"{baseline_id}.npz" using numpy.savez_compressed.
     - Return relative POSIX path: f"npz/baselines/{baseline_id}.npz".
   - load_baseline_arrays(baseline_id_or_rel_path: str) -> dict[str, np.ndarray]:
     - Resolve path and load array dictionary.

3. Implement evidence image persistence methods on StorageManager:
   - save_evidence_image(event_id: str, image_data: bytes | np.ndarray | Path) -> str:
     - Save image as PNG to self.storage_root / "evidence" / f"{event_id}.png".
     - If bytes: write directly. If Path: copy or read/write. If np.ndarray: save as PNG using PIL/matplotlib or OpenCV if available, or write PNG buffer.
     - Return relative POSIX path: f"evidence/{event_id}.png".
   - get_evidence_image_path(event_id_or_rel_path: str) -> Path:
     - Resolve absolute Path against self.storage_root.
   - resolve_path(rel_path: str) -> Path:
     - Resolve relative path safely against self.storage_root, preventing directory traversal attacks.
  </action>
  <verify>
    <automated>.venv/bin/python -c "import numpy as np; from phasesight.storage import StorageManager, RunArrays; sm = StorageManager(db_path=':memory:'); arr = RunArrays(timestamps_s=np.linspace(0, 10, 600), relative_dx_px=np.zeros(600), relative_dy_px=np.zeros(600)); rel = sm.save_run_arrays('test_run', arr); loaded = sm.load_run_arrays(rel); assert len(loaded.timestamps_s) == 600; sm.close(); print('Task 2 NPZ verified') status=OK"</automated>
  </verify>
  <done>
RunArrays saves and loads compressed NPZ bundles with lossless float64 precision and sub-5ms speed; StorageManager handles relative path resolution and evidence PNG persistence.
  </done>
</task>

<task type="auto">
  <name>Task 3: Complete Relational CRUD Operations & Foreign Key Cascades</name>
  <files>phasesight/storage.py</files>
  <action>
Implement complete CRUD operations for Assets, Baselines, Inspection Runs, and Review Events in phasesight/storage.py per D-01, D-02, D-05, PERSIST-01, PERSIST-02, PERSIST-03, PERSIST-04, and PERSIST-06.

Wrap all SQL operations inside with self._lock: and use parameterized queries (? placeholders) exclusively.

1. Asset Operations:
   - create_asset(name: str, target_roi: dict | ROI, anchor_roi: dict | ROI, expected_fps: float = 60.0, description: str = "", nominal_speed_rpm: float | None = None, scale_calibration: dict | None = None, asset_id: str | None = None) -> AssetRecord:
     - Generate asset_id via uuid.uuid4().hex[:12] if not provided.
     - Serialize ROIs and calibration to JSON.
     - Insert into assets; raise ValueError if asset_id already exists.
   - get_asset(asset_id: str) -> AssetRecord | None: Query by asset_id and deserialize.
   - list_assets() -> list[AssetRecord]: Return all assets ordered by name.
   - update_asset(asset_id: str, **kwargs) -> AssetRecord: Update specified fields, update updated_at timestamp, and return updated record.
   - delete_asset(asset_id: str, delete_files: bool = True) -> bool:
     - If delete_files is True, retrieve all NPZ and evidence paths linked to this asset's baselines, runs, and review events before deletion.
     - Execute DELETE FROM assets WHERE asset_id = ?; (Foreign key cascades will delete child records in baselines, inspection_runs, and review_events).
     - Unlink all retrieved NPZ and evidence files from disk.

2. Baseline Operations:
   - create_baseline(asset_id: str, baseline_record: BaselineRecord, camera_settings: dict | None = None, arrays: RunArrays | None = None, notes: str = "", baseline_id: str | None = None) -> StoredBaseline:
     - Generate baseline_id if None.
     - If arrays provided, save via save_baseline_arrays and store npz_rel_path.
     - Serialize baseline_record via baseline_record.to_dict() / json.dumps.
     - Insert into baselines; return StoredBaseline.
   - get_baseline(baseline_id: str) -> StoredBaseline | None: Query and deserialize.
   - get_latest_baseline_for_asset(asset_id: str) -> StoredBaseline | None: Query ORDER BY created_at DESC LIMIT 1.
   - list_baselines_for_asset(asset_id: str) -> list[StoredBaseline]: Query ORDER BY created_at DESC.
   - delete_baseline(baseline_id: str, delete_files: bool = True) -> bool:
     - Retrieve npz_rel_path, execute DELETE FROM baselines WHERE baseline_id = ?;.
     - Associated inspection_runs have baseline_id set to NULL via ON DELETE SET NULL.
     - If delete_files is True and npz_rel_path exists, unlink file.

3. Inspection Run Operations:
   - create_inspection_run(asset_id: str, video_path: str | Path, measured_fps: float, duration_s: float, frames_analysed: int, summary: dict, baseline_id: str | None = None, arrays: RunArrays | None = None, valid_patch_ratio: float = 1.0, status: str = "Unassessed", run_id: str | None = None) -> InspectionRunRecord:
     - Validate status in ('Normal', 'Review', 'Low confidence', 'Unassessed').
     - If arrays provided, save via save_run_arrays and store npz_rel_path.
     - Insert into inspection_runs; return InspectionRunRecord.
   - get_inspection_run(run_id: str) -> InspectionRunRecord | None.
   - list_inspection_runs(asset_id: str | None = None, limit: int = 50) -> list[InspectionRunRecord]: Query ordered by timestamp DESC.
   - update_inspection_run_status(run_id: str, status: str) -> bool: Validate status and update.
   - delete_inspection_run(run_id: str, delete_files: bool = True) -> bool:
     - Cascade delete reviews; delete NPZ and evidence files if delete_files=True.

4. Review Event Operations:
   - create_review_event(run_id: str, status: str, triggered_features: list[str] | None = None, operator_note: str = "", evidence_image: bytes | np.ndarray | Path | None = None, evaluation: BaselineEvaluation | None = None, operator_id: str = "operator", event_id: str | None = None) -> ReviewEventRecord:
     - Validate status in ('Normal', 'Review', 'Low confidence').
     - If evidence_image provided, save via save_evidence_image and store path.
     - Insert into review_events and update parent inspection run status to match event status.
   - get_review_event(event_id: str) -> ReviewEventRecord | None.
   - list_review_events_for_run(run_id: str) -> list[ReviewEventRecord].
   - delete_review_event(event_id: str, delete_files: bool = True) -> bool.
  </action>
  <verify>
    <automated>.venv/bin/python -c "from phasesight.storage import StorageManager; sm = StorageManager(db_path=':memory:'); a = sm.create_asset('Motor A', {'x': 10, 'y': 10, 'width': 30, 'height': 30}, {'x': 50, 'y': 50, 'width': 30, 'height': 30}); assert sm.get_asset(a.asset_id).name == 'Motor A'; assert sm.delete_asset(a.asset_id); assert sm.get_asset(a.asset_id) is None; sm.close(); print('Task 3 CRUD verified') status=OK"</automated>
  </verify>
  <done>
Complete CRUD methods for Assets, Baselines, Runs, and Review Events implemented with parameterized SQL queries, foreign key enforcement, and optional file cleanup.
  </done>
</task>

<task type="tdd">
  <name>Task 4: Comprehensive Test Suite in tests/test_storage.py</name>
  <files>tests/test_storage.py</files>
  <behavior>
    - test_asset_crud_and_duplicates: Create, read, list, update, and delete assets; duplicate asset_id raises ValueError (PERSIST-01).
    - test_roi_dataclass_roundtrip: AssetRecord target_roi_obj() and anchor_roi_obj() return valid phasesight.tracker.ROI instances (PERSIST-01, D-07).
    - test_baseline_persistence_and_latest: Save BaselineRecord, query by ID, and query get_latest_baseline_for_asset (PERSIST-02).
    - test_inspection_run_archival_and_status: Ingest inspection run, verify default status 'Unassessed', update status to 'Review' (PERSIST-03).
    - test_review_event_logging_and_constraints: Create review event with BaselineEvaluation, verify invalid status raises ValueError (PERSIST-04).
    - test_run_arrays_npz_fidelity_and_compression: Save and load RunArrays with 600 points; verify float64 precision and compression < 25 KB (PERSIST-05).
    - test_npz_missing_optional_arrays: Save and load RunArrays when optional PSD or response arrays are None (PERSIST-05).
    - test_foreign_key_cascades_asset_deletion: Deleting an asset automatically deletes associated baselines, inspection runs, and review events (PERSIST-06, D-05).
    - test_foreign_key_set_null_baseline_deletion: Deleting a baseline sets baseline_id to NULL on associated inspection runs without deleting the runs (PERSIST-06).
    - test_foreign_key_cascades_run_deletion: Deleting an inspection run automatically deletes associated review events (PERSIST-06).
    - test_file_cleanup_on_record_deletion: When delete_files=True, deleting assets or runs unlinks NPZ and evidence PNG files from disk (D-01).
    - test_in_memory_isolation_and_tempdir: Using db_path=':memory:' works without disk side effects and cleans up temporary files on close (D-04).
    - test_thread_concurrency_safety: 10 concurrent worker threads executing reads and writes concurrently succeed without sqlite3.InterfaceError (PERSIST-06).
    - test_schema_migration_idempotence: Calling init_schema multiple times maintains user_version = 1 and does not alter existing data (PERSIST-06).
    - test_path_traversal_prevention: Attempting relative path traversal (e.g., ../../secret) in resolve_path raises ValueError (PERSIST-06).
  </behavior>
  <action>
Create tests/test_storage.py implementing all 15 test scenarios specified above per PERSIST-01, PERSIST-02, PERSIST-03, PERSIST-04, PERSIST-05, and PERSIST-06.

1. Construct pytest fixtures:
   - storage_memory: Yields StorageManager(db_path=":memory:") and closes it after test.
   - storage_temp(tmp_path): Yields StorageManager(storage_root=tmp_path) and closes it.
   - sample_baseline_record: Helper returning a valid BaselineRecord from phasesight.baseline.
   - sample_run_arrays: Helper returning RunArrays with realistic 600-frame time series and 256-point PSD arrays.
   - sample_inspection_summary: Helper returning inspection summary dict matching phasesight.video output.

2. Implement test methods asserting:
   - Asset CRUD, ROI round-trips, duplicate asset_id rejection.
   - Baseline storage, JSON round-tripping with native floats, latest baseline lookup.
   - Inspection run archival, status transitions, summary JSON fidelity.
   - Review event logging with BaselineEvaluation and valid status enum checks.
   - Compressed NPZ array storage with dtype/shape integrity.
   - Foreign key cascade deletions and ON DELETE SET NULL behavior.
   - Physical file cleanup when delete_files=True vs retention when delete_files=False.
   - Thread safety with concurrent ThreadPoolExecutor workers.
   - In-memory isolation and temporary directory cleanup.

3. Run pytest to verify all tests pass cleanly.
  </action>
  <verify>
    <automated>.venv/bin/pytest tests/test_storage.py -v</automated>
  </verify>
  <done>
All 15+ unit tests in tests/test_storage.py pass cleanly with 100% assertion pass rate.
  </done>
</task>

<task type="auto">
  <name>Task 5: CLI Integration & Storage Administration Subcommands</name>
  <files>phasesight/cli.py</files>
  <action>
Extend phasesight/cli.py with storage management and administrative subcommands per PERSIST-01, PERSIST-06, D-01, and D-04.

1. In _build_parser():
   - Add db-info parser:
     - --storage-root: Path, default None (uses default or PHASESIGHT_STORAGE_ROOT).
     - --json: bool flag to output raw JSON metadata.
   - Add asset parser with subparsers (create, list, show):
     - create subparser:
       - name: str, positional required.
       - --target: str, required ("x,y,w,h").
       - --anchor: str, required ("x,y,w,h").
       - --fps: float, default 60.0.
       - --speed: float, default None (nominal RPM).
       - --desc: str, default "".
       - --asset-id: str, default None.
     - list subparser:
       - --storage-root: Path, default None.
       - --json: bool flag.
     - show subparser:
       - asset_id: str, positional required.
       - --storage-root: Path, default None.

2. In main():
   - Implement db-info handler:
     - Instantiate StorageManager, call get_db_info().
     - If --json: output json.dumps(info, indent=2).
     - Else: print formatted terminal table showing Database Path, Storage Root, SQLite Version, Schema Version, Foreign Keys (ENABLED), Asset Count, Baseline Count, Run Count, and Review Event Count.
   - Implement asset create handler:
     - Parse ROIs with parse_roi from phasesight.video.
     - Create asset via sm.create_asset().
     - Print confirmation banner with created asset_id, name, and ROIs.
   - Implement asset list handler:
     - Fetch all assets via sm.list_assets().
     - Display formatted table with columns: ID, Name, Expected FPS, Nominal RPM, Updated At.
   - Implement asset show handler:
     - Fetch asset by ID, display full details including target/anchor ROIs, baselines count, and recent inspection runs count.
  </action>
  <verify>
    <automated>.venv/bin/python -m phasesight.cli --help && .venv/bin/python -m phasesight.cli db-info --help && .venv/bin/python -m phasesight.cli asset --help && .venv/bin/python -m phasesight.cli db-info</automated>
  </verify>
  <done>
CLI subcommands db-info and asset (create, list, show) are registered, parse arguments correctly, execute database operations via StorageManager, and print formatted terminal tables.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| File System / SQL Engine | Untrusted or malformed input parameters passed into SQLite queries. |
| Filesystem Paths / NPZ & Evidence | User-supplied or database-stored paths used to write or load files on disk. |
| Multi-threaded Streamlit Access | Concurrent background execution threads in Streamlit accessing a shared SQLite connection. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-04-01 | Tampering / SQL Injection | `phasesight/storage.py:StorageManager` | high | mitigate | Mandate parameterized SQL queries (`?` placeholders) for all SELECT, INSERT, UPDATE, and DELETE operations. Prohibit f-strings or manual string formatting in SQL statements. |
| T-04-02 | Tampering / Elevation of Privilege | `phasesight/storage.py:resolve_path` | high | mitigate | Validate all relative file paths against `storage_root` using `Path.resolve()`; reject any path containing `..` or attempting directory traversal outside `storage_root`. |
| T-04-03 | Denial of Service / Concurrency Crash | `phasesight/storage.py:StorageManager` | medium | mitigate | Synchronize all database cursor executions and transactions using a reentrant lock (`threading.RLock()`), preventing SQLite interface misuse errors during concurrent Streamlit worker calls. |
| T-04-04 | Repudiation / Data Corruption | `phasesight/storage.py:create_connection` | high | mitigate | Enforce `PRAGMA foreign_keys = ON;` on every SQLite connection, and enable WAL journal mode (`PRAGMA journal_mode = WAL;`) for atomic crash-resilient transactions. |
| T-04-SC | Tampering | Python dependencies | high | mitigate | Standard stack uses Python standard library `sqlite3` and existing `numpy>=1.26` from `pyproject.toml`. No new external third-party dependencies are introduced. |
</threat_model>

<verification>
Automated verification commands:
1. Dataclasses & SQLite Schema: `.venv/bin/python -c "from phasesight.storage import StorageManager; sm = StorageManager(db_path=':memory:'); print(sm.get_db_info()); sm.close()"`
2. NPZ Array Roundtrip: `.venv/bin/python -c "import numpy as np; from phasesight.storage import RunArrays; a = RunArrays(timestamps_s=np.array([0.1, 0.2]), relative_dx_px=np.array([0.01, 0.02]), relative_dy_px=np.array([0.0, 0.0])); print('RunArrays verified')"`
3. Unit Test Suite: `.venv/bin/pytest tests/test_storage.py -v` (15+ passing tests)
4. CLI Commands: `.venv/bin/python -m phasesight.cli db-info && .venv/bin/python -m phasesight.cli asset --help`
5. Full Regression Suite: `.venv/bin/pytest -v` (55+ passing tests across entire codebase)
</verification>

<success_criteria>
1. `phasesight/storage.py` exists with complete implementations of `AssetRecord`, `StoredBaseline`, `InspectionRunRecord`, `ReviewEventRecord`, `RunArrays`, and `StorageManager`.
2. SQLite database initializes with `PRAGMA foreign_keys = ON;`, `PRAGMA journal_mode = WAL;`, and idempotent schema migrations (`PRAGMA user_version = 1`).
3. Complete CRUD operations and foreign key cascade deletions are implemented for Assets, Baselines, Inspection Runs, and Review Events.
4. `RunArrays` persists numerical time series and PSD arrays to compressed NPZ files with sub-5ms latency and full float64 fidelity.
5. All 15+ unit tests in `tests/test_storage.py` pass cleanly.
6. CLI subcommands `db-info` and `asset` (create, list, show) operate seamlessly from the terminal.
7. Existing 40 tests across `tests/test_tracker.py`, `tests/test_analysis.py`, `tests/test_baseline.py`, and `tests/test_ui.py` continue to pass with zero regressions.
8. Non-negotiable technical boundaries (pixel domain only, local-first architecture, no external database daemons) are strictly upheld throughout.
</success_criteria>

<output>
Create `.planning/phases/04-local-persistence/04-01-SUMMARY.md` when execution is complete.
</output>
