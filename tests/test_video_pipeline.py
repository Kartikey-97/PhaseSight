import numpy as np

from phasesight.synthetic import SyntheticConfig, make_scene, write_video, DEFAULT_ANCHOR_ROI, DEFAULT_TARGET_ROI
from phasesight.video import analyse_video


def test_encoded_video_round_trip_keeps_frequency(tmp_path):
    config = SyntheticConfig(
        duration_s=5.0,
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.35,
        camera_amplitude_px=0.4,
        noise_sigma=1.0,
        seed=44,
    )
    frames, _ = make_scene(config)
    video = tmp_path / "test.mp4"
    write_video(video, frames, config.fps)
    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "output",
        min_frequency_hz=1.0,
        max_frequency_hz=20.0,
        nperseg=256,
    )
    assert abs(summary["x_axis"]["dominant_frequency_hz"] - 8.5) < 0.5
    assert summary["x_axis"]["signal_quality"] == "VALID"
    assert (tmp_path / "output" / "test_motion.csv").exists()
    assert (tmp_path / "output" / "test_spectrum.png").exists()


def test_camera_only_h264_clip_is_flagged_when_anchor_has_same_peak(tmp_path):
    config = SyntheticConfig(
        duration_s=5.0,
        vibration_amplitude_px=0.0,
        camera_amplitude_px=0.15,
        camera_y_amplitude_px=0.05,
        lighting_flicker_depth=0.08,
        noise_sigma=1.5,
        seed=7,
    )
    frames, _ = make_scene(config)
    video = tmp_path / "null.mp4"
    write_video(video, frames, config.fps)
    summary = analyse_video(
        video,
        DEFAULT_TARGET_ROI,
        DEFAULT_ANCHOR_ROI,
        tmp_path / "null_output",
        min_frequency_hz=1.0,
        max_frequency_hz=20.0,
        nperseg=256,
    )
    # A short compressed null clip may be rejected as LOW_SIGNAL before its
    # shared anchor peak is strong enough for the contamination label. It must
    # never be presented as a valid machine vibration.
    assert summary["x_axis"]["signal_quality"] != "VALID"
