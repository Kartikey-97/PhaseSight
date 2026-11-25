"""Video inspection, preview, and ROI validation endpoints."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any
import uuid

import cv2
from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status

from backend.deps import get_manager
from backend.manager import MonitoringManager
from backend.presets import get_preset, list_presets, resolve_video_path
from backend.schemas import (
    CheckROIsRequest,
    CheckROIsResponse,
    PresetResponse,
    VideoPreviewResponse,
)
from phasesight.tracker import ROI, check_roi_texture, validate_rois

router = APIRouter(prefix="/videos", tags=["videos"])


def _extract_video_preview(video_path: Path) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    try:
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = float(count / fps) if fps > 0 and count > 0 else 0.0

        ret, frame = cap.read()
        if not ret or frame is None:
            raise ValueError("Could not read first frame from video")

        ret_png, buf = cv2.imencode(".png", frame)
        if not ret_png:
            raise ValueError("Could not encode frame to PNG")
        b64_png = base64.b64encode(buf.tobytes()).decode("ascii")

        return {
            "width": width,
            "height": height,
            "container_fps": fps,
            "frame_count": count,
            "duration_s": duration,
            "preview_png_base64": b64_png,
        }
    finally:
        cap.release()


def _check_rois_on_video(
    video_path: Path, target_roi: ROI, anchor_roi: ROI
) -> dict[str, Any]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {video_path}")
    try:
        ret, frame = cap.read()
        if not ret or frame is None:
            raise ValueError("Could not read first frame from video")

        errors = validate_rois(frame, target_roi, anchor_roi)
        has_t, t_std = check_roi_texture(frame, target_roi)
        has_a, a_std = check_roi_texture(frame, anchor_roi)

        return {
            "valid": len(errors) == 0,
            "target_texture_std": float(t_std),
            "anchor_texture_std": float(a_std),
            "errors": errors,
        }
    finally:
        cap.release()


@router.get("/presets", response_model=list[PresetResponse])
def get_presets() -> list[PresetResponse]:
    """List allowlisted video presets with availability status."""
    return list_presets()


@router.post("/preview", response_model=VideoPreviewResponse)
async def preview_video(
    request: Request,
    manager: MonitoringManager = Depends(get_manager),
) -> VideoPreviewResponse:
    """Generate preview metadata and base64 PNG of frame 0."""
    content_type = request.headers.get("content-type", "")
    preset_id: str | None = None
    upload_id: str | None = None
    file: UploadFile | None = None

    if "application/json" in content_type:
        try:
            body = await request.json()
            preset_id = body.get("preset_id")
            upload_id = body.get("upload_id")
        except Exception:
            pass
    else:
        try:
            form = await request.form()
            preset_id = form.get("preset_id")
            upload_id = form.get("upload_id")
            raw_file = form.get("file")
            if raw_file is not None and hasattr(raw_file, "filename") and hasattr(raw_file, "read"):
                file = raw_file
        except Exception:
            pass

    saved_upload_id = upload_id
    if file is not None and file.filename:
        saved_upload_id = f"upl_{uuid.uuid4().hex[:10]}"
        ext = Path(file.filename).suffix or ".mp4"
        dest_path = manager.uploads_dir / f"{saved_upload_id}{ext}"
        content = await file.read()
        dest_path.write_bytes(content)
        resolved_path = dest_path
        preset_id = None
    else:
        try:
            resolved_path = resolve_video_path(
                preset_id, upload_id, manager.uploads_dir
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )

    try:
        meta = await asyncio.to_thread(_extract_video_preview, resolved_path)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to decode video preview: {exc}",
        )

    preset_info = get_preset(preset_id) if preset_id else None
    rec_fps = preset_info.get("recommended_fps_override") if preset_info else None
    def_target = preset_info.get("default_target_roi") if preset_info else None
    def_anchor = preset_info.get("default_anchor_roi") if preset_info else None

    return VideoPreviewResponse(
        upload_id=saved_upload_id,
        preset_id=preset_id,
        width=meta["width"],
        height=meta["height"],
        container_fps=meta["container_fps"],
        frame_count=meta["frame_count"],
        duration_s=meta["duration_s"],
        preview_png_base64=meta["preview_png_base64"],
        recommended_fps_override=rec_fps,
        default_target_roi=def_target,
        default_anchor_roi=def_anchor,
        frame_width=meta["width"],
        frame_height=meta["height"],
        fps=meta["container_fps"],
        total_frames=meta["frame_count"],
        preview_image_base64=meta["preview_png_base64"],
    )


@router.post("/check-rois", response_model=CheckROIsResponse)
async def check_rois(
    request: CheckROIsRequest, manager: MonitoringManager = Depends(get_manager)
) -> CheckROIsResponse:
    """Validate ROI geometry and visible surface texture on frame 0."""
    try:
        resolved_path = resolve_video_path(
            request.preset_id, request.upload_id, manager.uploads_dir
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    target_roi = ROI(
        x=request.target_roi.x,
        y=request.target_roi.y,
        width=request.target_roi.width,
        height=request.target_roi.height,
    )
    anchor_roi = ROI(
        x=request.anchor_roi.x,
        y=request.anchor_roi.y,
        width=request.anchor_roi.width,
        height=request.anchor_roi.height,
    )

    try:
        result = await asyncio.to_thread(
            _check_rois_on_video, resolved_path, target_roi, anchor_roi
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    return CheckROIsResponse(
        valid=result["valid"],
        target_texture_std=result["target_texture_std"],
        anchor_texture_std=result["anchor_texture_std"],
        errors=result["errors"],
    )
