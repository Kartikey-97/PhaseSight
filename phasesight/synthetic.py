from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .tracker import ROI


@dataclass(frozen=True)
class SyntheticConfig:
    fps: int = 60
    duration_s: float = 10.0
    vibration_frequency_hz: float = 8.5
    vibration_amplitude_px: float = 0.35
    second_harmonic_amplitude_px: float = 0.0
    camera_frequency_hz: float = 0.7
    camera_amplitude_px: float = 0.65
    camera_y_amplitude_px: float = 0.25
    lighting_flicker_hz: float = 100.0
    lighting_flicker_depth: float = 0.08
    noise_sigma: float = 1.5
    seed: int = 7
    width: int = 640
    height: int = 360


DEFAULT_TARGET_ROI = ROI(360, 110, 160, 160)
DEFAULT_ANCHOR_ROI = ROI(60, 100, 160, 160)


def make_scene(config: SyntheticConfig) -> tuple[np.ndarray, np.ndarray]:
    """Generate frames and ground-truth relative target displacement in px."""
    rng = np.random.default_rng(config.seed)
    base = rng.normal(127.0, 35.0, (config.height, config.width)).astype(np.float32)
    base = cv2.GaussianBlur(base, (0, 0), 1.0)
    base = np.clip(base, 0, 255).astype(np.uint8)

    target = DEFAULT_TARGET_ROI
    anchor = DEFAULT_ANCHOR_ROI
    target.validate(base.shape, name="target ROI")
    anchor.validate(base.shape, name="anchor ROI")

    base_target = target.crop(base).copy()
    frames: list[np.ndarray] = []
    truth: list[float] = []
    count = int(round(config.fps * config.duration_s))

    for index in range(count):
        t = index / config.fps
        target_dx = config.vibration_amplitude_px * np.sin(
            2.0 * np.pi * config.vibration_frequency_hz * t
        )
        if config.second_harmonic_amplitude_px:
            target_dx += config.second_harmonic_amplitude_px * np.sin(
                2.0 * np.pi * 2.0 * config.vibration_frequency_hz * t + 0.25
            )
        camera_dx = config.camera_amplitude_px * np.sin(
            2.0 * np.pi * config.camera_frequency_hz * t
        )
        camera_dy = config.camera_y_amplitude_px * np.sin(
            2.0 * np.pi * 0.43 * t + 0.3
        )

        target_patch = cv2.warpAffine(
            base_target,
            np.float32([[1.0, 0.0, target_dx], [0.0, 1.0, 0.0]]),
            (target.width, target.height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REFLECT,
        )
        scene = base.copy()
        scene[target.y : target.y + target.height, target.x : target.x + target.width] = target_patch
        frame = cv2.warpAffine(
            scene,
            np.float32([[1.0, 0.0, camera_dx], [0.0, 1.0, camera_dy]]),
            (config.width, config.height),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REFLECT,
        )

        # Global gain modulation models illumination flicker. A camera-only
        # case sets target vibration amplitude to zero but keeps all nuisances.
        gain = 1.0 + config.lighting_flicker_depth * np.sin(
            2.0 * np.pi * config.lighting_flicker_hz * t
        )
        frame = frame.astype(np.float32) * gain + rng.normal(
            0.0, config.noise_sigma, frame.shape
        )
        frame = np.clip(frame, 0, 255).astype(np.uint8)
        frames.append(cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR))
        truth.append(float(target_dx))

    return np.stack(frames), np.asarray(truth, dtype=np.float64)


def write_video(path: str | Path, frames: np.ndarray, fps: int) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    if frames.ndim != 4 or frames.shape[-1] != 3:
        raise ValueError("frames must have shape (N, H, W, 3)")
    height, width = frames.shape[1:3]
    writer = cv2.VideoWriter(
        str(output), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (width, height)
    )
    if not writer.isOpened():
        raise RuntimeError("Could not create MP4 video; check OpenCV video codec support")
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()
