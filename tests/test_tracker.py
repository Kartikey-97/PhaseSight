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


# ==============================================================================
# Task 1: Dynamic ROI Quality Validation Regression Tests (Scenarios 1-8)
# ==============================================================================

def test_dynamic_roi_regression_1_normal_moving_textured():
    """Scenario 1: Normal moving textured ROI maintains valid samples and high response."""
    config = SyntheticConfig(
        duration_s=1.0,
        vibration_frequency_hz=8.5,
        vibration_amplitude_px=0.5,
        camera_amplitude_px=0.2,
        seed=10,
    )
    frames, truth = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    samples = [tracker.process(frame, i / config.fps) for i, frame in enumerate(frames[1:], start=1)]
    assert len(samples) > 0
    for s in samples:
        assert s.valid is True
        assert s.rejection_reason is None
        assert np.isfinite(s.relative_dx_px)
        assert np.isfinite(s.target_dx_px)
        assert np.isfinite(s.anchor_dx_px)
        assert s.target_response >= tracker.min_response
        assert s.anchor_response >= tracker.min_response


def test_dynamic_roi_regression_2_black_halfway():
    """Scenario 2: ROI becomes completely black halfway through recording."""
    config = SyntheticConfig(duration_s=1.0, seed=11)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    halfway = len(frames) // 2
    for i, frame in enumerate(frames[1:], start=1):
        test_frame = frame.copy()
        if i >= halfway:
            # Black out target ROI
            test_frame[
                DEFAULT_TARGET_ROI.y : DEFAULT_TARGET_ROI.y + DEFAULT_TARGET_ROI.height,
                DEFAULT_TARGET_ROI.x : DEFAULT_TARGET_ROI.x + DEFAULT_TARGET_ROI.width,
            ] = 0

        sample = tracker.process(test_frame, i / config.fps)
        if i < halfway:
            assert sample.valid is True
            assert sample.rejection_reason is None
            assert np.isfinite(sample.relative_dx_px)
        else:
            assert sample.valid is False
            assert "target_low_texture" in sample.rejection_reason
            assert np.isnan(sample.relative_dx_px)
            assert np.isnan(sample.target_dx_px)
            assert sample.target_response == 0.0
            # CRITICAL: Verify no artificial half-width displacement jumps (160/2 = 80 px)
            assert sample.target_dx_px != DEFAULT_TARGET_ROI.width / 2.0
            assert sample.relative_dx_px != DEFAULT_TARGET_ROI.width / 2.0


def test_dynamic_roi_regression_3_uniformly_white():
    """Scenario 3: ROI becomes uniformly white."""
    config = SyntheticConfig(duration_s=0.5, seed=12)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    white_frame = frames[1].copy()
    white_frame[
        DEFAULT_TARGET_ROI.y : DEFAULT_TARGET_ROI.y + DEFAULT_TARGET_ROI.height,
        DEFAULT_TARGET_ROI.x : DEFAULT_TARGET_ROI.x + DEFAULT_TARGET_ROI.width,
    ] = 255

    sample = tracker.process(white_frame, 1 / config.fps)
    assert sample.valid is False
    assert "target_low_texture" in sample.rejection_reason
    assert np.isnan(sample.relative_dx_px)
    assert np.isnan(sample.target_dx_px)
    assert sample.target_response == 0.0
    assert sample.target_dx_px != DEFAULT_TARGET_ROI.width / 2.0


def test_dynamic_roi_regression_4_gradual_contrast_loss():
    """Scenario 4: ROI becomes low contrast gradually and is rejected when std drops."""
    config = SyntheticConfig(duration_s=1.0, seed=13)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI, min_texture_std=2.0)

    # Frame with original contrast: valid
    s_full = tracker.process(frames[1], 1 / config.fps)
    assert s_full.valid is True

    # Gradually fade contrast towards uniform gray (std drops)
    faded_frame = frames[1].copy().astype(np.float32)
    t_crop = faded_frame[
        DEFAULT_TARGET_ROI.y : DEFAULT_TARGET_ROI.y + DEFAULT_TARGET_ROI.height,
        DEFAULT_TARGET_ROI.x : DEFAULT_TARGET_ROI.x + DEFAULT_TARGET_ROI.width,
    ]
    mean_val = np.mean(t_crop)
    # Scale patch contrast to standard deviation of 1.0 (< min_texture_std 2.0)
    current_std = np.std(t_crop)
    faded_crop = mean_val + (t_crop - mean_val) * (1.0 / current_std)
    faded_frame[
        DEFAULT_TARGET_ROI.y : DEFAULT_TARGET_ROI.y + DEFAULT_TARGET_ROI.height,
        DEFAULT_TARGET_ROI.x : DEFAULT_TARGET_ROI.x + DEFAULT_TARGET_ROI.width,
    ] = np.clip(faded_crop, 0, 255)

    s_faded = tracker.process(faded_frame.astype(np.uint8), 2 / config.fps)
    assert s_faded.valid is False
    assert "target_low_texture" in s_faded.rejection_reason
    assert np.isnan(s_faded.relative_dx_px)


