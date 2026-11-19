"""Live webcam acquisition, dropped frame detection, and timing regularity verification.

Provides bounded live buffer acquisition from physical UVC webcams or deterministic
synthetic mock streams, records monotonic arrival timestamps (time.perf_counter()),
detects dropped frames and severe stalls, quantifies timestamp jitter, and evaluates
sampling stability prior to downstream vibration screening.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import datetime
import os
from pathlib import Path
import time
from typing import Any, Callable

import cv2
import numpy as np

from phasesight.synthetic import SyntheticConfig, make_scene

VALID_STABILITY_STATUSES = ("STABLE", "WARNING_JITTER", "REJECTED_UNSTABLE")


@dataclass(frozen=True)
class CaptureStabilityReport:
    """Quantitative frame-rate stability and dropped frame audit report."""

    total_frames: int
    duration_s: float
    nominal_fps: float
    measured_fps: float
    median_dt_s: float
    mean_dt_s: float
    std_dt_s: float
    min_dt_s: float
    max_dt_s: float
    jitter_ratio: float  # std(dt) / median(dt)
    robust_jitter_ratio: float  # 1.4826 * MAD(dt) / median(dt)
    dropped_frames_count: int
    dropped_frame_indices: list[int] = field(default_factory=list)
    large_gap_count: int = 0  # intervals > 2.5 * median(dt)
    status: str = "STABLE"
    status_reasons: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.status not in VALID_STABILITY_STATUSES:
            raise ValueError(
                f"Invalid status '{self.status}'. Must be one of {VALID_STABILITY_STATUSES}"
            )

    def to_dict(self) -> dict[str, Any]:
        """Convert report to JSON-compatible dictionary."""
        return asdict(self)


@dataclass
class CaptureResult:
    """Container holding buffered video frames, timestamps, and stability audit."""

    frames: np.ndarray  # Shape (N, H, W, 3) uint8
    timestamps_s: np.ndarray  # 1D float64
    stability: CaptureStabilityReport
    video_path: Path | None = None


def calculate_timestamp_stability(
    timestamps_s: np.ndarray | list[float],
    nominal_fps: float = 30.0,
    *,
    warning_jitter_threshold: float = 0.05,
    reject_jitter_threshold: float = 0.15,
    max_tolerated_dropped_frames: int = 3,
) -> CaptureStabilityReport:
    """Quantify timestamp regularity, dropped frames, and acquisition stability.

    Parameters
    ----------
    timestamps_s : np.ndarray | list[float]
        Monotonically increasing arrival timestamps in seconds starting at 0.0.
    nominal_fps : float
        Requested nominal or metadata frame rate.
    warning_jitter_threshold : float
        Jitter ratio (std/median) threshold flagging WARNING_JITTER (default 0.05 / 5%).
    reject_jitter_threshold : float
        Jitter ratio threshold flagging REJECTED_UNSTABLE (default 0.15 / 15%).
    max_tolerated_dropped_frames : int
        Maximum allowable dropped frames before flagging REJECTED_UNSTABLE (default 3).
    """
    t = np.asarray(timestamps_s, dtype=np.float64)
    n_frames = len(t)
    duration = float(t[-1] - t[0]) if n_frames > 1 else 0.0

    # Minimum frames check
    if n_frames < 32:
        return CaptureStabilityReport(
            total_frames=n_frames,
            duration_s=duration,
            nominal_fps=float(nominal_fps),
            measured_fps=0.0,
            median_dt_s=0.0,
            mean_dt_s=0.0,
            std_dt_s=0.0,
            min_dt_s=0.0,
            max_dt_s=0.0,
            jitter_ratio=0.0,
            robust_jitter_ratio=0.0,
            dropped_frames_count=0,
            dropped_frame_indices=[],
            large_gap_count=0,
            status="REJECTED_UNSTABLE",
            status_reasons=[
                f"Too few frames captured ({n_frames}): minimum 32 frames required for spectral analysis."
            ],
        )

    dt = np.diff(t)

    # Monotonicity check
    if np.any(dt <= 0):
        return CaptureStabilityReport(
            total_frames=n_frames,
            duration_s=duration,
            nominal_fps=float(nominal_fps),
            measured_fps=0.0,
            median_dt_s=0.0,
            mean_dt_s=0.0,
            std_dt_s=0.0,
            min_dt_s=0.0,
            max_dt_s=0.0,
            jitter_ratio=0.0,
            robust_jitter_ratio=0.0,
            dropped_frames_count=0,
            dropped_frame_indices=[],
            large_gap_count=0,
            status="REJECTED_UNSTABLE",
            status_reasons=[
                "Non-monotonic timestamps detected: frame arrival timestamps must be strictly increasing."
            ],
        )

    median_dt = float(np.median(dt))
    mean_dt = float(np.mean(dt))
    std_dt = float(np.std(dt))
    min_dt = float(np.min(dt))
    max_dt = float(np.max(dt))

    measured_fps = (1.0 / median_dt) if median_dt > 0 else 0.0
    jitter_ratio = (std_dt / median_dt) if median_dt > 0 else 0.0

    # Robust MAD calculation: scale factor 1.4826 for normal consistency
    mad_dt = float(np.median(np.abs(dt - median_dt)))
    robust_jitter_ratio = (1.482602218505602 * mad_dt / median_dt) if median_dt > 0 else 0.0

    # Dropped frame detection (gaps > 1.5x median dt)
    drop_indices: list[int] = []
    dropped_count = 0
    large_gaps = 0

    for idx, delta in enumerate(dt):
        ratio = delta / median_dt if median_dt > 0 else 1.0
        if ratio > 1.5:
            est_drops = int(round(ratio)) - 1
            if est_drops > 0:
                dropped_count += est_drops
                drop_indices.append(idx)
        if ratio > 2.5:
            large_gaps += 1

    # Continuous jitter evaluation (excluding dropped frame gaps)
    non_drop_dt = [delta for delta in dt if delta <= 1.5 * median_dt]
    clean_jitter_ratio = (float(np.std(non_drop_dt)) / median_dt) if non_drop_dt and median_dt > 0 else jitter_ratio
    effective_jitter = min(jitter_ratio, max(clean_jitter_ratio, robust_jitter_ratio))

    # Stability classification
    reasons: list[str] = []
    is_rejected = False

    if dropped_count > max_tolerated_dropped_frames:
        is_rejected = True
        reasons.append(
            f"Excessive dropped frames: {dropped_count} frames dropped (> {max_tolerated_dropped_frames} tolerated limit)."
        )

    if large_gaps > 0:
        is_rejected = True
        reasons.append(
            f"Severe acquisition stalls detected: {large_gaps} inter-frame gap(s) exceeded 2.5x median interval ({2.5 * median_dt:.4f}s)."
        )

    if effective_jitter >= reject_jitter_threshold:
        is_rejected = True
        reasons.append(
            f"Severe timestamp jitter: {effective_jitter * 100:.1f}% exceeds rejection limit ({reject_jitter_threshold * 100:.1f}%)."
        )

    if is_rejected:
        status = "REJECTED_UNSTABLE"
    elif effective_jitter >= warning_jitter_threshold or dropped_count > 0:
        status = "WARNING_JITTER"
        if effective_jitter >= warning_jitter_threshold:
            reasons.append(
                f"Moderate timestamp jitter: {effective_jitter * 100:.1f}% exceeds warning limit ({warning_jitter_threshold * 100:.1f}%)."
            )
        if dropped_count > 0:
            reasons.append(
                f"Dropped frames detected: {dropped_count} frames missing during acquisition."
            )
    else:
        status = "STABLE"

    return CaptureStabilityReport(
        total_frames=n_frames,
        duration_s=duration,
        nominal_fps=float(nominal_fps),
        measured_fps=measured_fps,
        median_dt_s=median_dt,
        mean_dt_s=mean_dt,
        std_dt_s=std_dt,
        min_dt_s=min_dt,
        max_dt_s=max_dt,
        jitter_ratio=jitter_ratio,
        robust_jitter_ratio=robust_jitter_ratio,
        dropped_frames_count=dropped_count,
        dropped_frame_indices=drop_indices,
        large_gap_count=large_gaps,
        status=status,
        status_reasons=reasons,
    )


# Alias per plan specification
evaluate_timing_stability = calculate_timestamp_stability


class MockVideoCapture:
    """Duck-typed OpenCV VideoCapture generating deterministic synthetic frames."""

    def __init__(
        self,
        frames: np.ndarray | None = None,
        fps: float = 30.0,
        drop_indices: set[int] | None = None,
        jitter_ms: float = 0.0,
        seed: int = 42,
        num_synthetic_frames: int = 150,
        width: int = 640,
        height: int = 360,
    ) -> None:
        self.fps = float(fps)
        self.drop_indices = set(drop_indices or [])
        self.jitter_ms = float(jitter_ms)
        self.index = 0
        self.opened = True

        if frames is None:
            synth_duration = max(1.0, float(num_synthetic_frames) / float(fps))
            config = SyntheticConfig(
                fps=int(self.fps),
                duration_s=synth_duration,
                width=width,
                height=height,
                vibration_frequency_hz=8.5,
                vibration_amplitude_px=0.35,
                seed=seed,
            )
            raw_frames, _ = make_scene(config)
            self.frames = raw_frames[:num_synthetic_frames]
        else:
            self.frames = frames

        if self.frames.ndim != 4:
            raise ValueError(f"Mock frames must have 4 dimensions (N, H, W, C), got {self.frames.ndim}")

    def isOpened(self) -> bool:
        return self.opened

    def read(self) -> tuple[bool, np.ndarray | None]:
        if not self.opened or self.index >= len(self.frames):
            return False, None

        if self.index in self.drop_indices:
            self.index += 1
            if self.index >= len(self.frames):
                return False, None

        frame = self.frames[self.index].copy()
        self.index += 1
        return True, frame

    def get(self, prop_id: int) -> float:
        if prop_id == cv2.CAP_PROP_FRAME_WIDTH:
            return float(self.frames.shape[2])
        if prop_id == cv2.CAP_PROP_FRAME_HEIGHT:
            return float(self.frames.shape[1])
        if prop_id == cv2.CAP_PROP_FPS:
            return self.fps
        if prop_id == cv2.CAP_PROP_FRAME_COUNT:
            return float(len(self.frames))
        if prop_id == cv2.CAP_PROP_POS_FRAMES:
            return float(self.index)
        return 0.0

    def set(self, prop_id: int, value: float) -> bool:
        if prop_id == cv2.CAP_PROP_POS_FRAMES:
            self.index = int(value)
            return True
        return True

    def release(self) -> None:
        self.opened = False


def open_capture_source(
    source: int | str | Path | Any, fps: float = 30.0
) -> cv2.VideoCapture | MockVideoCapture:
    """Open capture device, mock stream, or video file.

    Parameters
    ----------
    source : int | str | Path | Any
        Camera index (0, 1), device string, file path, or 'mock:0'.
    fps : float
        Nominal FPS for mock capture devices.
    """
    src_str = str(source).strip()

    if src_str.lower().startswith("mock"):
        return MockVideoCapture(fps=fps)

    if src_str.isdigit():
        cap = cv2.VideoCapture(int(src_str))
    else:
        try:
            val = int(source)
            cap = cv2.VideoCapture(val)
        except (ValueError, TypeError):
            cap = cv2.VideoCapture(src_str)

    if not cap.isOpened():
        raise RuntimeError(
            f"Could not open video capture source '{source}'. "
            f"If attempting to access a live camera on macOS, ensure Camera permissions are granted "
            f"in System Settings -> Privacy & Security -> Camera."
        )

    return cap


def grab_preview_frame(
    source: int | str | Path | Any, warmup_frames: int = 2
) -> np.ndarray:
    """Grab a single preview frame from source, flushing OS driver buffer lag."""
    cap = open_capture_source(source)
    try:
        # Flush driver buffer
        for _ in range(max(1, warmup_frames)):
            ok, _ = cap.read()
            if not ok:
                break

        ok, frame = cap.read()
        if not ok or frame is None or frame.size == 0:
            raise RuntimeError(f"Failed to grab preview frame from capture source '{source}'.")
        return frame
    finally:
        cap.release()


def capture_live_clip(
    source: int | str | Path | Any,
    duration_s: float = 5.0,
    target_fps: float | None = 30.0,
    output_path: str | Path | None = None,
    progress_callback: Callable[[float], None] | None = None,
    stop_event: Any | None = None,
) -> CaptureResult:
    """Acquire a bounded live video buffer with monotonic timestamping and stability analysis.

    Parameters
    ----------
    source : int | str | Path | Any
        Camera index, video file, or 'mock:0'.
    duration_s : float
        Capture window in seconds.
    target_fps : float | None
        Target frame rate (default 30.0).
    output_path : str | Path | None
        Optional destination MP4 file path.
    progress_callback : Callable[[float], None] | None
        Callback receiving completion fraction [0.0, 1.0].
    stop_event : threading.Event | None
        Optional cooperative cancellation event.
    """
    nom_fps = target_fps or 30.0
    cap = open_capture_source(source, fps=nom_fps)
    is_mock = isinstance(cap, MockVideoCapture)

    frames: list[np.ndarray] = []
    timestamps: list[float] = []

    try:
        # Flush buffer
        for _ in range(2):
            ok, _ = cap.read()
            if not ok:
                break

        # Start timed acquisition
        t0 = time.perf_counter()
        timestamps.append(0.0)

        ok, first_frame = cap.read()
        if not ok or first_frame is None:
            raise RuntimeError(f"Could not read initial frame from source '{source}'.")
        frames.append(first_frame)

        while (stop_event is None or not stop_event.is_set()):
            if not is_mock and ((time.perf_counter() - t0) >= duration_s):
                break
            if is_mock and (len(frames) * (1.0 / nom_fps) >= duration_s):
                break

            ok, frame = cap.read()
            if not ok or frame is None:
                break

            if is_mock:
                dt_nom = 1.0 / nom_fps
                jitter = float(np.random.normal(0, cap.jitter_ms / 1000.0)) if cap.jitter_ms > 0 else 0.0
                now = len(frames) * dt_nom + jitter
            else:
                now = time.perf_counter() - t0

            frames.append(frame)
            timestamps.append(now)

            if progress_callback is not None:
                pct = min(1.0, max(0.0, now / duration_s))
                progress_callback(pct)

        if progress_callback is not None:
            progress_callback(1.0)

    finally:
        cap.release()

    frame_arr = np.asarray(frames)
    t_arr = np.asarray(timestamps, dtype=np.float64)

    stability = calculate_timestamp_stability(t_arr, nominal_fps=nom_fps)

    out_file = None
    if output_path is not None and len(frames) > 0:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        h, w = frames[0].shape[:2]
        if 1.0 <= stability.measured_fps <= 120.0:
            fps_to_write = float(round(stability.measured_fps, 2))
        else:
            fps_to_write = float(nom_fps)

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_file), fourcc, float(fps_to_write), (w, h))
        try:
            for f in frames:
                writer.write(f)
        finally:
            writer.release()

    return CaptureResult(
        frames=frame_arr,
        timestamps_s=t_arr,
        stability=stability,
        video_path=out_file,
    )
