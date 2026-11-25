from __future__ import annotations

from pathlib import Path
import threading
import time
from typing import Any

import cv2
import numpy as np

from phasesight.monitoring.session import MonitoringSession


class PacedVideoReplayAdapter:
    """Streams frames from a video file into a MonitoringSession paced to real time."""

    def __init__(
        self,
        video_path: str | Path,
        session: MonitoringSession,
        *,
        fps_override: float | None = None,
        playback_rate: float = 1.0,
        loop: bool = False,
    ) -> None:
        self.video_path = Path(video_path)
        if not self.video_path.is_file():
            raise FileNotFoundError(f"Video file not found: {self.video_path}")

        self.session = session
        self.fps_override = float(fps_override) if fps_override is not None else None
        self.playback_rate = max(0.001, float(playback_rate))
        self.loop = bool(loop)

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._latest_frame: np.ndarray | None = None
        self._eof_reached = False

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def eof_reached(self) -> bool:
        return self._eof_reached

    def start(self) -> None:
        """Start paced video replay in a background daemon thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._eof_reached = False
        self._thread = threading.Thread(
            target=self._run_loop, name="PacedVideoReplayAdapter", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        """Signal thread to stop and wait for termination."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def get_latest_frame_jpeg(self, quality: int = 75) -> bytes | None:
        """Encode the most recent frame as JPEG bytes for preview."""
        with self._lock:
            if self._latest_frame is None:
                return None
            frame = self._latest_frame.copy()

        ret, buf = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), int(quality)]
        )
        return buf.tobytes() if ret else None

    def _run_loop(self) -> None:
        cap = cv2.VideoCapture(str(self.video_path))
        if not cap.isOpened():
            self._eof_reached = True
            return

        fps_container = float(cap.get(cv2.CAP_PROP_FPS))
        if self.fps_override is not None:
            effective_fps = self.fps_override
        elif fps_container > 0 and np.isfinite(fps_container):
            effective_fps = fps_container
        else:
            effective_fps = 30.0

        frame_idx = 0
        time_offset = 0.0
        prev_sim_t = 0.0
        prev_pts_msec = 0.0
        wall_start = time.perf_counter()
        initial_sim_t: float | None = None

        try:
            while not self._stop_event.is_set():
                ret, frame = cap.read()
                if not ret or frame is None:
                    if self.loop:
                        time_offset = prev_sim_t + (1.0 / effective_fps)
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        frame_idx = 0
                        prev_pts_msec = 0.0
                        continue
                    else:
                        self._eof_reached = True
                        break

                if self.fps_override is not None:
                    t_sim = time_offset + (frame_idx / effective_fps)
                else:
                    pos_msec = float(cap.get(cv2.CAP_PROP_POS_MSEC))
                    if pos_msec > 0 and pos_msec > prev_pts_msec:
                        prev_pts_msec = pos_msec
                        t_sim = time_offset + (pos_msec / 1000.0)
                    else:
                        t_sim = time_offset + (frame_idx / effective_fps)

                if initial_sim_t is None:
                    initial_sim_t = t_sim

                prev_sim_t = t_sim
                frame_idx += 1

                with self._lock:
                    self._latest_frame = frame

                self.session.ingest_frame(frame, t_sim)

                # Pacing control
                sim_elapsed = t_sim - initial_sim_t
                target_wall_elapsed = sim_elapsed / self.playback_rate
                current_wall_elapsed = time.perf_counter() - wall_start
                sleep_sec = target_wall_elapsed - current_wall_elapsed
                if sleep_sec > 0.0005:
                    if self._stop_event.wait(timeout=sleep_sec):
                        break

        finally:
            cap.release()
