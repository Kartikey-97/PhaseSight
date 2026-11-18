import numpy as np
import pytest

from phasesight.synthetic import (
    DEFAULT_ANCHOR_ROI,
    DEFAULT_TARGET_ROI,
    SyntheticConfig,
    make_scene,
)
from phasesight.tracker import PhaseCorrelationTracker, ROI


def test_subpixel_motion_and_camera_shake_are_recovered():
    config = SyntheticConfig(
        duration_s=4.0,
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.35,
        camera_amplitude_px=0.65,
        camera_y_amplitude_px=0.25,
        lighting_flicker_depth=0.08,
        noise_sigma=1.5,
        seed=23,
    )
    frames, truth = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    measured = np.asarray([
        tracker.process(frame, i / config.fps).relative_dx_px
        for i, frame in enumerate(frames[1:], start=1)
    ])
    error = measured - truth[1:]
    assert np.sqrt(np.mean(error**2)) < 0.20
    assert np.corrcoef(measured, truth[1:])[0, 1] > 0.85


def test_reference_is_not_destroyed_by_repeated_phase_correlation():
    config = SyntheticConfig(duration_s=2.0, noise_sigma=0.5, seed=2)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    target_before = tracker._target_ref.copy()
    anchor_before = tracker._anchor_ref.copy()
    for i, frame in enumerate(frames[1:20], start=1):
        tracker.process(frame, i / config.fps)
    assert np.array_equal(tracker._target_ref, target_before)
    assert np.array_equal(tracker._anchor_ref, anchor_before)


def test_overlapping_rois_are_rejected():
    config = SyntheticConfig(duration_s=1.0)
    frames, _ = make_scene(config)
    with pytest.raises(ValueError, match="should not overlap"):
        PhaseCorrelationTracker(frames[0], ROI(50, 50, 100, 100), ROI(100, 100, 100, 100))


def test_out_of_bounds_roi_is_rejected():
    config = SyntheticConfig(duration_s=1.0)
    frames, _ = make_scene(config)
    with pytest.raises(ValueError, match="outside"):
        PhaseCorrelationTracker(frames[0], ROI(600, 300, 100, 100), DEFAULT_ANCHOR_ROI)


def test_check_roi_texture_distinguishes_texture_and_flat():
    from phasesight.tracker import check_roi_texture

    config = SyntheticConfig(duration_s=1.0, seed=1)
    frames, _ = make_scene(config)
    frame = frames[0]
    has_tex, std_val = check_roi_texture(frame, DEFAULT_TARGET_ROI)
    assert has_tex is True
    assert std_val > 5.0

    # Flat patch with no texture
    flat_frame = np.ones((360, 640, 3), dtype=np.uint8) * 128
    has_tex_flat, std_flat = check_roi_texture(flat_frame, DEFAULT_TARGET_ROI)
    assert has_tex_flat is False
    assert std_flat < 0.1


def test_validate_rois_detects_bounds_size_overlap_and_texture():
    from phasesight.tracker import validate_rois

    config = SyntheticConfig(duration_s=1.0, seed=1)
    frames, _ = make_scene(config)
    frame = frames[0]

    # Valid ROIs return no errors
    errors = validate_rois(frame, DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    assert errors == []

    # Small size (<32x32)
    errors = validate_rois(frame, ROI(10, 10, 20, 40), DEFAULT_ANCHOR_ROI)
    assert any("at least 32x32" in e for e in errors)

    # Out of bounds
    errors = validate_rois(frame, ROI(600, 300, 100, 100), DEFAULT_ANCHOR_ROI)
    assert any("outside frame dimensions" in e for e in errors)

    # Overlapping
    errors = validate_rois(frame, ROI(50, 50, 100, 100), ROI(100, 100, 100, 100))
    assert any("must not overlap" in e for e in errors)

    # Flat untextured region
    flat_frame = np.ones((360, 640, 3), dtype=np.uint8) * 128
    errors = validate_rois(flat_frame, DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    assert any("lacks visible texture" in e for e in errors)


def test_draw_rois_on_frame_renders_boxes():
    from phasesight.tracker import draw_rois_on_frame

    frame = np.zeros((360, 640, 3), dtype=np.uint8)
    annotated = draw_rois_on_frame(frame, DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)
    assert annotated.shape == frame.shape
    # Check that colors have been written (not all zero)
    assert np.any(annotated > 0)
