"""Single-session lifecycle manager for continuous monitoring."""

from __future__ import annotations

import collections
import dataclasses
import datetime
from pathlib import Path
import threading
from typing import Any
import uuid

from fastapi import HTTPException, status

from backend.presets import resolve_video_path
from backend.schemas import SessionStartRequest
from phasesight.baseline import BaselineRecord
from phasesight.monitoring.replay_adapter import PacedVideoReplayAdapter
from phasesight.monitoring.session import MonitoringConfig, MonitoringSession
from phasesight.storage import StorageManager
from phasesight.tracker import ROI


class MonitoringManager:
    """Thread-safe lifecycle manager enforcing a single active session."""

    def __init__(self, uploads_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self.active_session: MonitoringSession | None = None
        self.active_adapter: PacedVideoReplayAdapter | None = None
        self.active_metadata: dict[str, Any] = {}
        self.recent_reports: collections.deque[tuple[str, dict[str, Any]]] = (
            collections.deque(maxlen=20)
        )
        self.uploads_dir = (
            uploads_dir.resolve() if uploads_dir else Path("data/storage/uploads").resolve()
        )
        self.uploads_dir.mkdir(parents=True, exist_ok=True)

    @property
    def active_session_id(self) -> str | None:
        with self._lock:
            return self.active_session.config.session_id if self.active_session else None

    def get_session(self, session_id: str) -> MonitoringSession | None:
        with self._lock:
            if self.active_session and self.active_session.config.session_id == session_id:
                return self.active_session
            return None

    def start_session(
        self,
        request: SessionStartRequest,
        storage: StorageManager,
        base_dir: Path | None = None,
    ) -> MonitoringSession:
        """Initialize and start a monitoring session."""
        with self._lock:
            if self.active_session is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"A session is already active (id='{self.active_session.config.session_id}'). Stop it before starting a new one.",
                )

            session_id = request.session_id or f"sess_{uuid.uuid4().hex[:10]}"
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

            # Check for active baseline if asset_id is provided
            baseline_rec: BaselineRecord | None = None
            active_baseline_id: str | None = None
            if request.asset_id:
                stored_b = storage.get_latest_baseline_for_asset(request.asset_id)
                if stored_b:
                    baseline_rec = stored_b.baseline_record
                    active_baseline_id = stored_b.baseline_id

            video_file_path: Path | None = None
            if request.source_type == "video_replay":
                try:
                    video_file_path = resolve_video_path(
                        request.preset_id,
                        request.upload_id,
                        self.uploads_dir,
                        base_dir=base_dir,
                    )
                except Exception as exc:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to resolve replay video: {exc}",
                    )

            effective_fps_override = (
                None if request.source_type == "browser_webcam" else request.fps_override
            )
            timebase_source = (
                "browser_media_time"
                if request.source_type == "browser_webcam"
                else ("explicit_fps_override" if effective_fps_override is not None else "measured")
            )
            config = MonitoringConfig(
                session_id=session_id,
                source_type=request.source_type,
                target_roi=target_roi,
                anchor_roi=anchor_roi,
                expected_fps=effective_fps_override or request.expected_fps,
                timebase_source=timebase_source,
                buffer_capacity=request.buffer_capacity,
                nperseg_override=request.nperseg_override,
                asset_id=request.asset_id,
                video_path=str(video_file_path) if video_file_path else None,
                baseline=baseline_rec,
                baseline_id=active_baseline_id,
                min_texture_std=request.min_texture_std,
            )

            session = MonitoringSession(config)

            adapter = None
            if request.source_type == "video_replay" and video_file_path:
                adapter = PacedVideoReplayAdapter(
                    video_path=video_file_path,
                    session=session,
                    fps_override=request.fps_override,
                    playback_rate=request.playback_rate,
                    loop=request.loop,
                )
                adapter.start()

            self.active_session = session
            self.active_adapter = adapter
            self.active_metadata = {
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "preset_id": request.preset_id,
                "upload_id": request.upload_id,
                "loop": request.loop,
                "playback_rate": request.playback_rate,
            }
            return session

    def recalibrate_session(self, session_id: str) -> None:
        """Trigger recalibration on the next frame."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Active session '{session_id}' not found.",
                )
            session.request_recalibration()

    def stop_session(
        self, session_id: str, storage: StorageManager
    ) -> dict[str, Any]:
        """Stop active session, stop adapter, persist run, and clear active slot."""
        with self._lock:
            session = self.get_session(session_id)
            if not session:
                # Check recent reports cache
                for cached_id, rep in self.recent_reports:
                    if cached_id == session_id:
                        return {
                            "session_id": session_id,
                            "run_id": rep.get("run_id"),
                            "state": "PERSISTED",
                            "report": rep,
                        }
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Active session '{session_id}' not found.",
                )

            # Stop replay adapter if running
            if self.active_adapter is not None:
                self.active_adapter.stop()
                self.active_adapter = None

            # Ensure asset exists in storage for foreign key integrity
            if not session.config.asset_id or not storage.get_asset(session.config.asset_id):
                fallback_id = session.config.asset_id or "quick_bench"
                if not storage.get_asset(fallback_id):
                    storage.create_asset(
                        name="Quick Bench Asset"
                        if fallback_id == "quick_bench"
                        else fallback_id,
                        target_roi=session.config.target_roi,
                        anchor_roi=session.config.anchor_roi,
                        expected_fps=session.config.expected_fps,
                        description="Auto-generated default asset for ad-hoc inspection sessions.",
                        asset_id=fallback_id,
                    )
                session.config = dataclasses.replace(
                    session.config, asset_id=fallback_id
                )

            report = session.stop_and_persist(storage)
            if not report.get("measured_fps") or report.get("measured_fps") <= 0:
                report["measured_fps"] = report.get("fps_used") or (
                    session.config.expected_fps if session.config.expected_fps else 30.0
                )
            report["fps_used"] = report["measured_fps"]
            if not report.get("timebase_source"):
                report["timebase_source"] = session.config.timebase_source
            if not report.get("timestamp_source"):
                report["timestamp_source"] = session.config.timebase_source
            run_id = report.get("run_id")

            self.recent_reports.append((session_id, report))
            self.active_session = None
            self.active_metadata = {}

            return {
                "session_id": session_id,
                "run_id": run_id,
                "state": "PERSISTED",
                "report": report,
            }

    def shutdown(self) -> None:
        """Clean shutdown invoked during application lifespan termination."""
        with self._lock:
            if self.active_adapter is not None:
                self.active_adapter.stop()
                self.active_adapter = None
            self.active_session = None
