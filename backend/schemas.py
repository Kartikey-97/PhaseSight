"""Pydantic schemas and JSON sanitization utilities for PhaseSight backend."""

from __future__ import annotations

import math
from typing import Any, Sequence
import numpy as np
from pydantic import BaseModel, ConfigDict, Field, model_validator


def sanitize_json(obj: Any) -> Any:
    """Recursively converts non-finite floats and NumPy types to clean JSON-safe primitives."""
    if obj is None:
        return None
    if isinstance(obj, (bool, str)):
        return obj
    if isinstance(obj, (int, np.integer)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        val = float(obj)
        return val if math.isfinite(val) else None
    if isinstance(obj, np.ndarray):
        return [sanitize_json(x) for x in obj.tolist()]
    if isinstance(obj, dict):
        return {str(k): sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_json(x) for x in obj]
    if hasattr(obj, "to_dict") and callable(obj.to_dict):
        return sanitize_json(obj.to_dict())
    if hasattr(obj, "__dict__"):
        return sanitize_json(vars(obj))
    return str(obj)


class ROISchema(BaseModel):
    x: int
    y: int
    width: int
    height: int

    def to_xywh_dict(self) -> dict[str, int]:
        return {
            "x": int(self.x),
            "y": int(self.y),
            "width": int(self.width),
            "height": int(self.height),
        }


class HealthResponse(BaseModel):
    status: str = "ok"
    python_version: str
    versions: dict[str, str]
    active_session_id: str | None
    storage_ready: bool = True
    asset_count: int
    run_count: int


class AssetCreateRequest(BaseModel):
    name: str
    target_roi: ROISchema | None = None
    default_target_roi: ROISchema | None = None
    anchor_roi: ROISchema | None = None
    default_anchor_roi: ROISchema | None = None
    expected_fps: float = 60.0
    description: str = ""
    nominal_speed_rpm: float | None = None
    nominal_rpm: float | None = None
    scale_calibration: dict[str, Any] | None = None
    asset_id: str | None = None

    @model_validator(mode="after")
    def resolve_rois(self) -> "AssetCreateRequest":
        t = self.target_roi or self.default_target_roi or ROISchema(x=360, y=110, width=160, height=160)
        a = self.anchor_roi or self.default_anchor_roi or ROISchema(x=60, y=100, width=160, height=160)
        self.target_roi = t
        self.anchor_roi = a
        if self.nominal_speed_rpm is None and self.nominal_rpm is not None:
            self.nominal_speed_rpm = self.nominal_rpm
        return self


class AssetResponse(BaseModel):
    asset_id: str
    name: str
    description: str = ""
    nominal_speed_rpm: float | None = None
    nominal_rpm: float | None = None
    target_roi: dict[str, int]
    default_target_roi: dict[str, int] | None = None
    anchor_roi: dict[str, int]
    default_anchor_roi: dict[str, int] | None = None
    expected_fps: float = 60.0
    scale_calibration: dict[str, Any] | None = None
    created_at: str = ""
    updated_at: str = ""
    active_baseline: dict[str, Any] | None = None
    run_count: int = 0


class PresetResponse(BaseModel):
    preset_id: str
    label: str
    category: str  # "synthetic_validation" | "rotor_benchmark"
    rel_path: str
    exists: bool
    recommended_fps_override: float | None
    recommended_playback_rate: float
    default_target_roi: dict[str, int]
    default_anchor_roi: dict[str, int]
    description: str


class VideoPreviewResponse(BaseModel):
    upload_id: str | None = None
    preset_id: str | None = None
    width: int
    height: int
    container_fps: float
    frame_count: int
    duration_s: float
    preview_png_base64: str
    recommended_fps_override: float | None = None
    default_target_roi: dict[str, int] | None = None
    default_anchor_roi: dict[str, int] | None = None

    # Aliases for frontend compatibility
    frame_width: int | None = None
    frame_height: int | None = None
    fps: float | None = None
    total_frames: int | None = None
    preview_image_base64: str | None = None

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "frame_width" not in data and "width" in data:
                data["frame_width"] = data["width"]
            if "frame_height" not in data and "height" in data:
                data["frame_height"] = data["height"]
            if "fps" not in data and "container_fps" in data:
                data["fps"] = data["container_fps"]
            if "total_frames" not in data and "frame_count" in data:
                data["total_frames"] = data["frame_count"]
            if "preview_image_base64" not in data and "preview_png_base64" in data:
                data["preview_image_base64"] = data["preview_png_base64"]
            if "width" not in data and "frame_width" in data:
                data["width"] = data["frame_width"]
            if "height" not in data and "frame_height" in data:
                data["height"] = data["frame_height"]
            if "container_fps" not in data and "fps" in data:
                data["container_fps"] = data["fps"]
            if "frame_count" not in data and "total_frames" in data:
                data["frame_count"] = data["total_frames"]
            if "preview_png_base64" not in data and "preview_image_base64" in data:
                data["preview_png_base64"] = data["preview_image_base64"]
        return data


class CheckROIsRequest(BaseModel):
    preset_id: str | None = None
    upload_id: str | None = None
    target_roi: ROISchema
    anchor_roi: ROISchema


class CheckROIsResponse(BaseModel):
    valid: bool
    target_texture_std: float
    anchor_texture_std: float
    target_std: float | None = None
    anchor_std: float | None = None
    errors: list[str]

    @model_validator(mode="before")
    @classmethod
    def populate_aliases(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "target_std" not in data and "target_texture_std" in data:
                data["target_std"] = data["target_texture_std"]
            if "anchor_std" not in data and "anchor_texture_std" in data:
                data["anchor_std"] = data["anchor_texture_std"]
        return data


class RunAnalyzeResponse(BaseModel):
    run_id: str
    asset_id: str
    summary: dict[str, Any]
    baseline_assessment: dict[str, Any] | None
    arrays: dict[str, Any]


class BaselineBuildRequest(BaseModel):
    asset_id: str
    run_ids: list[str]
    require_valid_axes: list[str] | None = ["x", "y"]
    notes: str = ""


class SessionStartRequest(BaseModel):
    session_id: str | None = None
    source_type: str = "video_replay"  # "video_replay" | "browser_webcam"
    preset_id: str | None = None
    upload_id: str | None = None
    target_roi: ROISchema
    anchor_roi: ROISchema
    expected_fps: float = 30.0
    fps_override: float | None = None
    playback_rate: float = 1.0
    loop: bool = True
    buffer_capacity: int = 512
    nperseg_override: int | None = None
    asset_id: str | None = None
    min_texture_std: float = Field(default=2.0, ge=2.0)


class SessionStopResponse(BaseModel):
    session_id: str
    run_id: str | None
    state: str
    report: dict[str, Any]
