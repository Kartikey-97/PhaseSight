#!/usr/bin/env python3
"""Reset and seed a clean, production-ready demo database for PhaseSight.

1. Backs up any existing data/storage/phasesight.db to data/storage/phasesight.db.bak.
2. Creates a clean StorageManager instance at data/storage.
3. Seeds 2 verified real assets:
   - SpectraQuest Rotor Rig (500 FPS) [asset_id: rotor_rig_500fps]
   - Portable Synthetic Bench (60 FPS) [asset_id: portable_bench_60fps]
4. Executes 3 calibration runs on data/portable/baseline.mp4 and builds an immutable
   statistical baseline (Median/MAD) for portable_bench_60fps so deviation detection
   is immediately operational for live demo sessions.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys
import uuid

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from backend.routes.runs import _execute_analysis
from phasesight.baseline import build_baseline
from phasesight.storage import StorageManager
from phasesight.tracker import ROI


def reset_and_seed_database(storage_dir: Path | str = "data/storage") -> None:
    storage_path = Path(storage_dir).resolve()
    storage_path.mkdir(parents=True, exist_ok=True)
    db_file = storage_path / "phasesight.db"
    db_bak = storage_path / "phasesight.db.bak"

    print(f"=== [PhaseSight] Database Reset & Seed Utility ===")
    print(f"Storage path: {storage_path}")

    # 1. Backup and clean existing SQLite files
    if db_file.exists():
        print(f"Backing up existing database: {db_file} -> {db_bak}")
        shutil.copy2(db_file, db_bak)
        try:
            db_file.unlink()
        except Exception as exc:
            print(f"Notice: Could not unlink {db_file}: {exc}")

    for extra in ("phasesight.db-wal", "phasesight.db-shm"):
        extra_file = storage_path / extra
        if extra_file.exists():
            try:
                extra_file.unlink()
            except Exception:
                pass

    # Clean existing npz and batch_outputs for spotless state
    for sub in ("npz", "batch_outputs"):
        sub_dir = storage_path / sub
        if sub_dir.exists():
            shutil.rmtree(sub_dir)

    # 2. Initialize pristine StorageManager
    print("Initializing clean StorageManager schema...")
    storage = StorageManager(storage_path)

    # 3. Seed Asset 1: SpectraQuest Rotor Rig (500 FPS)
    print("\n[1/3] Seeding Asset 1: SpectraQuest Rotor Rig (500 FPS)...")
    rotor_asset = storage.create_asset(
        asset_id="rotor_rig_500fps",
        name="SpectraQuest Rotor Rig (500 FPS)",
        description="SpectraQuest machinery fault simulator benchmark at 500 FPS (Mendeley Data CC-BY-4.0)",
        nominal_speed_rpm=1000.0,
        expected_fps=500.0,
        target_roi=ROI(x=850, y=460, width=64, height=64),
        anchor_roi=ROI(x=600, y=560, width=64, height=64),
    )
    print(f"  Created asset: {rotor_asset.asset_id} ('{rotor_asset.name}')")

    # 4. Seed Asset 2: Portable Synthetic Bench (60 FPS)
    print("\n[2/3] Seeding Asset 2: Portable Synthetic Bench (60 FPS)...")
    portable_asset = storage.create_asset(
        asset_id="portable_bench_60fps",
        name="Portable Synthetic Bench (60 FPS)",
        description="Portable optical vibration test bench (60 FPS ground truth)",
        nominal_speed_rpm=510.0,
        expected_fps=60.0,
        target_roi=ROI(x=360, y=110, width=160, height=160),
        anchor_roi=ROI(x=60, y=100, width=160, height=160),
    )
    print(f"  Created asset: {portable_asset.asset_id} ('{portable_asset.name}')")

    # 5. Run 3 calibration analyses on data/portable/baseline.mp4
    baseline_mp4 = REPO_ROOT / "data" / "portable" / "baseline.mp4"
    if not baseline_mp4.is_file():
        raise FileNotFoundError(f"Required baseline video not found at: {baseline_mp4}")

    print("\n[3/3] Generating 3-run calibration baseline on data/portable/baseline.mp4...")
    runs_for_baseline = []
    target_roi = ROI(x=360, y=110, width=160, height=160)
    anchor_roi = ROI(x=60, y=100, width=160, height=160)

    for i in range(1, 4):
        run_id = f"run_cal_{i}_{uuid.uuid4().hex[:6]}"
        out_dir = storage.storage_root / "batch_outputs" / run_id
        print(f"  Executing calibration run {i}/3 ({run_id})...")
        summary, arrays = _execute_analysis(
            video_path=baseline_mp4,
            target_roi=target_roi,
            anchor_roi=anchor_roi,
            output_dir=out_dir,
            fps_override=60.0,
            nperseg=256,
        )

        run_rec = storage.create_inspection_run(
            asset_id="portable_bench_60fps",
            video_path=str(baseline_mp4),
            measured_fps=float(summary.get("fps_used", 60.0)),
            duration_s=float(summary.get("duration_s", 0.0)),
            frames_analysed=int(summary.get("frames_analysed", 0)),
            summary=summary,
            arrays=arrays,
            valid_patch_ratio=float(summary.get("valid_patch_ratio", 1.0)),
            status="Normal",
            run_id=run_id,
        )
        runs_for_baseline.append(run_rec)
        x_dom = summary.get("x_axis", {}).get("dominant_frequency_hz", 0.0)
        print(f"    Run {i} complete: frames={run_rec.frames_analysed}, X Peak={x_dom:.2f} Hz")

    # 6. Build and store statistical baseline
    print("  Aggregating runs into statistical baseline...")
    baseline_record = build_baseline(
        runs=[r.summary for r in runs_for_baseline],
        asset_id="portable_bench_60fps",
        require_valid_axes=["x"],
        notes="Seed 3-run calibration baseline on portable synthetic bench (60 FPS)",
    )

    stored_baseline = storage.create_baseline(
        asset_id="portable_bench_60fps",
        baseline_record=baseline_record,
        notes="Seed 3-run calibration baseline on portable synthetic bench (60 FPS)",
    )

    # Link runs to baseline
    with storage._lock:
        storage._conn.execute(
            "UPDATE inspection_runs SET baseline_id = ? WHERE asset_id = ?;",
            (stored_baseline.baseline_id, "portable_bench_60fps"),
        )
        storage._conn.commit()

    x_med = baseline_record.x_axis.dominant_frequency_hz.median
    x_mad = baseline_record.x_axis.dominant_frequency_hz.mad
    print(f"  Baseline built: ID={stored_baseline.baseline_id}")
    print(f"  X Dominant Freq Median: {x_med:.2f} Hz (MAD: {x_mad:.4f} Hz)")

    # 7. Verification checks
    print("\n=== Verification ===")
    assets = storage.list_assets()
    print(f"Total assets seeded: {len(assets)}")
    for a in assets:
        print(f"  - [{a.asset_id}] {a.name} (expected_fps={a.expected_fps})")

    baselines = storage.list_baselines_for_asset("portable_bench_60fps")
    print(f"Baselines for 'portable_bench_60fps': {len(baselines)}")
    assert len(assets) == 2, f"Expected 2 assets, found {len(assets)}"
    assert len(baselines) == 1, f"Expected 1 baseline, found {len(baselines)}"

    print("\nDemo database initialized and verified cleanly!")


if __name__ == "__main__":
    reset_and_seed_database()
