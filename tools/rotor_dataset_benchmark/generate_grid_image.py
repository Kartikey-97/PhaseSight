#!/usr/bin/env python3
"""
Generate detailed visual overview of Frame-TestRig and first frame of 1000rpm-Unb1.
Adds horizontal and vertical ruler markings to assist ROI selection.
"""

from __future__ import annotations
from pathlib import Path
import cv2
import numpy as np

REPORTS_DIR = Path("reports/rotor_dataset_benchmark")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

def annotate_frame_with_grid(image_path: Path, out_path: Path, step: int = 100):
    img = cv2.imread(str(image_path))
    h, w, _ = img.shape
    annotated = img.copy()

    # Draw grid lines
    for x in range(0, w, step):
        cv2.line(annotated, (x, 0), (x, h), (0, 255, 255), 1)
        cv2.putText(annotated, f"X={x}", (x + 2, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)
        cv2.putText(annotated, f"X={x}", (x + 2, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    for y in range(0, h, step):
        cv2.line(annotated, (0, y), (w, y), (0, 255, 255), 1)
        cv2.putText(annotated, f"Y={y}", (5, y - 5), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 255), 1)

    # Mark shaft centerline approx Y=495
    cv2.line(annotated, (0, 495), (w, 495), (0, 0, 255), 1)
    cv2.putText(annotated, "Shaft Centerline approx Y=495", (50, 490), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)

    cv2.imwrite(str(out_path), annotated)
    print(f"Saved annotated grid image: {out_path}")

if __name__ == "__main__":
    frame_first = REPORTS_DIR / "extracted_frames" / "1000rpm-Unb1_frame_first.jpg"
    out_grid = REPORTS_DIR / "1000rpm-Unb1_frame_first_grid.jpg"
    annotate_frame_with_grid(frame_first, out_grid, step=100)