def test_dynamic_roi_regression_5_temporary_texture_loss_and_recovery():
    """Scenario 5: ROI temporarily loses texture and later recovers cleanly."""
    config = SyntheticConfig(duration_s=1.0, seed=14)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    # Sequence: 5 normal frames -> 5 blank frames -> 5 normal frames
    results = []
    for i, frame in enumerate(frames[1:16], start=1):
        f = frame.copy()
        if 5 <= i <= 10:
            f[
                DEFAULT_TARGET_ROI.y : DEFAULT_TARGET_ROI.y + DEFAULT_TARGET_ROI.height,
                DEFAULT_TARGET_ROI.x : DEFAULT_TARGET_ROI.x + DEFAULT_TARGET_ROI.width,
            ] = 128
        results.append(tracker.process(f, i / config.fps))

    # Before drop
    for s in results[0:4]:
        assert s.valid is True
        assert np.isfinite(s.relative_dx_px)

    # During drop
    for s in results[4:10]:
        assert s.valid is False
        assert "target_low_texture" in s.rejection_reason
        assert np.isnan(s.relative_dx_px)

    # After recovery
    for s in results[10:]:
        assert s.valid is True
        assert s.rejection_reason is None
        assert np.isfinite(s.relative_dx_px)
        assert s.target_response >= tracker.min_response


def test_dynamic_roi_regression_6_target_loses_texture_anchor_valid():
    """Scenario 6: Target loses texture while anchor remains valid."""
    config = SyntheticConfig(duration_s=0.5, seed=15)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    test_frame = frames[1].copy()
    test_frame[
        DEFAULT_TARGET_ROI.y : DEFAULT_TARGET_ROI.y + DEFAULT_TARGET_ROI.height,
        DEFAULT_TARGET_ROI.x : DEFAULT_TARGET_ROI.x + DEFAULT_TARGET_ROI.width,
    ] = 50

    sample = tracker.process(test_frame, 1 / config.fps)
    assert sample.valid is False
    assert "target_low_texture" in sample.rejection_reason
    assert "anchor_low_texture" not in sample.rejection_reason
    assert np.isnan(sample.relative_dx_px)


def test_dynamic_roi_regression_7_anchor_loses_texture_target_valid():
    """Scenario 7: Anchor loses texture while target remains valid."""
    config = SyntheticConfig(duration_s=0.5, seed=16)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    test_frame = frames[1].copy()
    test_frame[
        DEFAULT_ANCHOR_ROI.y : DEFAULT_ANCHOR_ROI.y + DEFAULT_ANCHOR_ROI.height,
        DEFAULT_ANCHOR_ROI.x : DEFAULT_ANCHOR_ROI.x + DEFAULT_ANCHOR_ROI.width,
    ] = 50

    sample = tracker.process(test_frame, 1 / config.fps)
    assert sample.valid is False
    assert "anchor_low_texture" in sample.rejection_reason
    assert "target_low_texture" not in sample.rejection_reason
    assert np.isnan(sample.relative_dx_px)


def test_dynamic_roi_regression_8_both_rois_invalid():
    """Scenario 8: Both ROIs become invalid simultaneously."""
    config = SyntheticConfig(duration_s=0.5, seed=17)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    test_frame = np.zeros_like(frames[1])

    sample = tracker.process(test_frame, 1 / config.fps)
    assert sample.valid is False
    assert "target_low_texture" in sample.rejection_reason
    assert "anchor_low_texture" in sample.rejection_reason
    assert np.isnan(sample.relative_dx_px)


