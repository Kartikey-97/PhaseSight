"""Local persistence layer for PhaseSight.

Combines an embedded SQLite database (phasesight.db) for relational metadata,
asset definitions, baseline statistics, run records, and review events with
high-performance compressed NumPy NPZ files for raw displacement and PSD
spectral arrays.
"""

from __future__ import annotations

import datetime
from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import threading
from typing import Any
import uuid

import numpy as np

from phasesight.baseline import (
    BaselineEvaluation,
    BaselineRecord,
    deserialize_baseline,
    serialize_baseline,
)
from phasesight.tracker import ROI

# Valid status values for runs and review events
VALID_RUN_STATUSES = ("Normal", "Review", "Low confidence", "Unassessed")
VALID_REVIEW_STATUSES = ("Normal", "Review", "Low confidence")


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Data Models / Dataclasses
# ---------------------------------------------------------------------------

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

    def target_roi_obj(self) -> ROI:
        """Convert target ROI dictionary to ROI dataclass."""
        return ROI(
            x=int(self.target_roi["x"]),
            y=int(self.target_roi["y"]),
            width=int(self.target_roi["width"]),
            height=int(self.target_roi["height"]),
        )

    def anchor_roi_obj(self) -> ROI:
        """Convert anchor ROI dictionary to ROI dataclass."""
        return ROI(
            x=int(self.anchor_roi["x"]),
            y=int(self.anchor_roi["y"]),
            width=int(self.anchor_roi["width"]),
            height=int(self.anchor_roi["height"]),
        )

    def to_dict(self) -> dict[str, Any]:
        """Convert record to JSON-compatible dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssetRecord:
        """Construct record from dictionary."""
        return cls(
            asset_id=str(data["asset_id"]),
            name=str(data["name"]),
            description=str(data.get("description", "")),
            nominal_speed_rpm=(
                float(data["nominal_speed_rpm"])
                if data.get("nominal_speed_rpm") is not None
                else None
            ),
            target_roi=dict(data.get("target_roi", {})),
            anchor_roi=dict(data.get("anchor_roi", {})),
            expected_fps=float(data.get("expected_fps", 60.0)),
            scale_calibration=data.get("scale_calibration"),
            created_at=str(data.get("created_at", _utc_now_iso())),
            updated_at=str(data.get("updated_at", _utc_now_iso())),
        )


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

    def to_dict(self) -> dict[str, Any]:
        """Convert stored baseline to JSON-compatible dictionary."""
        return {
            "baseline_id": self.baseline_id,
            "asset_id": self.asset_id,
            "created_at": self.created_at,
            "run_count": self.run_count,
            "baseline_record": self.baseline_record.to_dict(),
            "camera_settings": self.camera_settings,
            "npz_rel_path": self.npz_rel_path,
            "notes": self.notes,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StoredBaseline:
        """Construct stored baseline from dictionary."""
        rec_data = data["baseline_record"]
        if isinstance(rec_data, BaselineRecord):
            record = rec_data
        elif isinstance(rec_data, str):
            record = deserialize_baseline(rec_data)
        else:
            record = BaselineRecord.from_dict(rec_data)

        return cls(
            baseline_id=str(data["baseline_id"]),
            asset_id=str(data["asset_id"]),
            created_at=str(data["created_at"]),
            run_count=int(data["run_count"]),
            baseline_record=record,
            camera_settings=dict(data.get("camera_settings", {})),
            npz_rel_path=data.get("npz_rel_path"),
            notes=str(data.get("notes", "")),
            version=str(data.get("version", "1.0")),
        )


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

    def __post_init__(self) -> None:
        if self.status not in VALID_RUN_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of {VALID_RUN_STATUSES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert inspection run to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> InspectionRunRecord:
        """Construct inspection run from dictionary."""
        return cls(
            run_id=str(data["run_id"]),
            asset_id=str(data["asset_id"]),
            timestamp=str(data["timestamp"]),
            video_path=str(data["video_path"]),
            measured_fps=float(data["measured_fps"]),
            duration_s=float(data["duration_s"]),
            frames_analysed=int(data["frames_analysed"]),
            valid_patch_ratio=float(data.get("valid_patch_ratio", 1.0)),
            summary=dict(data.get("summary", {})),
            baseline_id=data.get("baseline_id"),
            npz_rel_path=data.get("npz_rel_path"),
            status=str(data.get("status", "Unassessed")),
        )


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

    def __post_init__(self) -> None:
        if self.status not in VALID_REVIEW_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of {VALID_REVIEW_STATUSES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert review event to dictionary."""
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "status": self.status,
            "triggered_features": list(self.triggered_features),
            "operator_note": self.operator_note,
            "evidence_image_rel_path": self.evidence_image_rel_path,
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "created_at": self.created_at,
            "operator_id": self.operator_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewEventRecord:
        """Construct review event from dictionary."""
        eval_data = data.get("evaluation")
        evaluation = None
        if eval_data is not None:
            if isinstance(eval_data, BaselineEvaluation):
                evaluation = eval_data
            elif isinstance(eval_data, str):
                evaluation = BaselineEvaluation.from_dict(json.loads(eval_data))
            elif isinstance(eval_data, dict):
                evaluation = BaselineEvaluation.from_dict(eval_data)

        return cls(
            event_id=str(data["event_id"]),
            run_id=str(data["run_id"]),
            status=str(data["status"]),
            triggered_features=list(data.get("triggered_features", [])),
            operator_note=str(data.get("operator_note", "")),
            evidence_image_rel_path=data.get("evidence_image_rel_path"),
            evaluation=evaluation,
            created_at=str(data.get("created_at", _utc_now_iso())),
            operator_id=str(data.get("operator_id", "operator")),
        )


