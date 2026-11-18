from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .tracker import ROI

SAMPLE_VIDEOS = {
    "Baseline clip (8.5 Hz reference target)": Path("data/portable/baseline.mp4"),
    "Changed clip (8.5 Hz + 2x harmonic)": Path("data/portable/changed.mp4"),
    "Camera-only clip (null control)": Path("data/portable/camera_only.mp4"),
}

DEFAULT_SAMPLE_TARGET_ROI = ROI(360, 110, 160, 160)
DEFAULT_SAMPLE_ANCHOR_ROI = ROI(60, 100, 160, 160)


def get_video_metadata(video_path: str | Path) -> dict[str, Any]:
    """Retrieve video dimensions, FPS, and frame count."""
    path_str = str(video_path)
    cap = cv2.VideoCapture(path_str)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        return {
            "path": path_str,
            "width": width,
            "height": height,
            "fps": fps,
            "frame_count": frame_count,
            "duration_s": (frame_count / fps) if (fps > 0 and frame_count > 0) else 0.0,
        }
    finally:
        cap.release()


def read_first_frame(video_path: str | Path) -> np.ndarray:
    """Read the first frame from a video file."""
    path_str = str(video_path)
    cap = cv2.VideoCapture(path_str)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    try:
        ok, frame = cap.read()
        if not ok or frame is None or frame.size == 0:
            raise RuntimeError(f"Could not read first frame from: {video_path}")
        return frame
    finally:
        cap.release()
