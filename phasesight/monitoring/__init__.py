"""PhaseSight Continuous Vibration Monitoring Engine.

Provides O(1) circular motion buffering, online rolling Welch PSD analysis,
thread-safe live session lifecycle orchestration, and paced video stream adapters.
Zero-coupling with Streamlit, FastAPI, or Matplotlib.
"""

from __future__ import annotations

from phasesight.monitoring.replay_adapter import PacedVideoReplayAdapter
from phasesight.monitoring.ring_buffer import BufferSnapshot, RollingMotionBuffer
from phasesight.monitoring.rolling_analysis import (
    RollingAnalysisResult,
    RollingAxisMetrics,
    analyze_rolling_window,
    select_adaptive_nperseg,
)
from phasesight.monitoring.session import MonitoringConfig, MonitoringSession

__all__ = [
    "BufferSnapshot",
    "RollingMotionBuffer",
    "RollingAxisMetrics",
    "RollingAnalysisResult",
    "select_adaptive_nperseg",
    "analyze_rolling_window",
    "MonitoringConfig",
    "MonitoringSession",
    "PacedVideoReplayAdapter",
]