@dataclass
class RunArrays:
    """Numerical time series and Welch PSD arrays."""

    timestamps_s: np.ndarray
    relative_dx_px: np.ndarray
    relative_dy_px: np.ndarray
    target_dx_px: np.ndarray | None = None
    target_dy_px: np.ndarray | None = None
    anchor_dx_px: np.ndarray | None = None
    anchor_dy_px: np.ndarray | None = None
    target_response: np.ndarray | None = None
    anchor_response: np.ndarray | None = None
    x_frequencies_hz: np.ndarray | None = None
    x_psd_px2_per_hz: np.ndarray | None = None
    y_frequencies_hz: np.ndarray | None = None
    y_psd_px2_per_hz: np.ndarray | None = None

    def save_npz(self, filepath: str | Path) -> None:
        """Save arrays using compressed NumPy NPZ format."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, np.ndarray] = {
            "timestamps_s": np.asarray(self.timestamps_s, dtype=np.float64),
            "relative_dx_px": np.asarray(self.relative_dx_px, dtype=np.float64),
            "relative_dy_px": np.asarray(self.relative_dy_px, dtype=np.float64),
        }
        if self.target_dx_px is not None:
            payload["target_dx_px"] = np.asarray(self.target_dx_px, dtype=np.float64)
        if self.target_dy_px is not None:
            payload["target_dy_px"] = np.asarray(self.target_dy_px, dtype=np.float64)
        if self.anchor_dx_px is not None:
            payload["anchor_dx_px"] = np.asarray(self.anchor_dx_px, dtype=np.float64)
        if self.anchor_dy_px is not None:
            payload["anchor_dy_px"] = np.asarray(self.anchor_dy_px, dtype=np.float64)
        if self.target_response is not None:
            payload["target_response"] = np.asarray(self.target_response, dtype=np.float64)
        if self.anchor_response is not None:
            payload["anchor_response"] = np.asarray(self.anchor_response, dtype=np.float64)
        if self.x_frequencies_hz is not None:
            payload["x_frequencies_hz"] = np.asarray(self.x_frequencies_hz, dtype=np.float64)
        if self.x_psd_px2_per_hz is not None:
            payload["x_psd_px2_per_hz"] = np.asarray(self.x_psd_px2_per_hz, dtype=np.float64)
        if self.y_frequencies_hz is not None:
            payload["y_frequencies_hz"] = np.asarray(self.y_frequencies_hz, dtype=np.float64)
        if self.y_psd_px2_per_hz is not None:
            payload["y_psd_px2_per_hz"] = np.asarray(self.y_psd_px2_per_hz, dtype=np.float64)

        np.savez_compressed(path, **payload)

    @classmethod
    def load_npz(cls, filepath: str | Path) -> RunArrays:
        """Load arrays from compressed NumPy NPZ file."""
        path = Path(filepath)
        if not path.is_file():
            raise FileNotFoundError(f"Run arrays file not found: {path}")

        with np.load(path) as data:
            return cls(
                timestamps_s=data["timestamps_s"],
                relative_dx_px=data["relative_dx_px"],
                relative_dy_px=data["relative_dy_px"],
                target_dx_px=data["target_dx_px"] if "target_dx_px" in data else None,
                target_dy_px=data["target_dy_px"] if "target_dy_px" in data else None,
                anchor_dx_px=data["anchor_dx_px"] if "anchor_dx_px" in data else None,
                anchor_dy_px=data["anchor_dy_px"] if "anchor_dy_px" in data else None,
                target_response=data["target_response"] if "target_response" in data else None,
                anchor_response=data["anchor_response"] if "anchor_response" in data else None,
                x_frequencies_hz=data["x_frequencies_hz"] if "x_frequencies_hz" in data else None,
                x_psd_px2_per_hz=data["x_psd_px2_per_hz"] if "x_psd_px2_per_hz" in data else None,
                y_frequencies_hz=data["y_frequencies_hz"] if "y_frequencies_hz" in data else None,
                y_psd_px2_per_hz=data["y_psd_px2_per_hz"] if "y_psd_px2_per_hz" in data else None,
            )


# ---------------------------------------------------------------------------
# Database Initialization & Pragmas
# ---------------------------------------------------------------------------

def create_connection(db_path: str | Path) -> sqlite3.Connection:
    """Create SQLite connection with required pragmas enabled.

    Enforces foreign keys, row factory, and WAL journal mode (if file-backed).
    """
    path_str = str(db_path)
    conn = sqlite3.connect(path_str, check_same_thread=False)
    conn.row_factory = sqlite3.Row

    # Always enforce foreign keys
    conn.execute("PRAGMA foreign_keys = ON;")

    # If file-backed, enable WAL and normal synchronous mode
    if path_str != ":memory:":
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")

    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Initialize database schema idempotently using user_version tracking."""
    cur = conn.cursor()
    cur.execute("PRAGMA user_version;")
    row = cur.fetchone()
    current_version = row[0] if row else 0

    if current_version < 1:
        # Create core tables
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS assets (
                asset_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                nominal_speed_rpm REAL,
                target_roi_json TEXT NOT NULL,
                anchor_roi_json TEXT NOT NULL,
                expected_fps REAL NOT NULL CHECK (expected_fps > 0),
                scale_calibration_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS baselines (
                baseline_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                created_at TEXT NOT NULL,
                run_count INTEGER NOT NULL CHECK (run_count >= 1),
                camera_settings_json TEXT NOT NULL DEFAULT '{}',
                baseline_record_json TEXT NOT NULL,
                npz_rel_path TEXT,
                notes TEXT NOT NULL DEFAULT '',
                version TEXT NOT NULL DEFAULT '1.0'
            );

            CREATE TABLE IF NOT EXISTS inspection_runs (
                run_id TEXT PRIMARY KEY,
                asset_id TEXT NOT NULL REFERENCES assets(asset_id) ON DELETE CASCADE,
                baseline_id TEXT REFERENCES baselines(baseline_id) ON DELETE SET NULL,
                timestamp TEXT NOT NULL,
                video_path TEXT NOT NULL,
                measured_fps REAL NOT NULL CHECK (measured_fps > 0),
                duration_s REAL NOT NULL CHECK (duration_s >= 0),
                frames_analysed INTEGER NOT NULL CHECK (frames_analysed >= 0),
                valid_patch_ratio REAL NOT NULL DEFAULT 1.0,
                npz_rel_path TEXT,
                summary_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'Unassessed'
            );

            CREATE TABLE IF NOT EXISTS review_events (
                event_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL REFERENCES inspection_runs(run_id) ON DELETE CASCADE,
                status TEXT NOT NULL CHECK (status IN ('Normal', 'Review', 'Low confidence')),
                triggered_features_json TEXT NOT NULL DEFAULT '[]',
                operator_note TEXT NOT NULL DEFAULT '',
                evidence_image_rel_path TEXT,
                evaluation_json TEXT,
                created_at TEXT NOT NULL,
                operator_id TEXT NOT NULL DEFAULT 'operator'
            );

            CREATE INDEX IF NOT EXISTS idx_baselines_asset_id ON baselines(asset_id);
            CREATE INDEX IF NOT EXISTS idx_runs_asset_id ON inspection_runs(asset_id);
            CREATE INDEX IF NOT EXISTS idx_runs_timestamp ON inspection_runs(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_runs_baseline_id ON inspection_runs(baseline_id);
            CREATE INDEX IF NOT EXISTS idx_review_events_run_id ON review_events(run_id);
            CREATE INDEX IF NOT EXISTS idx_review_events_created_at ON review_events(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_review_events_status ON review_events(status);

            PRAGMA user_version = 1;
            """
        )
        conn.commit()


# ---------------------------------------------------------------------------
# StorageManager
# ---------------------------------------------------------------------------

class StorageManager:
    """Manages local persistence of PhaseSight assets, baselines, runs, and arrays."""

    def __init__(
        self,
        storage_root: str | Path | None = None,
        db_path: str | Path | None = None,
    ) -> None:
        """Initialize StorageManager.

        Parameters
        ----------
        storage_root : str | Path | None
            Root folder for NPZ arrays and evidence files. Defaults to
            PHASESIGHT_STORAGE_ROOT environment variable or 'data/storage'.
        db_path : str | Path | None
            SQLite database path. Defaults to storage_root / 'phasesight.db',
            or ':memory:' for isolated in-memory execution.
        """
        self._temp_dir: tempfile.TemporaryDirectory | None = None

        if db_path == ":memory:":
            self.db_path: str | Path = ":memory:"
            if storage_root is None:
                self._temp_dir = tempfile.TemporaryDirectory()
                self.storage_root = Path(self._temp_dir.name)
            else:
                self.storage_root = Path(storage_root)
        else:
            if storage_root is None:
                env_root = os.environ.get("PHASESIGHT_STORAGE_ROOT", "data/storage")
                self.storage_root = Path(env_root)
            else:
                self.storage_root = Path(storage_root)

            if db_path is None:
                self.db_path = self.storage_root / "phasesight.db"
            else:
                self.db_path = Path(db_path)

        self._lock = threading.RLock()

        # Ensure directory structure exists
        self.storage_root.mkdir(parents=True, exist_ok=True)
        (self.storage_root / "npz" / "runs").mkdir(parents=True, exist_ok=True)
        (self.storage_root / "npz" / "baselines").mkdir(parents=True, exist_ok=True)
        (self.storage_root / "evidence").mkdir(parents=True, exist_ok=True)

        self._conn = create_connection(self.db_path)
        with self._lock:
            init_schema(self._conn)

    def close(self) -> None:
        """Close SQLite database and clean up temporary resources."""
        with self._lock:
            if self._conn:
                self._conn.close()
        if self._temp_dir is not None:
            self._temp_dir.cleanup()

    def __enter__(self) -> StorageManager:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def get_db_info(self) -> dict[str, Any]:
        """Return diagnostic information about the database and storage."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute("PRAGMA user_version;")
            schema_ver = cur.fetchone()[0]

            cur.execute("PRAGMA foreign_keys;")
            fk_enabled = cur.fetchone()[0]

            cur.execute("SELECT sqlite_version();")
            sqlite_ver = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM assets;")
            asset_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM baselines;")
            baseline_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM inspection_runs;")
            run_count = cur.fetchone()[0]

            cur.execute("SELECT count(*) FROM review_events;")
            review_count = cur.fetchone()[0]

        return {
            "schema_version": int(schema_ver),
            "foreign_keys": int(fk_enabled),
            "sqlite_version": str(sqlite_ver),
            "db_path": str(self.db_path),
            "storage_root": str(self.storage_root),
            "asset_count": int(asset_count),
            "baseline_count": int(baseline_count),
            "run_count": int(run_count),
            "review_count": int(review_count),
        }

    # -----------------------------------------------------------------------
    # Path Security & Resolution
    # -----------------------------------------------------------------------

    def resolve_path(self, rel_path: str | Path) -> Path:
        """Resolve a relative path against storage_root with traversal protection."""
        path_str = str(rel_path).strip()
        if ".." in Path(path_str).parts:
            raise ValueError(f"Path traversal detected: {rel_path}")

        resolved = (self.storage_root / path_str).resolve()
        root_resolved = self.storage_root.resolve()
        try:
            resolved.relative_to(root_resolved)
        except ValueError as exc:
            raise ValueError(f"Path outside storage root: {rel_path}") from exc

        return resolved

    # -----------------------------------------------------------------------
    # NPZ Array & Evidence Persistence
    # -----------------------------------------------------------------------

    def save_run_arrays(self, run_id: str, arrays: RunArrays) -> str:
        """Save run displacement and PSD arrays to compressed NPZ."""
        rel_posix = f"npz/runs/{run_id}.npz"
        abs_path = self.resolve_path(rel_posix)
        arrays.save_npz(abs_path)
        return rel_posix

    def load_run_arrays(self, run_id_or_rel_path: str) -> RunArrays:
        """Load run arrays given run_id or relative NPZ path."""
        if not run_id_or_rel_path.endswith(".npz"):
            rel_posix = f"npz/runs/{run_id_or_rel_path}.npz"
        else:
            rel_posix = run_id_or_rel_path

        abs_path = self.resolve_path(rel_posix)
        return RunArrays.load_npz(abs_path)

    def save_baseline_arrays(
        self, baseline_id: str, arrays: RunArrays | dict[str, np.ndarray]
    ) -> str:
        """Save baseline spectral or reference arrays to compressed NPZ."""
        rel_posix = f"npz/baselines/{baseline_id}.npz"
        abs_path = self.resolve_path(rel_posix)

        if isinstance(arrays, RunArrays):
            arrays.save_npz(abs_path)
        else:
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(abs_path, **arrays)

        return rel_posix

    def load_baseline_arrays(
        self, baseline_id_or_rel_path: str
    ) -> dict[str, np.ndarray]:
        """Load baseline arrays from compressed NPZ."""
        if not baseline_id_or_rel_path.endswith(".npz"):
            rel_posix = f"npz/baselines/{baseline_id_or_rel_path}.npz"
        else:
            rel_posix = baseline_id_or_rel_path

        abs_path = self.resolve_path(rel_posix)
        if not abs_path.is_file():
            raise FileNotFoundError(f"Baseline arrays file not found: {abs_path}")

        with np.load(abs_path) as data:
            return {k: data[k] for k in data.files}

    def save_evidence_image(
        self, event_id: str, image_data: bytes | np.ndarray | Path | str
    ) -> str:
        """Save evidence frame or plot image as PNG."""
        rel_posix = f"evidence/{event_id}.png"
        abs_path = self.resolve_path(rel_posix)
        abs_path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(image_data, bytes):
            abs_path.write_bytes(image_data)
        elif isinstance(image_data, (Path, str)):
            source_path = Path(image_data)
            if not source_path.is_file():
                raise FileNotFoundError(f"Source evidence image not found: {source_path}")
            shutil.copy2(source_path, abs_path)
        elif isinstance(image_data, np.ndarray):
            import cv2  # Optional import inside method
            cv2.imwrite(str(abs_path), image_data)
        else:
            raise TypeError(f"Unsupported image_data type: {type(image_data)}")

        return rel_posix

    def get_evidence_image_path(self, event_id_or_rel_path: str) -> Path:
        """Get absolute path to evidence PNG."""
        if not event_id_or_rel_path.endswith(".png"):
            rel_posix = f"evidence/{event_id_or_rel_path}.png"
        else:
            rel_posix = event_id_or_rel_path
        return self.resolve_path(rel_posix)

    def load_evidence_image(self, event_id_or_rel_path: str) -> bytes | None:
        """Load evidence PNG bytes if exists."""
        try:
            path = self.get_evidence_image_path(event_id_or_rel_path)
            if path.is_file():
                return path.read_bytes()
        except Exception:
            return None
        return None

    # -----------------------------------------------------------------------
    # Asset CRUD Operations
    # -----------------------------------------------------------------------

    def create_asset(
        self,
        name: str,
        target_roi: dict[str, int] | ROI,
        anchor_roi: dict[str, int] | ROI,
        expected_fps: float = 60.0,
        description: str = "",
        nominal_speed_rpm: float | None = None,
        scale_calibration: dict[str, Any] | None = None,
        asset_id: str | None = None,
    ) -> AssetRecord:
        """Create and store a new machine asset."""
        if not name.strip():
            raise ValueError("Asset name cannot be empty.")
        if expected_fps <= 0:
            raise ValueError("expected_fps must be greater than zero.")

        if isinstance(target_roi, ROI):
            target_roi_dict = {
                "x": int(target_roi.x),
                "y": int(target_roi.y),
                "width": int(target_roi.width),
                "height": int(target_roi.height),
            }
        else:
            target_roi_dict = dict(target_roi)

        if isinstance(anchor_roi, ROI):
            anchor_roi_dict = {
                "x": int(anchor_roi.x),
                "y": int(anchor_roi.y),
                "width": int(anchor_roi.width),
                "height": int(anchor_roi.height),
            }
        else:
            anchor_roi_dict = dict(anchor_roi)

        for key in ("x", "y", "width", "height"):
            if key not in target_roi_dict:
                raise ValueError(f"target_roi missing '{key}' coordinate.")
            if key not in anchor_roi_dict:
                raise ValueError(f"anchor_roi missing '{key}' coordinate.")

        assigned_id = asset_id or f"ast_{uuid.uuid4().hex[:10]}"
        now = _utc_now_iso()

        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM assets WHERE asset_id = ?;", (assigned_id,))
            if cur.fetchone():
                raise ValueError(f"Asset with ID '{assigned_id}' already exists.")

            cur.execute(
                """
                INSERT INTO assets (
                    asset_id, name, description, nominal_speed_rpm,
                    target_roi_json, anchor_roi_json, expected_fps,
                    scale_calibration_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    assigned_id,
                    name.strip(),
                    description.strip(),
                    nominal_speed_rpm,
                    json.dumps(target_roi_dict),
                    json.dumps(anchor_roi_dict),
                    float(expected_fps),
                    json.dumps(scale_calibration) if scale_calibration else None,
                    now,
                    now,
                ),
            )
            self._conn.commit()

        return AssetRecord(
            asset_id=assigned_id,
            name=name.strip(),
            description=description.strip(),
            nominal_speed_rpm=nominal_speed_rpm,
            target_roi=target_roi_dict,
            anchor_roi=anchor_roi_dict,
            expected_fps=float(expected_fps),
            scale_calibration=scale_calibration,
            created_at=now,
            updated_at=now,
        )

    def get_asset(self, asset_id: str) -> AssetRecord | None:
        """Fetch asset by ID."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT asset_id, name, description, nominal_speed_rpm,
                       target_roi_json, anchor_roi_json, expected_fps,
                       scale_calibration_json, created_at, updated_at
                FROM assets WHERE asset_id = ?;
                """,
                (asset_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return AssetRecord(
                asset_id=row["asset_id"],
                name=row["name"],
                description=row["description"],
                nominal_speed_rpm=row["nominal_speed_rpm"],
                target_roi=json.loads(row["target_roi_json"]),
                anchor_roi=json.loads(row["anchor_roi_json"]),
                expected_fps=float(row["expected_fps"]),
                scale_calibration=(
                    json.loads(row["scale_calibration_json"])
                    if row["scale_calibration_json"]
                    else None
                ),
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    def list_assets(self) -> list[AssetRecord]:
        """List all registered assets ordered by name."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT asset_id, name, description, nominal_speed_rpm,
                       target_roi_json, anchor_roi_json, expected_fps,
                       scale_calibration_json, created_at, updated_at
                FROM assets ORDER BY name ASC;
                """
            )
            rows = cur.fetchall()

        results = []
        for row in rows:
            results.append(
                AssetRecord(
                    asset_id=row["asset_id"],
                    name=row["name"],
                    description=row["description"],
                    nominal_speed_rpm=row["nominal_speed_rpm"],
                    target_roi=json.loads(row["target_roi_json"]),
                    anchor_roi=json.loads(row["anchor_roi_json"]),
                    expected_fps=float(row["expected_fps"]),
                    scale_calibration=(
                        json.loads(row["scale_calibration_json"])
                        if row["scale_calibration_json"]
                        else None
                    ),
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )
            )
        return results

    def update_asset(
        self,
        asset_id: str,
        name: str | None = None,
        description: str | None = None,
        nominal_speed_rpm: float | None = None,
        target_roi: dict[str, int] | ROI | None = None,
        anchor_roi: dict[str, int] | ROI | None = None,
        expected_fps: float | None = None,
        scale_calibration: dict[str, Any] | None = None,
    ) -> AssetRecord:
        """Update fields of an existing asset."""
        existing = self.get_asset(asset_id)
        if not existing:
            raise ValueError(f"Asset with ID '{asset_id}' does not exist.")

        new_name = name.strip() if name is not None else existing.name
        new_desc = description.strip() if description is not None else existing.description
        new_speed = nominal_speed_rpm if nominal_speed_rpm is not None else existing.nominal_speed_rpm
        new_fps = float(expected_fps) if expected_fps is not None else existing.expected_fps

        if target_roi is not None:
            if isinstance(target_roi, ROI):
                new_target_roi = {
                    "x": int(target_roi.x),
                    "y": int(target_roi.y),
                    "width": int(target_roi.width),
                    "height": int(target_roi.height),
                }
            else:
                new_target_roi = dict(target_roi)
        else:
            new_target_roi = existing.target_roi

        if anchor_roi is not None:
            if isinstance(anchor_roi, ROI):
                new_anchor_roi = {
                    "x": int(anchor_roi.x),
                    "y": int(anchor_roi.y),
                    "width": int(anchor_roi.width),
                    "height": int(anchor_roi.height),
                }
            else:
                new_anchor_roi = dict(anchor_roi)
        else:
            new_anchor_roi = existing.anchor_roi

        new_scale = scale_calibration if scale_calibration is not None else existing.scale_calibration
        now = _utc_now_iso()

        with self._lock:
            self._conn.execute(
                """
                UPDATE assets
                SET name = ?, description = ?, nominal_speed_rpm = ?,
                    target_roi_json = ?, anchor_roi_json = ?, expected_fps = ?,
                    scale_calibration_json = ?, updated_at = ?
                WHERE asset_id = ?;
                """,
                (
                    new_name,
                    new_desc,
                    new_speed,
                    json.dumps(new_target_roi),
                    json.dumps(new_anchor_roi),
                    new_fps,
                    json.dumps(new_scale) if new_scale else None,
                    now,
                    asset_id,
                ),
            )
            self._conn.commit()

        return AssetRecord(
            asset_id=asset_id,
            name=new_name,
            description=new_desc,
            nominal_speed_rpm=new_speed,
            target_roi=new_target_roi,
            anchor_roi=new_anchor_roi,
            expected_fps=new_fps,
            scale_calibration=new_scale,
            created_at=existing.created_at,
            updated_at=now,
        )

    def delete_asset(self, asset_id: str, delete_files: bool = True) -> bool:
        """Delete asset and optionally all associated files on disk."""
        files_to_delete: list[str] = []

        with self._lock:
            cur = self._conn.cursor()
            cur.execute("SELECT 1 FROM assets WHERE asset_id = ?;", (asset_id,))
            if not cur.fetchone():
                return False

            if delete_files:
                # Collect baseline NPZs
                cur.execute(
                    "SELECT npz_rel_path FROM baselines WHERE asset_id = ? AND npz_rel_path IS NOT NULL;",
                    (asset_id,),
                )
                for r in cur.fetchall():
                    if r[0]:
                        files_to_delete.append(r[0])

                # Collect run NPZs
                cur.execute(
                    "SELECT npz_rel_path FROM inspection_runs WHERE asset_id = ? AND npz_rel_path IS NOT NULL;",
                    (asset_id,),
                )
                for r in cur.fetchall():
                    if r[0]:
                        files_to_delete.append(r[0])

                # Collect review event evidence images
                cur.execute(
                    """
                    SELECT evidence_image_rel_path FROM review_events
                    WHERE run_id IN (SELECT run_id FROM inspection_runs WHERE asset_id = ?)
                    AND evidence_image_rel_path IS NOT NULL;
                    """,
                    (asset_id,),
                )
                for r in cur.fetchall():
                    if r[0]:
                        files_to_delete.append(r[0])

            # Delete asset; cascading foreign keys will delete baselines, runs, review events
            cur.execute("DELETE FROM assets WHERE asset_id = ?;", (asset_id,))
            self._conn.commit()

        if delete_files:
            for rel_path in files_to_delete:
                try:
                    p = self.resolve_path(rel_path)
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass

        return True

    # -----------------------------------------------------------------------
    # Baseline CRUD Operations
    # -----------------------------------------------------------------------

    def create_baseline(
        self,
        asset_id: str,
        baseline_record: BaselineRecord,
        camera_settings: dict[str, Any] | None = None,
        arrays: RunArrays | dict[str, np.ndarray] | None = None,
        notes: str = "",
        baseline_id: str | None = None,
    ) -> StoredBaseline:
        """Store a new statistical baseline for an asset."""
        # Verify asset exists
        if not self.get_asset(asset_id):
            raise ValueError(f"Asset with ID '{asset_id}' does not exist.")

        assigned_id = baseline_id or f"bsl_{uuid.uuid4().hex[:10]}"
        now = _utc_now_iso()
        cam_settings = camera_settings or {}

        npz_rel_path = None
        if arrays is not None:
            npz_rel_path = self.save_baseline_arrays(assigned_id, arrays)

        record_json = serialize_baseline(baseline_record)

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO baselines (
                    baseline_id, asset_id, created_at, run_count,
                    camera_settings_json, baseline_record_json,
                    npz_rel_path, notes, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    assigned_id,
                    asset_id,
                    now,
                    int(baseline_record.run_count),
                    json.dumps(cam_settings),
                    record_json,
                    npz_rel_path,
                    notes.strip(),
                    str(baseline_record.version),
                ),
            )
            self._conn.commit()

        return StoredBaseline(
            baseline_id=assigned_id,
            asset_id=asset_id,
            created_at=now,
            run_count=int(baseline_record.run_count),
            baseline_record=baseline_record,
            camera_settings=cam_settings,
            npz_rel_path=npz_rel_path,
            notes=notes.strip(),
            version=str(baseline_record.version),
        )

    def get_baseline(self, baseline_id: str) -> StoredBaseline | None:
        """Fetch baseline by ID."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT baseline_id, asset_id, created_at, run_count,
                       camera_settings_json, baseline_record_json,
                       npz_rel_path, notes, version
                FROM baselines WHERE baseline_id = ?;
                """,
                (baseline_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return StoredBaseline(
                baseline_id=row["baseline_id"],
                asset_id=row["asset_id"],
                created_at=row["created_at"],
                run_count=int(row["run_count"]),
                baseline_record=deserialize_baseline(row["baseline_record_json"]),
                camera_settings=json.loads(row["camera_settings_json"]),
                npz_rel_path=row["npz_rel_path"],
                notes=row["notes"],
                version=row["version"],
            )

    def get_latest_baseline_for_asset(self, asset_id: str) -> StoredBaseline | None:
        """Fetch the most recent baseline for an asset."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT baseline_id, asset_id, created_at, run_count,
                       camera_settings_json, baseline_record_json,
                       npz_rel_path, notes, version
                FROM baselines WHERE asset_id = ?
                ORDER BY created_at DESC LIMIT 1;
                """,
                (asset_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return StoredBaseline(
                baseline_id=row["baseline_id"],
                asset_id=row["asset_id"],
                created_at=row["created_at"],
                run_count=int(row["run_count"]),
                baseline_record=deserialize_baseline(row["baseline_record_json"]),
                camera_settings=json.loads(row["camera_settings_json"]),
                npz_rel_path=row["npz_rel_path"],
                notes=row["notes"],
                version=row["version"],
            )

    def list_baselines_for_asset(self, asset_id: str) -> list[StoredBaseline]:
        """List all baselines for an asset ordered by creation date DESC."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT baseline_id, asset_id, created_at, run_count,
                       camera_settings_json, baseline_record_json,
                       npz_rel_path, notes, version
                FROM baselines WHERE asset_id = ?
                ORDER BY created_at DESC;
                """,
                (asset_id,),
            )
            rows = cur.fetchall()

        results = []
        for row in rows:
            results.append(
                StoredBaseline(
                    baseline_id=row["baseline_id"],
                    asset_id=row["asset_id"],
                    created_at=row["created_at"],
                    run_count=int(row["run_count"]),
                    baseline_record=deserialize_baseline(row["baseline_record_json"]),
                    camera_settings=json.loads(row["camera_settings_json"]),
                    npz_rel_path=row["npz_rel_path"],
                    notes=row["notes"],
                    version=row["version"],
                )
            )
        return results

    def delete_baseline(self, baseline_id: str, delete_files: bool = True) -> bool:
        """Delete baseline and optionally clean up NPZ file."""
        npz_to_delete = None

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT npz_rel_path FROM baselines WHERE baseline_id = ?;",
                (baseline_id,),
            )
            row = cur.fetchone()
            if not row:
                return False

            npz_to_delete = row[0]
            cur.execute("DELETE FROM baselines WHERE baseline_id = ?;", (baseline_id,))
            self._conn.commit()

        if delete_files and npz_to_delete:
            try:
                p = self.resolve_path(npz_to_delete)
                if p.is_file():
                    p.unlink()
            except Exception:
                pass

        return True

    # -----------------------------------------------------------------------
    # Inspection Run CRUD Operations
    # -----------------------------------------------------------------------

    def create_inspection_run(
        self,
        asset_id: str,
        video_path: str | Path,
        measured_fps: float,
        duration_s: float,
        frames_analysed: int,
        summary: dict[str, Any],
        baseline_id: str | None = None,
        arrays: RunArrays | None = None,
        valid_patch_ratio: float = 1.0,
        status: str = "Unassessed",
        run_id: str | None = None,
        timestamp: str | None = None,
    ) -> InspectionRunRecord:
        """Create and store an inspection run record."""
        if not self.get_asset(asset_id):
            raise ValueError(f"Asset with ID '{asset_id}' does not exist.")

        if baseline_id is not None and not self.get_baseline(baseline_id):
            raise ValueError(f"Baseline with ID '{baseline_id}' does not exist.")

        if status not in VALID_RUN_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {VALID_RUN_STATUSES}"
            )

        assigned_id = run_id or f"run_{uuid.uuid4().hex[:10]}"
        now = timestamp or _utc_now_iso()

        npz_rel_path = None
        if arrays is not None:
            npz_rel_path = self.save_run_arrays(assigned_id, arrays)

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO inspection_runs (
                    run_id, asset_id, baseline_id, timestamp, video_path,
                    measured_fps, duration_s, frames_analysed, valid_patch_ratio,
                    npz_rel_path, summary_json, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    assigned_id,
                    asset_id,
                    baseline_id,
                    now,
                    str(video_path),
                    float(measured_fps),
                    float(duration_s),
                    int(frames_analysed),
                    float(valid_patch_ratio),
                    npz_rel_path,
                    json.dumps(summary),
                    status,
                ),
            )
            self._conn.commit()

        return InspectionRunRecord(
            run_id=assigned_id,
            asset_id=asset_id,
            timestamp=now,
            video_path=str(video_path),
            measured_fps=float(measured_fps),
            duration_s=float(duration_s),
            frames_analysed=int(frames_analysed),
            valid_patch_ratio=float(valid_patch_ratio),
            summary=summary,
            baseline_id=baseline_id,
            npz_rel_path=npz_rel_path,
            status=status,
        )

    def get_inspection_run(self, run_id: str) -> InspectionRunRecord | None:
        """Fetch inspection run by ID."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT run_id, asset_id, baseline_id, timestamp, video_path,
                       measured_fps, duration_s, frames_analysed, valid_patch_ratio,
                       npz_rel_path, summary_json, status
                FROM inspection_runs WHERE run_id = ?;
                """,
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return InspectionRunRecord(
                run_id=row["run_id"],
                asset_id=row["asset_id"],
                timestamp=row["timestamp"],
                video_path=row["video_path"],
                measured_fps=float(row["measured_fps"]),
                duration_s=float(row["duration_s"]),
                frames_analysed=int(row["frames_analysed"]),
                valid_patch_ratio=float(row["valid_patch_ratio"]),
                summary=json.loads(row["summary_json"]),
                baseline_id=row["baseline_id"],
                npz_rel_path=row["npz_rel_path"],
                status=row["status"],
            )

    def list_inspection_runs(
        self, asset_id: str | None = None, limit: int = 50, offset: int = 0
    ) -> list[InspectionRunRecord]:
        """List inspection runs optionally filtered by asset ID."""
        with self._lock:
            cur = self._conn.cursor()
            if asset_id is not None:
                cur.execute(
                    """
                    SELECT run_id, asset_id, baseline_id, timestamp, video_path,
                           measured_fps, duration_s, frames_analysed, valid_patch_ratio,
                           npz_rel_path, summary_json, status
                    FROM inspection_runs
                    WHERE asset_id = ?
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (asset_id, limit, offset),
                )
            else:
                cur.execute(
                    """
                    SELECT run_id, asset_id, baseline_id, timestamp, video_path,
                           measured_fps, duration_s, frames_analysed, valid_patch_ratio,
                           npz_rel_path, summary_json, status
                    FROM inspection_runs
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?;
                    """,
                    (limit, offset),
                )
            rows = cur.fetchall()

        results = []
        for row in rows:
            results.append(
                InspectionRunRecord(
                    run_id=row["run_id"],
                    asset_id=row["asset_id"],
                    timestamp=row["timestamp"],
                    video_path=row["video_path"],
                    measured_fps=float(row["measured_fps"]),
                    duration_s=float(row["duration_s"]),
                    frames_analysed=int(row["frames_analysed"]),
                    valid_patch_ratio=float(row["valid_patch_ratio"]),
                    summary=json.loads(row["summary_json"]),
                    baseline_id=row["baseline_id"],
                    npz_rel_path=row["npz_rel_path"],
                    status=row["status"],
                )
            )
        return results

    def update_inspection_run_status(self, run_id: str, status: str) -> bool:
        """Update inspection run status."""
        if status not in VALID_RUN_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {VALID_RUN_STATUSES}"
            )

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "UPDATE inspection_runs SET status = ? WHERE run_id = ?;",
                (status, run_id),
            )
            self._conn.commit()
            return cur.rowcount > 0

    def delete_inspection_run(self, run_id: str, delete_files: bool = True) -> bool:
        """Delete inspection run and associated files and review events."""
        files_to_delete: list[str] = []

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT npz_rel_path FROM inspection_runs WHERE run_id = ?;",
                (run_id,),
            )
            row = cur.fetchone()
            if not row:
                return False

            if row[0]:
                files_to_delete.append(row[0])

            if delete_files:
                cur.execute(
                    """
                    SELECT evidence_image_rel_path FROM review_events
                    WHERE run_id = ? AND evidence_image_rel_path IS NOT NULL;
                    """,
                    (run_id,),
                )
                for r in cur.fetchall():
                    if r[0]:
                        files_to_delete.append(r[0])

            # Foreign keys cascade to review_events
            cur.execute("DELETE FROM inspection_runs WHERE run_id = ?;", (run_id,))
            self._conn.commit()

        if delete_files:
            for rel_path in files_to_delete:
                try:
                    p = self.resolve_path(rel_path)
                    if p.is_file():
                        p.unlink()
                except Exception:
                    pass

        return True

    # -----------------------------------------------------------------------
    # Review Event CRUD Operations
    # -----------------------------------------------------------------------

    def create_review_event(
        self,
        run_id: str,
        status: str,
        triggered_features: list[str] | None = None,
        operator_note: str = "",
        evidence_image: bytes | np.ndarray | Path | str | None = None,
        evaluation: BaselineEvaluation | None = None,
        operator_id: str = "operator",
        event_id: str | None = None,
    ) -> ReviewEventRecord:
        """Log an operator review event and update run status."""
        if not self.get_inspection_run(run_id):
            raise ValueError(f"Inspection run with ID '{run_id}' does not exist.")

        if status not in VALID_REVIEW_STATUSES:
            raise ValueError(
                f"Invalid status '{status}'. Must be one of {VALID_REVIEW_STATUSES}"
            )

        assigned_id = event_id or f"rev_{uuid.uuid4().hex[:10]}"
        now = _utc_now_iso()
        feat_list = triggered_features or []

        evidence_rel_path = None
        if evidence_image is not None:
            evidence_rel_path = self.save_evidence_image(assigned_id, evidence_image)

        eval_json = json.dumps(evaluation.to_dict()) if evaluation else None

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                INSERT INTO review_events (
                    event_id, run_id, status, triggered_features_json,
                    operator_note, evidence_image_rel_path, evaluation_json,
                    created_at, operator_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    assigned_id,
                    run_id,
                    status,
                    json.dumps(feat_list),
                    operator_note.strip(),
                    evidence_rel_path,
                    eval_json,
                    now,
                    operator_id.strip(),
                ),
            )
            # Synchronize parent run status
            cur.execute(
                "UPDATE inspection_runs SET status = ? WHERE run_id = ?;",
                (status, run_id),
            )
            self._conn.commit()

        return ReviewEventRecord(
            event_id=assigned_id,
            run_id=run_id,
            status=status,
            triggered_features=feat_list,
            operator_note=operator_note.strip(),
            evidence_image_rel_path=evidence_rel_path,
            evaluation=evaluation,
            created_at=now,
            operator_id=operator_id.strip(),
        )

    def get_review_event(self, event_id: str) -> ReviewEventRecord | None:
        """Fetch review event by ID."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT event_id, run_id, status, triggered_features_json,
                       operator_note, evidence_image_rel_path, evaluation_json,
                       created_at, operator_id
                FROM review_events WHERE event_id = ?;
                """,
                (event_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            eval_obj = None
            if row["evaluation_json"]:
                eval_obj = BaselineEvaluation.from_dict(json.loads(row["evaluation_json"]))

            return ReviewEventRecord(
                event_id=row["event_id"],
                run_id=row["run_id"],
                status=row["status"],
                triggered_features=json.loads(row["triggered_features_json"]),
                operator_note=row["operator_note"],
                evidence_image_rel_path=row["evidence_image_rel_path"],
                evaluation=eval_obj,
                created_at=row["created_at"],
                operator_id=row["operator_id"],
            )

    def list_review_events_for_run(self, run_id: str) -> list[ReviewEventRecord]:
        """List all review events for a given inspection run."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT event_id, run_id, status, triggered_features_json,
                       operator_note, evidence_image_rel_path, evaluation_json,
                       created_at, operator_id
                FROM review_events WHERE run_id = ?
                ORDER BY created_at DESC;
                """,
                (run_id,),
            )
            rows = cur.fetchall()

        results = []
        for row in rows:
            eval_obj = None
            if row["evaluation_json"]:
                eval_obj = BaselineEvaluation.from_dict(json.loads(row["evaluation_json"]))

            results.append(
                ReviewEventRecord(
                    event_id=row["event_id"],
                    run_id=row["run_id"],
                    status=row["status"],
                    triggered_features=json.loads(row["triggered_features_json"]),
                    operator_note=row["operator_note"],
                    evidence_image_rel_path=row["evidence_image_rel_path"],
                    evaluation=eval_obj,
                    created_at=row["created_at"],
                    operator_id=row["operator_id"],
                )
            )
        return results

    def list_recent_review_events(self, limit: int = 50) -> list[ReviewEventRecord]:
        """List recent review events across all runs."""
        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                """
                SELECT event_id, run_id, status, triggered_features_json,
                       operator_note, evidence_image_rel_path, evaluation_json,
                       created_at, operator_id
                FROM review_events
                ORDER BY created_at DESC LIMIT ?;
                """,
                (limit,),
            )
            rows = cur.fetchall()

        results = []
        for row in rows:
            eval_obj = None
            if row["evaluation_json"]:
                eval_obj = BaselineEvaluation.from_dict(json.loads(row["evaluation_json"]))

            results.append(
                ReviewEventRecord(
                    event_id=row["event_id"],
                    run_id=row["run_id"],
                    status=row["status"],
                    triggered_features=json.loads(row["triggered_features_json"]),
                    operator_note=row["operator_note"],
                    evidence_image_rel_path=row["evidence_image_rel_path"],
                    evaluation=eval_obj,
                    created_at=row["created_at"],
                    operator_id=row["operator_id"],
                )
            )
        return results

    def delete_review_event(self, event_id: str, delete_files: bool = True) -> bool:
        """Delete review event and optionally remove evidence image."""
        img_to_delete = None

        with self._lock:
            cur = self._conn.cursor()
            cur.execute(
                "SELECT evidence_image_rel_path FROM review_events WHERE event_id = ?;",
                (event_id,),
            )
            row = cur.fetchone()
            if not row:
                return False

            img_to_delete = row[0]
            cur.execute("DELETE FROM review_events WHERE event_id = ?;", (event_id,))
            self._conn.commit()

        if delete_files and img_to_delete:
            try:
                p = self.resolve_path(img_to_delete)
                if p.is_file():
                    p.unlink()
            except Exception:
                pass

        return True
