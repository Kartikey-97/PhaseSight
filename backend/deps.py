"""FastAPI dependency injection providers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from backend.manager import MonitoringManager
from phasesight.storage import StorageManager

_GLOBAL_STORAGE: StorageManager | None = None
_GLOBAL_MANAGER: MonitoringManager | None = None


def get_storage() -> StorageManager:
    """Provide singleton StorageManager instance, overridable in tests."""
    global _GLOBAL_STORAGE
    if _GLOBAL_STORAGE is None:
        root = os.environ.get("PHASESIGHT_STORAGE_ROOT", "data/storage")
        _GLOBAL_STORAGE = StorageManager(storage_root=root)
    return _GLOBAL_STORAGE


def get_manager() -> MonitoringManager:
    """Provide singleton MonitoringManager instance, overridable in tests."""
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        storage = get_storage()
        uploads = storage.storage_root / "uploads"
        _GLOBAL_MANAGER = MonitoringManager(uploads_dir=uploads)
    return _GLOBAL_MANAGER


def reset_dependencies() -> None:
    """Reset singletons (used primarily during test teardowns)."""
    global _GLOBAL_STORAGE, _GLOBAL_MANAGER
    if _GLOBAL_MANAGER:
        _GLOBAL_MANAGER.shutdown()
        _GLOBAL_MANAGER = None
    if _GLOBAL_STORAGE:
        _GLOBAL_STORAGE.close()
        _GLOBAL_STORAGE = None
