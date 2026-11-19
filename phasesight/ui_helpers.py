from __future__ import annotations

import csv
import os
from pathlib import Path
import tempfile
from typing import Any

import cv2
import numpy as np

# Ensure headless Matplotlib does not complain about sandbox cache directory
os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .analysis import analyse_displacement
from .storage import RunArrays
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


def status_badge(status: str) -> str:
    """Return colored status badge markdown string."""
    s = status.strip()
    if s == "Normal":
        return "🟢 Normal"
    elif s == "Review":
        return "🔴 Review"
    elif s == "Low confidence":
        return "🟡 Low confidence"
    elif s == "Unassessed":
        return "⚪ Unassessed"
    return f"⚪ {status}"


def sync_active_asset_rois(asset: Any | None) -> None:
    """Synchronize session state ROI coordinates and FPS from the active asset."""
    import streamlit as st

    if asset is not None:
        t_roi = asset.target_roi
        a_roi = asset.anchor_roi
        st.session_state["tx_input"] = int(t_roi["x"])
        st.session_state["ty_input"] = int(t_roi["y"])
        st.session_state["tw_input"] = int(t_roi["width"])
        st.session_state["th_input"] = int(t_roi["height"])
        st.session_state["ax_input"] = int(a_roi["x"])
        st.session_state["ay_input"] = int(a_roi["y"])
        st.session_state["aw_input"] = int(a_roi["width"])
        st.session_state["ah_input"] = int(a_roi["height"])
        st.session_state["fps_override_val"] = float(asset.expected_fps)
    else:
        st.session_state["tx_input"] = int(DEFAULT_SAMPLE_TARGET_ROI.x)
        st.session_state["ty_input"] = int(DEFAULT_SAMPLE_TARGET_ROI.y)
        st.session_state["tw_input"] = int(DEFAULT_SAMPLE_TARGET_ROI.width)
        st.session_state["th_input"] = int(DEFAULT_SAMPLE_TARGET_ROI.height)
        st.session_state["ax_input"] = int(DEFAULT_SAMPLE_ANCHOR_ROI.x)
        st.session_state["ay_input"] = int(DEFAULT_SAMPLE_ANCHOR_ROI.y)
        st.session_state["aw_input"] = int(DEFAULT_SAMPLE_ANCHOR_ROI.width)
        st.session_state["ah_input"] = int(DEFAULT_SAMPLE_ANCHOR_ROI.height)
        st.session_state["fps_override_val"] = 60.0


def run_arrays_from_csv(
    csv_path: str | Path,
    fps: float = 60.0,
    compute_spectra: bool = True,
) -> RunArrays:
    """Construct RunArrays instance from motion CSV file."""
    path = Path(csv_path)
    if not path.is_file():
        raise FileNotFoundError(f"Motion CSV file not found: {path}")

    timestamps: list[float] = []
    target_dx: list[float] = []
    target_dy: list[float] = []
    anchor_dx: list[float] = []
    anchor_dy: list[float] = []
    relative_dx: list[float] = []
    relative_dy: list[float] = []
    target_resp: list[float] = []
    anchor_resp: list[float] = []

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            timestamps.append(float(row["timestamp_s"]))
            target_dx.append(float(row["target_dx_px"]))
            target_dy.append(float(row["target_dy_px"]))
            anchor_dx.append(float(row["anchor_dx_px"]))
            anchor_dy.append(float(row["anchor_dy_px"]))
            relative_dx.append(float(row["relative_dx_px"]))
            relative_dy.append(float(row["relative_dy_px"]))
            target_resp.append(float(row["target_response"]))
            anchor_resp.append(float(row["anchor_response"]))

    t_arr = np.asarray(timestamps, dtype=np.float64)
    rel_dx_arr = np.asarray(relative_dx, dtype=np.float64)
    rel_dy_arr = np.asarray(relative_dy, dtype=np.float64)

    x_freqs = None
    x_psd = None
    y_freqs = None
    y_psd = None

    if compute_spectra and len(t_arr) >= 32:
        try:
            res_x = analyse_displacement(t_arr, rel_dx_arr)
            x_freqs = res_x.frequencies_hz
            x_psd = res_x.psd_px2_per_hz
        except Exception:
            pass

        try:
            res_y = analyse_displacement(t_arr, rel_dy_arr)
            y_freqs = res_y.frequencies_hz
            y_psd = res_y.psd_px2_per_hz
        except Exception:
            pass

    return RunArrays(
        timestamps_s=t_arr,
        relative_dx_px=rel_dx_arr,
        relative_dy_px=rel_dy_arr,
        target_dx_px=np.asarray(target_dx, dtype=np.float64),
        target_dy_px=np.asarray(target_dy, dtype=np.float64),
        anchor_dx_px=np.asarray(anchor_dx, dtype=np.float64),
        anchor_dy_px=np.asarray(anchor_dy, dtype=np.float64),
        target_response=np.asarray(target_resp, dtype=np.float64),
        anchor_response=np.asarray(anchor_resp, dtype=np.float64),
        x_frequencies_hz=x_freqs,
        x_psd_px2_per_hz=x_psd,
        y_frequencies_hz=y_freqs,
        y_psd_px2_per_hz=y_psd,
    )


def plot_run_arrays(arrays: RunArrays, title: str | None = None) -> plt.Figure:
    """Generate a 2-panel Matplotlib figure for RunArrays (time series and Welch PSD)."""
    fig, (ax_time, ax_psd) = plt.subplots(2, 1, figsize=(9, 6), constrained_layout=True, dpi=140)

    # Panel 1: Time series
    t = arrays.timestamps_s
    ax_time.plot(t, arrays.relative_dx_px, label="Relative dx (X)", color="#1f77b4", lw=1.2)
    ax_time.plot(t, arrays.relative_dy_px, label="Relative dy (Y)", color="#ff7f0e", lw=1.0, alpha=0.85)
    ax_time.set_ylabel("Displacement (px)")
    ax_time.set_xlabel("Time (s)")
    ax_time.grid(True, linestyle="--", alpha=0.5)
    ax_time.legend(loc="upper right", frameon=True)
    if title:
        ax_time.set_title(title, fontsize=11, fontweight="bold")
    else:
        ax_time.set_title("Relative Machine Displacement", fontsize=11, fontweight="bold")

    # Panel 2: Power Spectral Density
    if arrays.x_frequencies_hz is not None and arrays.x_psd_px2_per_hz is not None:
        ax_psd.semilogy(
            arrays.x_frequencies_hz,
            arrays.x_psd_px2_per_hz,
            label="X PSD",
            color="#1f77b4",
            lw=1.3,
        )
    if arrays.y_frequencies_hz is not None and arrays.y_psd_px2_per_hz is not None:
        ax_psd.semilogy(
            arrays.y_frequencies_hz,
            arrays.y_psd_px2_per_hz,
            label="Y PSD",
            color="#ff7f0e",
            lw=1.1,
            alpha=0.85,
        )

    ax_psd.set_ylabel("PSD (px²/Hz)")
    ax_psd.set_xlabel("Frequency (Hz)")
    ax_psd.grid(True, which="both", linestyle="--", alpha=0.5)
    if (arrays.x_frequencies_hz is not None and arrays.x_psd_px2_per_hz is not None) or (
        arrays.y_frequencies_hz is not None and arrays.y_psd_px2_per_hz is not None
    ):
        ax_psd.legend(loc="upper right", frameon=True)
    ax_psd.set_title("Welch Power Spectral Density", fontsize=11, fontweight="bold")

    return fig
