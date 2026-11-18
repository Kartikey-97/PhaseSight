from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import cv2
import numpy as np


@dataclass(frozen=True)
class ROI:
    """A rectangular region in x, y, width, height order."""

    x: int
    y: int
    width: int
    height: int

    def validate(self, frame_shape: Sequence[int], *, name: str) -> None:
        h, w = int(frame_shape[0]), int(frame_shape[1])
        if self.width < 32 or self.height < 32:
            raise ValueError(f"{name} must be at least 32x32 pixels")
        if self.x < 0 or self.y < 0 or self.x + self.width > w or self.y + self.height > h:
            raise ValueError(f"{name} lies outside the frame dimensions {w}x{h}")

    def crop(self, frame: np.ndarray) -> np.ndarray:
        return frame[self.y : self.y + self.height, self.x : self.x + self.width]


@dataclass(frozen=True)
class MotionSample:
    timestamp_s: float
    target_dx_px: float
    target_dy_px: float
    anchor_dx_px: float
    anchor_dy_px: float
    relative_dx_px: float
    relative_dy_px: float
    target_response: float
    anchor_response: float


class PhaseCorrelationTracker:
    """Measure target translation relative to a static anchor ROI.

    This is deliberately a translation-only MVP. It does not estimate rotation,
    perspective change, or a calibrated physical displacement in millimetres.
    """

    def __init__(
        self,
        first_frame: np.ndarray,
        target_roi: ROI,
        anchor_roi: ROI,
    ) -> None:
        gray = to_gray_float(first_frame)
        target_roi.validate(gray.shape, name="target_roi")
        anchor_roi.validate(gray.shape, name="anchor_roi")
        if _rectangles_overlap(target_roi, anchor_roi):
            raise ValueError("Target ROI and anchor ROI should not overlap")

        self.target_roi = target_roi
        self.anchor_roi = anchor_roi
        self._frame_shape = gray.shape
        self._target_ref = np.ascontiguousarray(target_roi.crop(gray))
        self._anchor_ref = np.ascontiguousarray(anchor_roi.crop(gray))
        self._target_window = cv2.createHanningWindow(
            (target_roi.width, target_roi.height), cv2.CV_32F
        )
        self._anchor_window = cv2.createHanningWindow(
            (anchor_roi.width, anchor_roi.height), cv2.CV_32F
        )

    def process(self, frame: np.ndarray, timestamp_s: float) -> MotionSample:
        gray = to_gray_float(frame)
        if gray.shape != self._frame_shape:
            raise ValueError(
                f"Frame size changed from {self._frame_shape[::-1]} to {gray.shape[::-1]}"
            )
        if not np.isfinite(timestamp_s):
            raise ValueError("timestamp_s must be finite")

        target = _normalise_patch(self.target_roi.crop(gray))
        anchor = _normalise_patch(self.anchor_roi.crop(gray))

        # OpenCV returns the translation of src2 relative to src1. Fresh
        # buffers are passed because the phase-correlation implementation
        # applies its window to working image data; never expose references.
        (target_dx, target_dy), target_response = cv2.phaseCorrelate(
            _normalise_patch(self._target_ref), target, self._target_window
        )
        (anchor_dx, anchor_dy), anchor_response = cv2.phaseCorrelate(
            _normalise_patch(self._anchor_ref), anchor, self._anchor_window
        )

        return MotionSample(
            timestamp_s=float(timestamp_s),
            target_dx_px=float(target_dx),
            target_dy_px=float(target_dy),
            anchor_dx_px=float(anchor_dx),
            anchor_dy_px=float(anchor_dy),
            relative_dx_px=float(target_dx - anchor_dx),
            relative_dy_px=float(target_dy - anchor_dy),
            target_response=float(np.clip(target_response, 0.0, 1.0)),
            anchor_response=float(np.clip(anchor_response, 0.0, 1.0)),
        )



def _normalise_patch(patch: np.ndarray) -> np.ndarray:
    """Remove per-patch DC level and normalize contrast before registration."""
    result = np.asarray(patch, dtype=np.float32).copy()
    result -= float(np.mean(result))
    standard_deviation = float(np.std(result))
    if standard_deviation > 1e-6:
        result /= standard_deviation
    return np.ascontiguousarray(result)


def to_gray_float(frame: np.ndarray) -> np.ndarray:
    if frame is None or not isinstance(frame, np.ndarray):
        raise ValueError("frame must be a non-empty NumPy array")
    if frame.size == 0:
        raise ValueError("frame is empty")
    if frame.ndim == 3:
        if frame.shape[2] == 3:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        elif frame.shape[2] == 4:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2GRAY)
        else:
            raise ValueError("frame must have 1, 3 or 4 channels")
    elif frame.ndim != 2:
        raise ValueError("frame must be a 2D grayscale or 3D color image")
    return np.ascontiguousarray(frame.astype(np.float32, copy=False))


