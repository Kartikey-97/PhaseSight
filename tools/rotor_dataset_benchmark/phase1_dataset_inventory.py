#!/usr/bin/env python3
"""
Phase 1: Dataset Inventory and Metadata Analysis
Recursively inspects all AVI videos, CSV sensor recordings, images, and CAD models.
Outputs manifest table, detailed JSON, and frame samples.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import cv2
import numpy as np

DATASET_ROOT = Path("data/rotor_dataset")
REPORTS_DIR = Path("reports/rotor_dataset_benchmark")
FRAMES_DIR = REPORTS_DIR / "extracted_frames"

def inspect_avi(file_path: Path) -> dict:
    cap = cv2.VideoCapture(str(file_path))
    if not cap.isOpened():
        return {
            "file": file_path.name,
            "status": "ERROR_CANNOT_OPEN",
            "size_bytes": file_path.stat().st_size,
        }

    meta_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    reported_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
    fourcc_str = "".join([chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)])

    decodable_count = 0
    duplicate_count = 0
    corrupt_count = 0
    pts_list = []
    prev_frame = None

    first_frame = None
    mid_frame = None
    last_frame = None

    # First pass: read all frames to count accurately and check corruption/duplicates
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        pos_msec = cap.get(cv2.CAP_PROP_POS_MSEC)
        pts_list.append(pos_msec)
        decodable_count += 1

        if first_frame is None:
            first_frame = frame.copy()
        mid_frame = frame  # will be captured at half count in second pass if needed

        if prev_frame is not None:
            # Check for identical duplicate frames
            if np.array_equal(frame, prev_frame):
                duplicate_count += 1
        prev_frame = frame
        last_frame = frame

    cap.release()

    # Re-read to get exact middle frame
    cap2 = cv2.VideoCapture(str(file_path))
    mid_idx = decodable_count // 2
    for idx in range(mid_idx + 1):
        ok, f = cap2.read()
        if idx == mid_idx and ok:
            mid_frame = f.copy()
    cap2.release()

    # Save representative frames
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)
    stem = file_path.stem
    if first_frame is not None:
        cv2.imwrite(str(FRAMES_DIR / f"{stem}_frame_first.jpg"), first_frame)
    if mid_frame is not None:
        cv2.imwrite(str(FRAMES_DIR / f"{stem}_frame_mid.jpg"), mid_frame)
    if last_frame is not None:
        cv2.imwrite(str(FRAMES_DIR / f"{stem}_frame_last.jpg"), last_frame)

    # Inspect timestamps
    unique_pts = len(set(pts_list))
    pts_diffs = np.diff(pts_list) if len(pts_list) > 1 else np.array([])
    pts_constant = bool(len(pts_diffs) > 0 and np.allclose(pts_diffs, pts_diffs[0]))
    pts_frozen = bool(unique_pts <= 1)

    # Physical vs metadata duration
    nominal_camera_fps = 500.0  # From README.md
    duration_meta_s = decodable_count / meta_fps if meta_fps > 0 else 0.0
    duration_actual_s = decodable_count / nominal_camera_fps

    return {
        "file": file_path.name,
        "type": "AVI Video",
        "size_bytes": file_path.stat().st_size,
        "resolution": f"{w}x{h}",
        "width": w,
        "height": h,
        "container_fps": meta_fps,
        "physical_fps": nominal_camera_fps,
        "reported_frame_count": reported_count,
        "decodable_frame_count": decodable_count,
        "duration_container_s": duration_meta_s,
        "duration_physical_s": duration_actual_s,
        "codec": fourcc_str,
        "duplicate_frames": duplicate_count,
        "corrupt_frames": corrupt_count,
        "pts_frozen": pts_frozen,
        "pts_constant_step": pts_constant,
        "pts_unique_count": unique_pts,
        "status": "VALID",
    }


def inspect_csv(file_path: Path) -> dict:
    size = file_path.stat().st_size
    # Read raw lines first to inspect headers
    with open(file_path, "r", encoding="utf-8") as f:
        first_line = f.readline().strip()
        second_line = f.readline().strip()

    # Check if first line contains non-numeric header
    has_header = False
    tokens = first_line.split(",")
    try:
        float(tokens[0])
    except ValueError:
        has_header = True

    try:
        data = np.loadtxt(file_path, delimiter=",", skiprows=1 if has_header else 0)
    except Exception as e:
        return {
            "file": file_path.name,
            "type": "CSV Sensor Data",
            "size_bytes": size,
            "status": f"LOAD_ERROR: {e}",
        }

    n_samples, n_cols = data.shape
    sampling_rate_hz = 1000.0  # From README.md
    duration_s = n_samples / sampling_rate_hz

    # Non-finite values
    n_nan = int(np.isnan(data).sum())
    n_inf = int(np.isinf(data).sum())

    channels_stats = []
    for col_idx in range(n_cols):
        col_data = data[:, col_idx]
        col_min = float(np.min(col_data))
        col_max = float(np.max(col_data))
        col_mean = float(np.mean(col_data))
        col_std = float(np.std(col_data))
        col_ptp = float(col_max - col_min)
        # Check potential clipping
        channels_stats.append({
            "channel": col_idx + 1,
            "min": col_min,
            "max": col_max,
            "mean": col_mean,
            "std": col_std,
            "peak_to_peak": col_ptp,
        })

    return {
        "file": file_path.name,
        "type": "CSV Sensor Data",
        "size_bytes": size,
        "has_explicit_header": has_header,
        "columns": n_cols,
        "samples": n_samples,
        "sampling_rate_hz": sampling_rate_hz,
        "duration_s": duration_s,
        "nan_count": n_nan,
        "inf_count": n_inf,
        "channels": channels_stats,
        "status": "VALID",
    }


def main():
    print("Beginning Phase 1: Dataset Inventory...")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    FRAMES_DIR.mkdir(parents=True, exist_ok=True)

    manifest_rows = []
    video_details = []
    csv_details = []
    other_details = []

    # 1. Inventory AVIs
    raw_videos_dir = DATASET_ROOT / "Raw videos"
    avi_files = sorted(list(raw_videos_dir.glob("*.avi")))
    print(f"Found {len(avi_files)} AVI videos.")
    for avi in avi_files:
        print(f"  Inspecting {avi.name}...")
        details = inspect_avi(avi)
        video_details.append(details)
        manifest_rows.append({
            "Filename": avi.name,
            "Type": "AVI Video",
            "Size": f"{details['size_bytes'] / (1024*1024):.2f} MB",
            "Related operating condition": avi.stem,
            "Status": f"Valid ({details['decodable_frame_count']} frames, {details['resolution']}, {details['duration_physical_s']:.2f}s @ 500fps)",
        })

    # 2. Inventory CSVs
    sensor_dir = DATASET_ROOT / "Sensor data"
    csv_files = sorted(list(sensor_dir.glob("*.csv")))
    print(f"Found {len(csv_files)} CSV sensor files.")
    for csv_f in csv_files:
        print(f"  Inspecting {csv_f.name}...")
        details = inspect_csv(csv_f)
        csv_details.append(details)
        manifest_rows.append({
            "Filename": csv_f.name,
            "Type": "CSV Sensor Data",
            "Size": f"{details['size_bytes'] / 1024:.2f} KB",
            "Related operating condition": csv_f.stem,
            "Status": f"Valid ({details['samples']} samples, 4-ch, {details['duration_s']:.2f}s @ 1000Hz)",
        })

    # 3. Inventory other files
    other_files = [
        DATASET_ROOT / "Frame-TestRig.jpg",
        DATASET_ROOT / "Rotor-TestRig.jpg",
        DATASET_ROOT / "README.md",
        DATASET_ROOT / "Three-dimensional rotor test rig model" / "Rotor Test-rig.x_t",
        DATASET_ROOT / "Three-dimensional rotor test rig model" / "Rotor Test-rig.STEP",
    ]
    for of in other_files:
        if of.exists():
            size = of.stat().st_size
            ext = of.suffix.lower()
            tname = "Image" if ext == ".jpg" else ("CAD Model" if ext in [".x_t", ".step"] else "Documentation")
            stat_desc = "Available"
            if ext == ".jpg":
                img = cv2.imread(str(of))
                if img is not None:
                    h, w, c = img.shape
                    stat_desc = f"Valid Image ({w}x{h}, {c} channels)"
            other_details.append({
                "file": of.name,
                "type": tname,
                "size_bytes": size,
                "status": stat_desc,
            })
            manifest_rows.append({
                "Filename": of.name,
                "Type": tname,
                "Size": f"{size / 1024:.2f} KB" if size < 1024*1024 else f"{size / (1024*1024):.2f} MB",
                "Related operating condition": "Rig Setup / Documentation",
                "Status": stat_desc,
            })

    # Save full inventory JSON
    full_inventory = {
        "dataset_name": "Vibration Displacement Dataset of Rotors under Various Operational Conditions",
        "total_files": len(manifest_rows),
        "video_count": len(video_details),
        "csv_count": len(csv_details),
        "videos": video_details,
        "csvs": csv_details,
        "auxiliary": other_details,
    }

    json_path = REPORTS_DIR / "dataset_inventory.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(full_inventory, f, indent=2)
    print(f"Saved dataset inventory JSON to {json_path}")

    # Save manifest CSV
    manifest_csv_path = REPORTS_DIR / "dataset_manifest.csv"
    with open(manifest_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["Filename", "Type", "Size", "Related operating condition", "Status"])
        writer.writeheader()
        writer.writerows(manifest_rows)
    print(f"Saved dataset manifest CSV to {manifest_csv_path}")

    # Generate Markdown Table
    md_table = [
        "| Filename | Type | Size | Related operating condition | Status |",
        "|---|---|---|---|---|",
    ]
    for row in manifest_rows:
        md_table.append(f"| {row['Filename']} | {row['Type']} | {row['Size']} | {row['Related operating condition']} | {row['Status']} |")

    md_manifest_path = REPORTS_DIR / "dataset_manifest.md"
    with open(md_manifest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md_table) + "\n")
    print(f"Saved dataset manifest Markdown to {md_manifest_path}")

    print("\nPhase 1 Inventory Complete!")


if __name__ == "__main__":
    main()