def test_dynamic_roi_non_finite_rejection():
    """Verify non-finite pixel values (NaN/inf) are explicitly caught and rejected."""
    config = SyntheticConfig(duration_s=0.5, seed=18)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    test_frame = frames[1].copy().astype(np.float32)
    # Inject NaN into target ROI
    test_frame[DEFAULT_TARGET_ROI.y + 10, DEFAULT_TARGET_ROI.x + 10] = np.nan

    sample = tracker.process(test_frame, 1 / config.fps)
    assert sample.valid is False
    assert "target_non_finite" in sample.rejection_reason
    assert np.isnan(sample.relative_dx_px)


def test_from_patches_and_process_patches_match_standard_tracker():
    config = SyntheticConfig(duration_s=1.0, seed=42)
    frames, _ = make_scene(config)
    frame0 = frames[0]

    # Standard tracker initialized from full frame
    tracker_standard = PhaseCorrelationTracker(frame0, DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    # Patch-direct tracker initialized from crops
    t_crop = DEFAULT_TARGET_ROI.crop(frame0)
    a_crop = DEFAULT_ANCHOR_ROI.crop(frame0)
    tracker_patches = PhaseCorrelationTracker.from_patches(
        t_crop, a_crop, DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI, frame_shape=frame0.shape[:2]
    )

    for i, frame in enumerate(frames[1:10], start=1):
        ts = i / config.fps
        sample_std = tracker_standard.process(frame, ts)
        sample_pat = tracker_patches.process_patches(
            DEFAULT_TARGET_ROI.crop(frame), DEFAULT_ANCHOR_ROI.crop(frame), ts
        )

        assert sample_std.valid == sample_pat.valid
        if sample_std.valid:
            assert np.isclose(sample_std.target_dx_px, sample_pat.target_dx_px, atol=1e-5)
            assert np.isclose(sample_std.target_dy_px, sample_pat.target_dy_px, atol=1e-5)
            assert np.isclose(sample_std.anchor_dx_px, sample_pat.anchor_dx_px, atol=1e-5)
            assert np.isclose(sample_std.anchor_dy_px, sample_pat.anchor_dy_px, atol=1e-5)
            assert np.isclose(sample_std.relative_dx_px, sample_pat.relative_dx_px, atol=1e-5)
            assert np.isclose(sample_std.relative_dy_px, sample_pat.relative_dy_px, atol=1e-5)
            assert np.isclose(sample_std.target_response, sample_pat.target_response, atol=1e-5)
            assert np.isclose(sample_std.anchor_response, sample_pat.anchor_response, atol=1e-5)


def test_recalibrate_resets_shift_to_zero():
    config = SyntheticConfig(duration_s=1.0, vibration_amplitude_px=2.0, seed=43)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    # Process frame 10 (displaced from frame 0)
    sample_before = tracker.process(frames[10], 10 / config.fps)
    assert sample_before.valid is True

    # Recalibrate to frame 10
    tracker.recalibrate(
        DEFAULT_TARGET_ROI.crop(frames[10]),
        DEFAULT_ANCHOR_ROI.crop(frames[10]),
    )

    # Now measuring frame 10 relative to the new reference should yield ~(0.0, 0.0) px
    sample_after = tracker.process(frames[10], 10 / config.fps)
    assert sample_after.valid is True
    assert abs(sample_after.target_dx_px) < 0.05
    assert abs(sample_after.target_dy_px) < 0.05
    assert abs(sample_after.relative_dx_px) < 0.05
    assert abs(sample_after.relative_dy_px) < 0.05


def test_recalibrate_rejects_flat_patch_without_corrupting_references():
    config = SyntheticConfig(duration_s=1.0, seed=44)
    frames, _ = make_scene(config)
    tracker = PhaseCorrelationTracker(frames[0], DEFAULT_TARGET_ROI, DEFAULT_ANCHOR_ROI)

    orig_target_ref = tracker._target_ref.copy()
    orig_anchor_ref = tracker._anchor_ref.copy()

    flat_patch = np.ones((DEFAULT_TARGET_ROI.height, DEFAULT_TARGET_ROI.width), dtype=np.uint8) * 128
    valid_anchor = DEFAULT_ANCHOR_ROI.crop(frames[0])

    with pytest.raises(ValueError, match="lacks visible texture"):
        tracker.recalibrate(flat_patch, valid_anchor)

    # Verify existing references were not corrupted
    assert np.array_equal(tracker._target_ref, orig_target_ref)
    assert np.array_equal(tracker._anchor_ref, orig_anchor_ref)

    # Valid process still succeeds
    sample = tracker.process(frames[1], 1 / config.fps)
    assert sample.valid is True

