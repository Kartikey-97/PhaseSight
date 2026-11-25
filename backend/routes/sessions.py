"""Continuous monitoring session endpoints."""

from __future__ import annotations

import asyncio
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import StreamingResponse

from backend.deps import get_manager, get_storage
from backend.manager import MonitoringManager
from backend.schemas import SessionStartRequest, SessionStopResponse, sanitize_json
from phasesight.storage import StorageManager

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.get("/active")
def get_active_session(
    manager: MonitoringManager = Depends(get_manager),
) -> dict[str, Any]:
    """Check currently active session status."""
    if manager.active_session is None:
        return {"active": False, "session_id": None}

    return {
        "active": True,
        "session_id": manager.active_session.config.session_id,
        "state": manager.active_session.state,
        "source_type": manager.active_session.config.source_type,
        "metadata": manager.active_metadata,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
def start_session(
    request: SessionStartRequest,
    storage: StorageManager = Depends(get_storage),
    manager: MonitoringManager = Depends(get_manager),
) -> dict[str, Any]:
    """Start a new continuous monitoring session."""
    session = manager.start_session(request, storage)
    return {
        "session_id": session.config.session_id,
        "state": session.state,
        "source_type": session.config.source_type,
    }


@router.get("/{session_id}")
def get_session_info(
    session_id: str, manager: MonitoringManager = Depends(get_manager)
) -> dict[str, Any]:
    """Fetch current session telemetry or cached completed report."""
    session = manager.get_session(session_id)
    if session:
        telem = session.get_rolling_telemetry(force=False)
        return sanitize_json(telem)

    for cached_id, report in manager.recent_reports:
        if cached_id == session_id:
            return sanitize_json(
                {
                    "session_id": session_id,
                    "state": "PERSISTED",
                    "report": report,
                }
            )

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Session '{session_id}' not found.",
    )


@router.post("/{session_id}/recalibrate")
def recalibrate_session(
    session_id: str, manager: MonitoringManager = Depends(get_manager)
) -> dict[str, Any]:
    """Request zero-offset recalibration on the next ingested frame."""
    manager.recalibrate_session(session_id)
    return {"status": "recalibration_requested", "session_id": session_id}


@router.post("/{session_id}/stop", response_model=SessionStopResponse)
def stop_session(
    session_id: str,
    storage: StorageManager = Depends(get_storage),
    manager: MonitoringManager = Depends(get_manager),
) -> SessionStopResponse:
    """Stop active session and persist inspection run to storage."""
    result = manager.stop_session(session_id, storage)
    return SessionStopResponse(
        session_id=result["session_id"],
        run_id=result["run_id"],
        state=result["state"],
        report=sanitize_json(result["report"]),
    )


@router.get("/{session_id}/frame.jpg")
def get_latest_frame(
    session_id: str, manager: MonitoringManager = Depends(get_manager)
) -> Response:
    """Fetch the latest frame from the video replay adapter as JPEG."""
    session = manager.get_session(session_id)
    if not session or not manager.active_adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active video replay stream for this session.",
        )

    jpeg_bytes = manager.active_adapter.get_latest_frame_jpeg()
    if not jpeg_bytes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Frame not available yet.",
        )

    return Response(
        content=jpeg_bytes,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{session_id}/mjpeg")
def stream_mjpeg(
    session_id: str, manager: MonitoringManager = Depends(get_manager)
) -> StreamingResponse:
    """Stream live multipart/x-mixed-replace JPEG video feed."""
    session = manager.get_session(session_id)
    if not session or not manager.active_adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No active video replay stream for this session.",
        )

    adapter = manager.active_adapter

    async def mjpeg_generator():
        try:
            while (
                manager.active_session_id == session_id
                and adapter.is_running
            ):
                jpeg = adapter.get_latest_frame_jpeg()
                if jpeg:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                    )
                await asyncio.sleep(0.05)  # ~20 FPS emission
        except (asyncio.CancelledError, GeneratorExit):
            pass

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store"},
    )
