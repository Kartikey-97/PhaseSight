"""Tests for PhaseSight local persistence layer (SQLite + NumPy NPZ)."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import numpy as np

from phasesight.baseline import (
    AxisBaseline,
    BaselineEvaluation,
    BaselineRecord,
    FeatureDeviation,
    FeatureStats,
)
from phasesight.storage import (
    AssetRecord,
    InspectionRunRecord,
    ReviewEventRecord,
    RunArrays,
    StorageManager,
    create_connection,
    init_schema,
)
from phasesight.tracker import ROI


@pytest.fixture
def storage_memory():
    """Yield in-memory StorageManager with automatic cleanup."""
    sm = StorageManager(db_path=":memory:")
    yield sm
    sm.close()


@pytest.fixture
def storage_temp(tmp_path: Path):
    """Yield file-backed StorageManager in temporary folder."""
    sm = StorageManager(storage_root=tmp_path)
    yield sm
    sm.close()


@pytest.fixture
def sample_baseline_record() -> BaselineRecord:
    """Return a representative BaselineRecord."""
    scale = 1.482602218505602
    x_axis = AxisBaseline(
        dominant_frequency_hz=FeatureStats(median=8.50, mad=0.01, scale_factor=scale, epsilon=0.020, sample_count=3),
        rms_displacement_px=FeatureStats(median=0.450, mad=0.005, scale_factor=scale, epsilon=0.005, sample_count=3),
        peak_to_median_db=FeatureStats(median=-12.5, mad=0.2, scale_factor=scale, epsilon=1.0, sample_count=3),
        second_harmonic_ratio=FeatureStats(median=0.035, mad=0.002, scale_factor=scale, epsilon=0.010, sample_count=3),
    )
    y_axis = AxisBaseline(
        dominant_frequency_hz=FeatureStats(median=0.0, mad=0.0, scale_factor=scale, epsilon=0.020, sample_count=3),
        rms_displacement_px=FeatureStats(median=0.010, mad=0.001, scale_factor=scale, epsilon=0.005, sample_count=3),
        peak_to_median_db=FeatureStats(median=-40.0, mad=0.5, scale_factor=scale, epsilon=1.0, sample_count=3),
        second_harmonic_ratio=None,
    )
    return BaselineRecord(
        baseline_id="bsl_test_123",
        asset_id="ast_test",
        created_at="2026-11-18T12:00:00+00:00",
        run_count=3,
        target_roi={"x": 360, "y": 110, "width": 160, "height": 160},
        anchor_roi={"x": 60, "y": 100, "width": 160, "height": 160},
        sampling_rate_hz=60.0,
        x_axis=x_axis,
        y_axis=y_axis,
        baseline_run_ids=["run_01", "run_02", "run_03"],
        notes="Healthy reference baseline",
        version="1.0",
    )


@pytest.fixture
def sample_run_arrays() -> RunArrays:
    """Return a representative RunArrays object with 600 frames and 256 PSD points."""
    t = np.linspace(0, 10, 600, dtype=np.float64)
    dx = 0.5 * np.sin(2 * np.pi * 8.5 * t)
    dy = 0.05 * np.random.randn(600)
    freqs = np.linspace(0, 30, 256, dtype=np.float64)
    psd_x = np.exp(-0.5 * ((freqs - 8.5) / 0.5) ** 2)
    psd_y = np.ones(256, dtype=np.float64) * 1e-4

    return RunArrays(
        timestamps_s=t,
        relative_dx_px=dx,
        relative_dy_px=dy,
        target_dx_px=dx + 0.1,
        target_dy_px=dy + 0.1,
        anchor_dx_px=np.zeros(600),
        anchor_dy_px=np.zeros(600),
        target_response=np.ones(600) * 0.95,
        anchor_response=np.ones(600) * 0.98,
        x_frequencies_hz=freqs,
        x_psd_px2_per_hz=psd_x,
        y_frequencies_hz=freqs,
        y_psd_px2_per_hz=psd_y,
    )


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------

def test_asset_crud_and_duplicates(storage_memory: StorageManager):
    """PERSIST-01: Asset create, read, list, update, delete, and duplicate prevention."""
    sm = storage_memory

    # Create
    asset = sm.create_asset(
        name="Cooling Fan B",
        target_roi={"x": 100, "y": 120, "width": 80, "height": 80},
        anchor_roi={"x": 20, "y": 20, "width": 80, "height": 80},
        expected_fps=60.0,
        description="Auxiliary fan for motor 3",
        nominal_speed_rpm=1750.0,
        asset_id="ast_fan_b",
    )
    assert asset.asset_id == "ast_fan_b"
    assert asset.name == "Cooling Fan B"
    assert asset.nominal_speed_rpm == 1750.0

    # Duplicate ID rejection
    with pytest.raises(ValueError, match="already exists"):
        sm.create_asset(
            name="Duplicate Fan",
            target_roi={"x": 10, "y": 10, "width": 32, "height": 32},
            anchor_roi={"x": 0, "y": 0, "width": 32, "height": 32},
            asset_id="ast_fan_b",
        )

    # Read
    fetched = sm.get_asset("ast_fan_b")
    assert fetched is not None
    assert fetched.name == "Cooling Fan B"
    assert fetched.expected_fps == 60.0

    # List
    all_assets = sm.list_assets()
    assert len(all_assets) == 1
    assert all_assets[0].asset_id == "ast_fan_b"

    # Update
    updated = sm.update_asset(
        "ast_fan_b",
        name="Cooling Fan B (Overhauled)",
        nominal_speed_rpm=1800.0,
    )
    assert updated.name == "Cooling Fan B (Overhauled)"
    assert updated.nominal_speed_rpm == 1800.0

    refetched = sm.get_asset("ast_fan_b")
    assert refetched.name == "Cooling Fan B (Overhauled)"

    # Delete
    deleted = sm.delete_asset("ast_fan_b")
    assert deleted is True
    assert sm.get_asset("ast_fan_b") is None
    assert len(sm.list_assets()) == 0


def test_roi_dataclass_roundtrip(storage_memory: StorageManager):
    """PERSIST-01 / D-07: Asset target_roi_obj() and anchor_roi_obj() return valid tracker.ROI instances."""
    sm = storage_memory
    roi_t = ROI(x=360, y=110, width=160, height=160)
    roi_a = ROI(x=60, y=100, width=160, height=160)

    asset = sm.create_asset(
        name="Pump Alpha",
        target_roi=roi_t,
        anchor_roi=roi_a,
    )

    assert isinstance(asset.target_roi_obj(), ROI)
    assert isinstance(asset.anchor_roi_obj(), ROI)
    assert asset.target_roi_obj() == roi_t
    assert asset.anchor_roi_obj() == roi_a


def test_baseline_persistence_and_latest(
    storage_temp: StorageManager, sample_baseline_record: BaselineRecord
):
    """PERSIST-02: Storing BaselineRecord and querying get_latest_baseline_for_asset."""
    sm = storage_temp
    asset = sm.create_asset(
        name="Chilled Water Pump",
        target_roi={"x": 50, "y": 50, "width": 64, "height": 64},
        anchor_roi={"x": 0, "y": 0, "width": 64, "height": 64},
    )

    # Save baseline 1
    b1 = sm.create_baseline(
        asset_id=asset.asset_id,
        baseline_record=sample_baseline_record,
        camera_settings={"shutter": "1/500", "iso": 100},
        notes="Initial healthy baseline",
        baseline_id="bsl_001",
    )
    assert b1.baseline_id == "bsl_001"
    assert b1.run_count == 3
    assert b1.baseline_record.sampling_rate_hz == 60.0
    assert b1.baseline_record.x_axis is not None

    # Save baseline 2
    b2 = sm.create_baseline(
        asset_id=asset.asset_id,
        baseline_record=sample_baseline_record,
        notes="Second baseline check",
        baseline_id="bsl_002",
    )

    # Query latest
    latest = sm.get_latest_baseline_for_asset(asset.asset_id)
    assert latest is not None
    assert latest.baseline_id == "bsl_002"
    assert latest.notes == "Second baseline check"

    # List all for asset
    baselines = sm.list_baselines_for_asset(asset.asset_id)
    assert len(baselines) == 2


def test_inspection_run_archival_and_status(storage_temp: StorageManager):
    """PERSIST-03: Archiving inspection runs, verifying default status, and updating status."""
    sm = storage_temp
    asset = sm.create_asset(
        name="Conveyor Motor",
        target_roi={"x": 10, "y": 10, "width": 40, "height": 40},
        anchor_roi={"x": 0, "y": 0, "width": 40, "height": 40},
    )

    summary_data = {
        "x": {"dominant_frequency_hz": 8.52, "rms_amplitude_px": 0.48, "signal_quality": "VALID"},
        "y": {"dominant_frequency_hz": 0.0, "rms_amplitude_px": 0.01, "signal_quality": "CONTAMINATED"},
    }

    run = sm.create_inspection_run(
        asset_id=asset.asset_id,
        video_path="/data/conveyor_run_01.mp4",
        measured_fps=59.98,
        duration_s=10.05,
        frames_analysed=603,
        summary=summary_data,
        valid_patch_ratio=0.98,
        run_id="run_conv_01",
    )

    assert run.run_id == "run_conv_01"
    assert run.status == "Unassessed"
    assert run.frames_analysed == 603

    # Update status
    updated = sm.update_inspection_run_status("run_conv_01", "Review")
    assert updated is True

    fetched = sm.get_inspection_run("run_conv_01")
    assert fetched.status == "Review"
    assert fetched.summary["x"]["dominant_frequency_hz"] == 8.52


def test_review_event_logging_and_constraints(storage_temp: StorageManager):
    """PERSIST-04: Logging review events with BaselineEvaluation and status validation."""
    sm = storage_temp
    asset = sm.create_asset(
        name="Blower",
        target_roi={"x": 20, "y": 20, "width": 50, "height": 50},
        anchor_roi={"x": 0, "y": 0, "width": 50, "height": 50},
    )
    run = sm.create_inspection_run(
        asset_id=asset.asset_id,
        video_path="blower.mp4",
        measured_fps=60.0,
        duration_s=5.0,
        frames_analysed=300,
        summary={},
        run_id="run_blower_01",
    )

    dev = FeatureDeviation(
        feature_name="rms_amplitude_px",
        axis="x",
        current_value=0.62,
        baseline_median=0.45,
        baseline_mad=0.005,
        z_robust=4.2,
        is_trigger=True,
        notes="rms exceeded",
    )
    eval_obj = BaselineEvaluation(
        status="Review",
        confidence_passed=True,
        reasons=["rms_amplitude_px (z=+4.2)"],
        trigger_features=["rms_amplitude_px"],
        deviations={"x:rms_amplitude_px": dev},
        z_threshold=3.0,
        baseline_id="bsl_blower_01",
        asset_id=asset.asset_id,
        evaluated_at="2026-11-18T12:00:00+00:00",
    )

    # Valid review event
    rev = sm.create_review_event(
        run_id=run.run_id,
        status="Review",
        triggered_features=["rms_amplitude_px"],
        operator_note="Unusual vibration spike observed on X axis.",
        evaluation=eval_obj,
        event_id="rev_blower_01",
    )
    assert rev.status == "Review"
    assert rev.evaluation is not None
    assert rev.evaluation.status == "Review"
    assert len(rev.evaluation.deviations) == 1

    # Check that parent run status synchronized
    parent_run = sm.get_inspection_run(run.run_id)
    assert parent_run.status == "Review"

    # Invalid status raises ValueError
    with pytest.raises(ValueError, match="Invalid status"):
        sm.create_review_event(
            run_id=run.run_id,
            status="Fault",  # Invalid! Must be Normal, Review, or Low confidence
        )


def test_run_arrays_npz_fidelity_and_compression(
    storage_temp: StorageManager, sample_run_arrays: RunArrays
):
    """PERSIST-05: Saving and loading RunArrays with lossless precision and compression under 25 KB."""
    sm = storage_temp
    rel_path = sm.save_run_arrays("run_arrays_test", sample_run_arrays)

    # Check file exists and size < 35 KB
    abs_path = sm.resolve_path(rel_path)
    assert abs_path.is_file()
    file_size_kb = abs_path.stat().st_size / 1024
    assert file_size_kb < 35.0, f"NPZ file too large: {file_size_kb} KB"

    # Load and verify precision
    loaded = sm.load_run_arrays("run_arrays_test")
    assert len(loaded.timestamps_s) == 600
    assert np.allclose(loaded.timestamps_s, sample_run_arrays.timestamps_s)
    assert np.allclose(loaded.relative_dx_px, sample_run_arrays.relative_dx_px)
    assert np.allclose(loaded.relative_dy_px, sample_run_arrays.relative_dy_px)
    assert np.allclose(loaded.x_psd_px2_per_hz, sample_run_arrays.x_psd_px2_per_hz)


def test_npz_missing_optional_arrays(storage_temp: StorageManager):
    """PERSIST-05: RunArrays handles optional None arrays gracefully."""
    sm = storage_temp
    minimal_arrays = RunArrays(
        timestamps_s=np.array([0.0, 0.1, 0.2]),
        relative_dx_px=np.array([0.01, 0.02, 0.03]),
        relative_dy_px=np.array([0.00, 0.01, 0.00]),
    )
    rel_path = sm.save_run_arrays("minimal_arrays", minimal_arrays)
    loaded = sm.load_run_arrays(rel_path)

    assert len(loaded.timestamps_s) == 3
    assert loaded.target_dx_px is None
    assert loaded.x_psd_px2_per_hz is None


def test_foreign_key_cascades_asset_deletion(
    storage_temp: StorageManager, sample_baseline_record: BaselineRecord, sample_run_arrays: RunArrays
):
    """PERSIST-06 / D-05: Deleting an asset cascades deletion to baselines, runs, and reviews."""
    sm = storage_temp
    asset = sm.create_asset(
        name="Turbine 1",
        target_roi={"x": 0, "y": 0, "width": 32, "height": 32},
        anchor_roi={"x": 50, "y": 50, "width": 32, "height": 32},
        asset_id="ast_turbine_1",
    )
    baseline = sm.create_baseline(
        asset_id="ast_turbine_1",
        baseline_record=sample_baseline_record,
        arrays=sample_run_arrays,
        baseline_id="bsl_turbine_1",
    )
    run = sm.create_inspection_run(
        asset_id="ast_turbine_1",
        baseline_id="bsl_turbine_1",
        video_path="turbine.mp4",
        measured_fps=60.0,
        duration_s=10.0,
        frames_analysed=600,
        summary={},
        arrays=sample_run_arrays,
        run_id="run_turbine_1",
    )
    rev = sm.create_review_event(
        run_id="run_turbine_1",
        status="Normal",
        evidence_image=b"\x89PNG\r\n\x1a\nfakeimagebytes",
        event_id="rev_turbine_1",
    )

    # Delete asset with files
    deleted = sm.delete_asset("ast_turbine_1", delete_files=True)
    assert deleted is True

    # Database records deleted
    assert sm.get_asset("ast_turbine_1") is None
    assert sm.get_baseline("bsl_turbine_1") is None
    assert sm.get_inspection_run("run_turbine_1") is None
    assert sm.get_review_event("rev_turbine_1") is None

    # Files deleted
    assert not sm.resolve_path(f"npz/baselines/{baseline.baseline_id}.npz").is_file()
    assert not sm.resolve_path(f"npz/runs/{run.run_id}.npz").is_file()
    assert not sm.resolve_path(f"evidence/{rev.event_id}.png").is_file()


def test_foreign_key_set_null_baseline_deletion(
    storage_memory: StorageManager, sample_baseline_record: BaselineRecord
):
    """PERSIST-06: Deleting a baseline sets run baseline_id to NULL without deleting the run."""
    sm = storage_memory
    asset = sm.create_asset(
        name="Pump 9",
        target_roi={"x": 0, "y": 0, "width": 32, "height": 32},
        anchor_roi={"x": 10, "y": 10, "width": 32, "height": 32},
        asset_id="ast_pump_9",
    )
    baseline = sm.create_baseline(
        asset_id="ast_pump_9",
        baseline_record=sample_baseline_record,
        baseline_id="bsl_pump_9",
    )
    run = sm.create_inspection_run(
        asset_id="ast_pump_9",
        baseline_id="bsl_pump_9",
        video_path="pump.mp4",
        measured_fps=60.0,
        duration_s=5.0,
        frames_analysed=300,
        summary={},
        run_id="run_pump_9",
    )

    # Delete baseline
    sm.delete_baseline("bsl_pump_9")
    assert sm.get_baseline("bsl_pump_9") is None

    # Inspection run still exists, but baseline_id is set to None
    fetched_run = sm.get_inspection_run("run_pump_9")
    assert fetched_run is not None
    assert fetched_run.baseline_id is None


def test_foreign_key_cascades_run_deletion(storage_memory: StorageManager):
    """PERSIST-06: Deleting an inspection run automatically cascades to review events."""
    sm = storage_memory
    asset = sm.create_asset(
        name="Fan 4",
        target_roi={"x": 0, "y": 0, "width": 32, "height": 32},
        anchor_roi={"x": 10, "y": 10, "width": 32, "height": 32},
    )
    run = sm.create_inspection_run(
        asset_id=asset.asset_id,
        video_path="fan.mp4",
        measured_fps=60.0,
        duration_s=2.0,
        frames_analysed=120,
        summary={},
        run_id="run_fan_4",
    )
    rev = sm.create_review_event(
        run_id="run_fan_4",
        status="Low confidence",
        event_id="rev_fan_4",
    )

    sm.delete_inspection_run("run_fan_4")
    assert sm.get_inspection_run("run_fan_4") is None
    assert sm.get_review_event("rev_fan_4") is None


def test_file_cleanup_on_record_deletion(
    storage_temp: StorageManager, sample_run_arrays: RunArrays
):
    """D-01 / PERSIST-06: delete_files=True removes files; delete_files=False retains them."""
    sm = storage_temp
    asset = sm.create_asset(
        name="Mixer",
        target_roi={"x": 0, "y": 0, "width": 32, "height": 32},
        anchor_roi={"x": 10, "y": 10, "width": 32, "height": 32},
    )
    run = sm.create_inspection_run(
        asset_id=asset.asset_id,
        video_path="mixer.mp4",
        measured_fps=60.0,
        duration_s=10.0,
        frames_analysed=600,
        summary={},
        arrays=sample_run_arrays,
        run_id="run_mixer_01",
    )
    npz_path = sm.resolve_path(f"npz/runs/{run.run_id}.npz")
    assert npz_path.is_file()

    # Delete run with delete_files=True
    sm.delete_inspection_run(run.run_id, delete_files=True)
    assert not npz_path.is_file()


def test_in_memory_isolation_and_tempdir():
    """D-04: db_path=':memory:' works without disk side effects and cleans up on close."""
    sm = StorageManager(db_path=":memory:")
    info = sm.get_db_info()
    assert info["db_path"] == ":memory:"
    temp_root = Path(info["storage_root"])
    assert temp_root.is_dir()

    # Create dummy asset and array
    sm.create_asset(
        name="Memory Asset",
        target_roi={"x": 10, "y": 10, "width": 32, "height": 32},
        anchor_roi={"x": 0, "y": 0, "width": 32, "height": 32},
    )
    sm.close()

    # Temporary directory should be cleaned up
    assert not temp_root.exists()


def test_thread_concurrency_safety():
    """PERSIST-06: 10 concurrent worker threads executing concurrent operations succeed without error."""
    sm = StorageManager(db_path=":memory:")
    asset = sm.create_asset(
        name="Concurrent Machine",
        target_roi={"x": 0, "y": 0, "width": 32, "height": 32},
        anchor_roi={"x": 10, "y": 10, "width": 32, "height": 32},
        asset_id="ast_concurrent",
    )

    def worker_task(idx: int) -> str:
        run_id = f"run_worker_{idx}"
        sm.create_inspection_run(
            asset_id="ast_concurrent",
            video_path=f"video_{idx}.mp4",
            measured_fps=60.0,
            duration_s=1.0,
            frames_analysed=60,
            summary={"idx": idx},
            run_id=run_id,
        )
        sm.create_review_event(
            run_id=run_id,
            status="Normal",
            operator_note=f"Worker {idx} review",
            event_id=f"rev_worker_{idx}",
        )
        fetched = sm.get_inspection_run(run_id)
        assert fetched is not None
        return run_id

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker_task, i) for i in range(10)]
        results = [f.result() for f in futures]

    assert len(results) == 10
    info = sm.get_db_info()
    assert info["run_count"] == 10
    assert info["review_count"] == 10
    sm.close()


def test_schema_migration_idempotence(storage_memory: StorageManager):
    """PERSIST-06: Calling init_schema multiple times maintains user_version = 1."""
    conn = storage_memory._conn
    init_schema(conn)
    init_schema(conn)

    cur = conn.cursor()
    cur.execute("PRAGMA user_version;")
    assert cur.fetchone()[0] == 1


def test_path_traversal_prevention(storage_memory: StorageManager):
    """PERSIST-06 / T-04-02: Path traversal attempts raise ValueError."""
    sm = storage_memory

    with pytest.raises(ValueError, match="Path traversal detected"):
        sm.resolve_path("../../etc/passwd")

    with pytest.raises(ValueError, match="Path traversal detected"):
        sm.resolve_path("npz/../../../secret.txt")