def _rectangles_overlap(a: ROI, b: ROI) -> bool:
    return not (
        a.x + a.width <= b.x
        or b.x + b.width <= a.x
        or a.y + a.height <= b.y
        or b.y + b.height <= a.y
    )


def check_roi_texture(frame: np.ndarray, roi: ROI, min_std: float = 2.0) -> tuple[bool, float]:
    """Check if an ROI in a frame has sufficient texture/contrast.

    Returns (has_texture, standard_deviation). Flat or near-monochrome regions
    fail this check because phase correlation requires spatial intensity variations.
    """
    gray = to_gray_float(frame)
    roi.validate(gray.shape, name="roi")
    patch = roi.crop(gray)
    std_dev = float(np.std(patch))
    return (std_dev >= min_std, std_dev)


def validate_rois(
    frame: np.ndarray,
    target_roi: ROI,
    anchor_roi: ROI,
    *,
    min_size: int = 32,
    min_texture_std: float = 2.0,
) -> list[str]:
    """Validate target and anchor ROIs against frame bounds, size, overlap, and texture.

    Returns a list of error messages. An empty list indicates valid ROIs.
    """
    errors: list[str] = []
    if frame is None or not isinstance(frame, np.ndarray) or frame.size == 0:
        return ["Frame is empty or invalid"]

    gray = to_gray_float(frame)
    h, w = gray.shape[:2]

    # Target ROI bounds & size
    if target_roi.width < min_size or target_roi.height < min_size:
        errors.append(
            f"Target ROI must be at least {min_size}x{min_size} pixels (got {target_roi.width}x{target_roi.height})"
        )
    if (
        target_roi.x < 0
        or target_roi.y < 0
        or target_roi.x + target_roi.width > w
        or target_roi.y + target_roi.height > h
    ):
        errors.append(f"Target ROI lies outside frame dimensions ({w}x{h})")

    # Anchor ROI bounds & size
    if anchor_roi.width < min_size or anchor_roi.height < min_size:
        errors.append(
            f"Anchor ROI must be at least {min_size}x{min_size} pixels (got {anchor_roi.width}x{anchor_roi.height})"
        )
    if (
        anchor_roi.x < 0
        or anchor_roi.y < 0
        or anchor_roi.x + anchor_roi.width > w
        or anchor_roi.y + anchor_roi.height > h
    ):
        errors.append(f"Anchor ROI lies outside frame dimensions ({w}x{h})")

    # Overlap check
    if not errors and _rectangles_overlap(target_roi, anchor_roi):
        errors.append("Target ROI and Anchor ROI must not overlap")

    # Texture checks (only if ROIs are within frame bounds)
    if not errors:
        target_patch = target_roi.crop(gray)
        target_std = float(np.std(target_patch))
        if target_std < min_texture_std:
            errors.append(
                f"Target ROI lacks visible texture/contrast (std={target_std:.2f} < {min_texture_std:.1f}); "
                "select a region with visible edges or texture"
            )

        anchor_patch = anchor_roi.crop(gray)
        anchor_std = float(np.std(anchor_patch))
        if anchor_std < min_texture_std:
            errors.append(
                f"Anchor ROI lacks visible texture/contrast (std={anchor_std:.2f} < {min_texture_std:.1f}); "
                "select a static region with visible edges or texture"
            )

    return errors


def draw_rois_on_frame(
    frame: np.ndarray,
    target_roi: ROI | None = None,
    anchor_roi: ROI | None = None,
) -> np.ndarray:
    """Draw target (green) and anchor (orange) bounding boxes on a frame."""
    out = frame.copy()
    if out.ndim == 2:
        out = cv2.cvtColor(out, cv2.COLOR_GRAY2BGR)

    if target_roi is not None:
        cv2.rectangle(
            out,
            (target_roi.x, target_roi.y),
            (target_roi.x + target_roi.width, target_roi.y + target_roi.height),
            (0, 255, 0),
            2,
        )
        cv2.putText(
            out,
            f"Target ({target_roi.width}x{target_roi.height})",
            (target_roi.x, max(18, target_roi.y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 255, 0),
            1,
            cv2.LINE_AA,
        )

    if anchor_roi is not None:
        cv2.rectangle(
            out,
            (anchor_roi.x, anchor_roi.y),
            (anchor_roi.x + anchor_roi.width, anchor_roi.y + anchor_roi.height),
            (0, 140, 255),
            2,
        )
        cv2.putText(
            out,
            f"Anchor ({anchor_roi.width}x{anchor_roi.height})",
            (anchor_roi.x, max(18, anchor_roi.y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 140, 255),
            1,
            cv2.LINE_AA,
        )

    return out
