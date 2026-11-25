#!/usr/bin/env python3
"""
Phase 3: Annotated ROI Selection
Generates high-resolution annotated image of 1000rpm-Unb1 showing:
- Physical sensor positions (Sensors #1, #2, #3, #4)
- Candidate Target ROIs (T1, T2, T3, T4, T5, T6)
- Candidate Anchor ROIs (A1, A2, A3)
Saves image and metadata to reports/rotor_dataset_benchmark/
"""

from __future__ import annotations
import json
from pathlib import Path
import cv2
import numpy as np

REPORTS_DIR = Path("reports/rotor_dataset_benchmark")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

CANDIDATE_ROIS = {
    "targets": [
        {
            "id": "T1_span1_mid",
            "name": "Target 1 (Span 1 Mid - near Sensor #2)",
            "x": 520, "y": 460, "w": 64, "h": 64,
            "description": "Shaft top edge in Span 1; high contrast edge against uniform backdrop near antinode.",
            "sensor_relation": "Sensor #2 (Span 1 midspan deflection)",
        },
        {
            "id": "T2_span2_mid",
            "name": "Target 2 (Span 2 Mid - near Sensor #3)",
            "x": 720, "y": 460, "w": 64, "h": 64,
            "description": "Shaft top edge in Span 2; clear edge near central disk/coupling antinode.",
            "sensor_relation": "Sensor #3 (Span 2 midspan deflection)",
        },
        {
            "id": "T3_span2_right",
            "name": "Target 3 (Span 2 Right - near Sensor #4)",
            "x": 820, "y": 460, "w": 64, "h": 64,
            "description": "Shaft top edge near Bearing Pedestal 2.",
            "sensor_relation": "Sensor #4 (Recommended reference sensor for acceleration)",
        },
        {
            "id": "T4_span1_left",
            "name": "Target 4 (Span 1 Left - near Sensor #1)",
            "x": 350, "y": 460, "w": 64, "h": 64,
            "description": "Shaft top edge near Bearing Pedestal 1.",
            "sensor_relation": "Sensor #1 (Span 1 near bearing)",
        },
        {
            "id": "T5_span1_bottom",
            "name": "Target 5 (Span 1 Bottom Edge)",
            "x": 520, "y": 485, "w": 64, "h": 64,
            "description": "Shaft bottom edge in Span 1.",
            "sensor_relation": "Sensor #2 complementary edge",
        },
        {
            "id": "T6_rotating_surface",
            "name": "Target 6 (Rotating Surface Internal - Failure Case)",
            "x": 550, "y": 488, "w": 48, "h": 32,
            "description": "Inside shaft body without edge; texture rotates, testing phase correlation limits.",
            "sensor_relation": "Rotational texture failure test",
        },
    ],
    "anchors": [
        {
            "id": "A1_base_center",
            "name": "Anchor 1 (Base Center Mechanical Fixture)",
            "x": 600, "y": 560, "w": 64, "h": 64,
            "description": "Machine bed casting / fixture below shaft; texture std=29.2 px, high rigidity.",
        },
        {
            "id": "A2_pedestal1",
            "name": "Anchor 2 (Bearing Pedestal 1 Housing)",
            "x": 210, "y": 380, "w": 48, "h": 48,
            "description": "Rigid bearing housing 1; texture std=24.2 px.",
        },
        {
            "id": "A3_pedestal2",
            "name": "Anchor 3 (Bearing Pedestal 2 Housing)",
            "x": 910, "y": 440, "w": 48, "h": 48,
            "description": "Rigid bearing housing 2; texture std=38.1 px.",
        },
    ]
}

def annotate_rois():
    frame_path = REPORTS_DIR / "extracted_frames" / "1000rpm-Unb1_frame_first.jpg"
    img = cv2.imread(str(frame_path))
    h, w, _ = img.shape
    vis = img.copy()

    # Draw sensor location approximations along the top
    sensor_x_map = {
        "Sensor #1": 350,
        "Sensor #2": 520,
        "Sensor #3": 720,
        "Sensor #4": 820,
    }
    for s_name, sx in sensor_x_map.items():
        cv2.line(vis, (sx, 350), (sx, 450), (255, 0, 255), 2)
        cv2.putText(vis, s_name, (sx - 35, 340), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 2)

    # Draw Target ROIs (Cyan / Blue)
    for t in CANDIDATE_ROIS["targets"]:
        color = (0, 0, 255) if "Failure" in t["name"] else (255, 255, 0)
        cv2.rectangle(vis, (t["x"], t["y"]), (t["x"] + t["w"], t["y"] + t["h"]), color, 2)
        label = t["id"].split("_")[0]
        cv2.putText(vis, label, (t["x"] + 2, t["y"] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

    # Draw Anchor ROIs (Green)
    for a in CANDIDATE_ROIS["anchors"]:
        cv2.rectangle(vis, (a["x"], a["y"]), (a["x"] + a["w"], a["y"] + a["h"]), (0, 255, 0), 2)
        label = a["id"].split("_")[0]
        cv2.putText(vis, label, (a["x"] + 2, a["y"] - 6), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)

    # Add legend at top left
    cv2.rectangle(vis, (15, 15), (420, 140), (20, 20, 20), -1)
    cv2.putText(vis, "ROI Candidate Map (1000rpm-Unb1)", (25, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
    cv2.putText(vis, "Cyan: Candidate Target ROIs (T1-T5)", (25, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)
    cv2.putText(vis, "Red: Negative Failure Test Target (T6)", (25, 85), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 1)
    cv2.putText(vis, "Green: Candidate Anchor ROIs (A1-A3)", (25, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    cv2.putText(vis, "Magenta: Physical Sensor Proximity Planes", (25, 125), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 0, 255), 1)

    out_img_path = REPORTS_DIR / "roi_selection_annotated.png"
    cv2.imwrite(str(out_img_path), vis)
    print(f"Saved annotated ROI image to {out_img_path}")

    # Save JSON metadata
    out_json = REPORTS_DIR / "candidate_rois.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(CANDIDATE_ROIS, f, indent=2)
    print(f"Saved candidate ROIs JSON to {out_json}")

if __name__ == "__main__":
    annotate_rois()
