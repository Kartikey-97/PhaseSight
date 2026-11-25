from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from phasesight.tracker import MotionSample


@dataclass(frozen=True)
class BufferSnapshot:
    """Contiguous chronologically ordered snapshot of rolling motion samples."""

    timestamps_s: np.ndarray
    target_dx_px: np.ndarray
    target_dy_px: np.ndarray
    anchor_dx_px: np.ndarray
    anchor_dy_px: np.ndarray
    relative_dx_px: np.ndarray
    relative_dy_px: np.ndarray
    target_response: np.ndarray
    anchor_response: np.ndarray
    valid: np.ndarray
    count: int
    capacity: int
    valid_count: int
    valid_ratio: float
    total_samples_seen: int


class RollingMotionBuffer:
    """Pre-allocated circular ring buffer for motion tracking samples."""

    def __init__(self, capacity: int = 512) -> None:
        if capacity < 1:
            raise ValueError("Buffer capacity must be at least 1")
        self.capacity = int(capacity)
        self._head = 0
        self._count = 0
        self._total_samples_seen = 0

        self._timestamps_s = np.zeros(self.capacity, dtype=np.float64)
        self._target_dx_px = np.zeros(self.capacity, dtype=np.float64)
        self._target_dy_px = np.zeros(self.capacity, dtype=np.float64)
        self._anchor_dx_px = np.zeros(self.capacity, dtype=np.float64)
        self._anchor_dy_px = np.zeros(self.capacity, dtype=np.float64)
        self._relative_dx_px = np.zeros(self.capacity, dtype=np.float64)
        self._relative_dy_px = np.zeros(self.capacity, dtype=np.float64)
        self._target_response = np.zeros(self.capacity, dtype=np.float64)
        self._anchor_response = np.zeros(self.capacity, dtype=np.float64)
        self._valid = np.zeros(self.capacity, dtype=bool)

    def append(self, sample: MotionSample) -> None:
        """Insert a sample into the circular buffer in O(1) time."""
        idx = self._head
        self._timestamps_s[idx] = float(sample.timestamp_s)
        self._target_dx_px[idx] = float(sample.target_dx_px)
        self._target_dy_px[idx] = float(sample.target_dy_px)
        self._anchor_dx_px[idx] = float(sample.anchor_dx_px)
        self._anchor_dy_px[idx] = float(sample.anchor_dy_px)
        self._relative_dx_px[idx] = float(sample.relative_dx_px)
        self._relative_dy_px[idx] = float(sample.relative_dy_px)
        self._target_response[idx] = float(sample.target_response)
        self._anchor_response[idx] = float(sample.anchor_response)
        self._valid[idx] = bool(sample.valid)

        self._head = (self._head + 1) % self.capacity
        if self._count < self.capacity:
            self._count += 1
        self._total_samples_seen += 1

    def clear(self) -> None:
        """Clear all stored samples from the buffer."""
        self._head = 0
        self._count = 0

    def snapshot(self, max_samples: int | None = None) -> BufferSnapshot:
        """Extract a contiguous chronologically ordered snapshot."""
        if self._count == 0:
            empty_f = np.empty(0, dtype=np.float64)
            empty_b = np.empty(0, dtype=bool)
            return BufferSnapshot(
                timestamps_s=empty_f,
                target_dx_px=empty_f,
                target_dy_px=empty_f,
                anchor_dx_px=empty_f,
                anchor_dy_px=empty_f,
                relative_dx_px=empty_f,
                relative_dy_px=empty_f,
                target_response=empty_f,
                anchor_response=empty_f,
                valid=empty_b,
                count=0,
                capacity=self.capacity,
                valid_count=0,
                valid_ratio=0.0,
                total_samples_seen=self._total_samples_seen,
            )

        if self._count < self.capacity:
            indices = np.arange(0, self._count)
        else:
            indices = (self._head + np.arange(self.capacity)) % self.capacity

        if max_samples is not None and max_samples < len(indices):
            indices = indices[-max_samples:]

        timestamps = np.ascontiguousarray(self._timestamps_s[indices])
        target_dx = np.ascontiguousarray(self._target_dx_px[indices])
        target_dy = np.ascontiguousarray(self._target_dy_px[indices])
        anchor_dx = np.ascontiguousarray(self._anchor_dx_px[indices])
        anchor_dy = np.ascontiguousarray(self._anchor_dy_px[indices])
        relative_dx = np.ascontiguousarray(self._relative_dx_px[indices])
        relative_dy = np.ascontiguousarray(self._relative_dy_px[indices])
        target_resp = np.ascontiguousarray(self._target_response[indices])
        anchor_resp = np.ascontiguousarray(self._anchor_response[indices])
        valid = np.ascontiguousarray(self._valid[indices])

        n = len(indices)
        valid_count = int(np.sum(valid))
        valid_ratio = float(valid_count / n) if n > 0 else 0.0

        return BufferSnapshot(
            timestamps_s=timestamps,
            target_dx_px=target_dx,
            target_dy_px=target_dy,
            anchor_dx_px=anchor_dx,
            anchor_dy_px=anchor_dy,
            relative_dx_px=relative_dx,
            relative_dy_px=relative_dy,
            target_response=target_resp,
            anchor_response=anchor_resp,
            valid=valid,
            count=n,
            capacity=self.capacity,
            valid_count=valid_count,
            valid_ratio=valid_ratio,
            total_samples_seen=self._total_samples_seen,
        )

    def __len__(self) -> int:
        return self._count
