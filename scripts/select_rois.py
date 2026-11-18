#!/usr/bin/env python3
"""Open a video frame and let the user select target and static anchor ROIs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("video", type=Path)
    parser.add_argument("--output", type=Path, default=Path("rois.json"))
    args = parser.parse_args()

    cap = cv2.VideoCapture(str(args.video))
    if not cap.isOpened():
        raise SystemExit(f"Could not open {args.video}")
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit("Could not read first frame")

    print("Select a box around a stationary, textured part of the MACHINE. Press ENTER/SPACE to confirm.")
    target = cv2.selectROI("Select TARGET ROI", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyWindow("Select TARGET ROI")
    print("Select a separate, stationary BACKGROUND/ANCHOR region (wall, pillar, rigid frame).")
    anchor = cv2.selectROI("Select ANCHOR ROI", frame, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()

    target = tuple(int(v) for v in target)
    anchor = tuple(int(v) for v in anchor)
    if target[2] < 32 or target[3] < 32 or anchor[2] < 32 or anchor[3] < 32:
        raise SystemExit("Both boxes must be at least 32x32 pixels")
    args.output.write_text(
        json.dumps({"target_roi": target, "anchor_roi": anchor}, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {args.output}")
    print(f"TARGET: {','.join(map(str, target))}")
    print(f"ANCHOR: {','.join(map(str, anchor))}")


if __name__ == "__main__":
    main()
