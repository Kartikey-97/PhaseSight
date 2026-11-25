"""WebSocket endpoints for binary ROI ingestion and live telemetry streaming."""

from __future__ import annotations

import asyncio
import struct
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status

from backend.deps import get_manager
from backend.manager import MonitoringManager
from backend.schemas import sanitize_json

router = APIRouter(prefix="/ws/v1/sessions", tags=["websockets"])

HEADER_FORMAT = "<dIHHHHI"
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  # 24 bytes


@router.websocket("/{session_id}/ingest")
async def websocket_ingest(
    websocket: WebSocket,
    session_id: str,
    manager: MonitoringManager = Depends(get_manager),
) -> None:
    """Ingest raw binary grayscale ROI crops from browser webcam."""
    session = manager.get_session(session_id)
    if not session:
        await websocket.close(code=4404, reason=f"Session '{session_id}' not found.")
        return

    if session.config.source_type != "browser_webcam":
        await websocket.close(
            code=4400,
            reason=f"Session source_type is '{session.config.source_type}', expected 'browser_webcam'.",
        )
        return

    await websocket.accept()

    expected_t_w = session.config.target_roi.width
    expected_t_h = session.config.target_roi.height
    expected_a_w = session.config.anchor_roi.width
    expected_a_h = session.config.anchor_roi.height

    try:
        while True:
            data = await websocket.receive_bytes()
            if len(data) < HEADER_SIZE:
                await websocket.send_json(
                    {
                        "type": "ingest_error",
                        "detail": f"Packet too short ({len(data)} < {HEADER_SIZE} header bytes)",
                    }
                )
                continue

            (
                media_time_s,
                seq_num,
                target_w,
                target_h,
                anchor_w,
                anchor_h,
                flags,
            ) = struct.unpack(HEADER_FORMAT, data[:HEADER_SIZE])

            target_bytes_len = target_w * target_h
            anchor_bytes_len = anchor_w * anchor_h
            expected_total_len = HEADER_SIZE + target_bytes_len + anchor_bytes_len

            if len(data) != expected_total_len:
                await websocket.send_json(
                    {
                        "type": "ingest_error",
                        "detail": f"Buffer length mismatch: got {len(data)}, expected {expected_total_len}",
                    }
                )
                continue

            if (
                target_w != expected_t_w
                or target_h != expected_t_h
                or anchor_w != expected_a_w
                or anchor_h != expected_a_h
            ):
                await websocket.send_json(
                    {
                        "type": "ingest_error",
                        "detail": (
                            f"ROI dimension mismatch: packet ({target_w}x{target_h}, {anchor_w}x{anchor_h}) "
                            f"!= config ({expected_t_w}x{expected_t_h}, {expected_a_w}x{expected_a_h})"
                        ),
                    }
                )
                continue

            # Flag bit 0: recalibration request
            if flags & 1:
                session.request_recalibration()

            t_payload = data[HEADER_SIZE : HEADER_SIZE + target_bytes_len]
            a_payload = data[HEADER_SIZE + target_bytes_len :]

            target_patch = np.frombuffer(t_payload, dtype=np.uint8).reshape(
                (target_h, target_w)
            )
            anchor_patch = np.frombuffer(a_payload, dtype=np.uint8).reshape(
                (anchor_h, anchor_w)
            )

            try:
                session.ingest_patches(target_patch, anchor_patch, media_time_s)
            except ValueError as val_err:
                await websocket.send_json(
                    {
                        "type": "ingest_error",
                        "detail": str(val_err),
                        "seq_num": seq_num,
                    }
                )
            except Exception as exc:
                await websocket.send_json(
                    {
                        "type": "ingest_error",
                        "detail": f"Ingestion error: {exc}",
                        "seq_num": seq_num,
                    }
                )

    except WebSocketDisconnect:
        pass
    except Exception:
        pass


@router.websocket("/{session_id}/telemetry")
async def websocket_telemetry(
    websocket: WebSocket,
    session_id: str,
    manager: MonitoringManager = Depends(get_manager),
) -> None:
    """Stream live trace batches and periodic rolling spectral analysis updates."""
    session = manager.get_session(session_id)
    if not session:
        await websocket.close(code=4404, reason=f"Session '{session_id}' not found.")
        return

    await websocket.accept()

    try:
        # Initial snapshot
        initial_telem = session.get_rolling_telemetry(force=True)
        if initial_telem:
            await websocket.send_json(
                sanitize_json({"type": "snapshot", **initial_telem})
            )

        while True:
            # 1. Drain trace points
            batch = session.drain_trace_batch()
            if batch:
                await websocket.send_json(
                    sanitize_json(
                        {
                            "type": "trace_batch",
                            "session_id": session_id,
                            "state": session.state,
                            "samples": batch,
                        }
                    )
                )

            # 2. Rolling spectral analysis update
            telem = session.get_rolling_telemetry(force=False)
            if telem:
                await websocket.send_json(
                    sanitize_json({"type": "rolling_update", **telem})
                )

            # 3. Check termination
            if session.state in ("PERSISTED", "ERROR"):
                await websocket.send_json(
                    sanitize_json(
                        {
                            "type": "session_ended",
                            "session_id": session_id,
                            "state": session.state,
                            "error": session.error_message,
                        }
                    )
                )
                break

            await asyncio.sleep(0.10)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
