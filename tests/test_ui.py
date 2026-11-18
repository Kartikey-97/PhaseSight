from pathlib import Path

import numpy as np
import pytest
from streamlit.testing.v1 import AppTest

from phasesight.ui_helpers import get_video_metadata, read_first_frame


APP_PATH = Path(__file__).parent.parent / "phasesight" / "app.py"


def test_ui_helpers_get_metadata_and_frame():
    baseline_path = Path("data/portable/baseline.mp4")
    meta = get_video_metadata(baseline_path)
    assert meta["width"] == 640
    assert meta["height"] == 360
    assert meta["fps"] == pytest.approx(60.0, rel=1e-2)
    assert meta["frame_count"] == 600

    frame = read_first_frame(baseline_path)
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (360, 640, 3)


def test_ui_helpers_reject_invalid_video(tmp_path):
    invalid_path = tmp_path / "nonexistent.mp4"
    with pytest.raises(RuntimeError, match="Could not open video"):
        get_video_metadata(invalid_path)

    with pytest.raises(RuntimeError, match="Could not open video"):
        read_first_frame(invalid_path)


def test_streamlit_app_loads_and_renders_cleanly():
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception
    # Check that tabs rendered
    assert len(at.tabs) == 3


def test_streamlit_app_sample_clip_inspection():
    at = AppTest.from_file(str(APP_PATH), default_timeout=30)
    at.run()
    assert not at.exception
    # Should have radio button for input source
    assert len(at.radio) >= 1
    # Check that the default sample clip loads metadata and images
    assert len(at.image) >= 1
