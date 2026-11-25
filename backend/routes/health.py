"""Health check endpoint."""

from __future__ import annotations

import sys
import cv2
import fastapi
import numpy as np
import scipy
from fastapi import APIRouter, Depends

from backend.deps import get_manager, get_storage
from backend.manager import MonitoringManager
from backend.schemas import HealthResponse
from phasesight.storage import StorageManager

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
def get_health(
    storage: StorageManager = Depends(get_storage),
    manager: MonitoringManager = Depends(get_manager),
) -> HealthResponse:
    """Return system readiness, component versions, and active session status."""
    info = storage.get_db_info()
    return HealthResponse(
        status="ok",
        python_version=sys.version.split()[0],
        versions={
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "cv2": cv2.__version__,
            "fastapi": fastapi.__version__,
        },
        active_session_id=manager.active_session_id,
        storage_ready=True,
        asset_count=info.get("asset_count", 0),
        run_count=info.get("run_count", 0),
    )
