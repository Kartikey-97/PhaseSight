#!/usr/bin/env python3
"""
PhaseSight - Final Benchmark Integrity Review Script
Investigates:
1. FPS and timestamp integrity (CLI vs container PTS vs physical 500 FPS)
2. Sensor units and calibration analysis
3. Frequency-estimation consistency (FFT vs Welch vs parabolic interpolation)
4. Controlled resonance comparison (apples-to-apples, unsaturated channels #4 & #1)
5. Unbalance-condition comparison (Unb1, Unb2, Unb3 at 1000, 2000, 3000 RPM)
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import cv2
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

from phasesight.analysis import analyse_displacement
from phasesight.tracker import PhaseCorrelationTracker, ROI

DATASET_ROOT = Path("data/rotor_dataset")
RAW_VIDEOS_DIR = DATASET_ROOT / "Raw videos"
SENSOR_DIR = DATASET_ROOT / "Sensor data"
REPORTS_DIR = Path("reports/rotor_dataset_benchmark")
PLOTS_DIR = REPORTS_DIR / "plots"

# Standard Anchor
ANCHOR_A1 = ROI(600, 560, 64, 64)

# Targets
TARGET_A = ROI(600, 460, 64, 64)   # Midspan Span 1 (near Sensor 2)
TARGET_C = ROI(850, 460, 64, 64)   # Right Span 2 near Pedestal 2 (near Sensor 4)
TARGET_D = ROI(250, 460, 64, 64)   # Left Span 1 near Pedestal 1 (near Sensor 1)

def test_fps_timestamp_mechanics(video_file: str = "1000rpm-Unb1.avi"):
    """Examine OpenCV POS_MSEC behavior and PhaseSight video.py timestamp assignment."""
    vpath = RAW_VIDEOS_DIR / video_file
    cap = cv2.VideoCapture(str(vpath))
    meta_fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    pos_msecs = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        pos_msecs.append(cap.get(cv2.CAP_PROP_POS_MSEC))
    cap.release()

    dt_msec = np.diff(pos_msecs)
    unique_dts = np.unique(np.round(dt_msec, 4))

    return {
        "video": video_file,
        "container_meta_fps": meta_fps,
        "container_frame_count": count,
        "first_5_pos_msec": pos_msecs[:5],
        "last_5_pos_msec": pos_msecs[-5:],
        "dt_msec_unique": unique_dts.tolist(),
        "implied_container_dt_s": float(np.mean(dt_msec)) / 1000.0,
        "implied_container_fps": 1000.0 / float(np.mean(dt_msec)),
    }

def main():
    print("Running Benchmark Integrity Review...")
    res = test_fps_timestamp_mechanics()
    print("FPS Mechanics:", json.dumps(res, indent=2))

if __name__ == "__main__":
    main()
