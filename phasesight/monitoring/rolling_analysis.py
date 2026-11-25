from __future__ import annotations

from dataclasses import dataclass, field
import numpy as np

from phasesight.analysis import (
    analyse_displacement,
    classify_signal_quality,
    is_anchor_contaminated,
)
from phasesight.baseline import BaselineRecord, evaluate_run_against_baseline
from phasesight.capture import calculate_timestamp_stability
from phasesight.monitoring.ring_buffer import BufferSnapshot
from phasesight.tracker import ROI


@dataclass(frozen=True)
class RollingAxisMetrics:
    available: bool
    dominant_frequency_hz: float | None
    rms_displacement_px: float | None
    peak_to_median_db: float | None
    second_harmonic_ratio: float | None
    frequency_resolution_hz: float | None
    sampling_rate_hz: float | None
    signal_quality: str  # "BUFFERING" | "VALID" | "LOW_SIGNAL" | "CONTAMINATED" | "DEGRADED"
    anchor_contaminated: bool
    anchor_dominant_frequency_hz: float | None
    anchor_peak_to_median_db: float | None
    target_dominant_frequency_hz: float | None


@dataclass(frozen=True)
class RollingAnalysisResult:
    state: str  # "BUFFERING" | "WARMING_UP" | "ACTIVE" | "DEGRADED"
    buffer_filled: int
    buffer_capacity: int
    required_warmup_samples: int
    window_duration_s: float
    valid_ratio: float
    measured_fps: float
    nyquist_hz: float
    usable_max_hz: float
    timebase_source: str
    timing_status: str
    jitter_ratio: float | None
    dropped_frames: int | None
    nperseg_used: int
    x_axis: RollingAxisMetrics
    y_axis: RollingAxisMetrics
    frequencies_hz: list[float]
    x_psd: list[float]
    y_psd: list[float]
    mean_min_phase_response: float | None
    baseline_assessment: dict | None
    warnings: list[str]
    should_reset_buffer: bool
    mean_target_response: float | None = None
    mean_anchor_response: float | None = None


def select_adaptive_nperseg(
    fs: float,
    nperseg_override: int | None = None,
    target_segment_s: float = 2.5,
) -> int:
    """Select appropriate Welch nperseg segment size for the estimated sampling rate."""
    if nperseg_override is not None:
        return max(32, int(nperseg_override))
    if fs >= 200.0:
        return 256  # exact parity with 500 FPS rotor benchmark

    for cand in (256, 128, 64, 32):
        if cand / fs <= target_segment_s:
            return cand
    return 32


def _unavailable_axis_metrics(signal_quality: str = "BUFFERING") -> RollingAxisMetrics:
    return RollingAxisMetrics(
        available=False,
        dominant_frequency_hz=None,
        rms_displacement_px=None,
        peak_to_median_db=None,
        second_harmonic_ratio=None,
        frequency_resolution_hz=None,
        sampling_rate_hz=None,
        signal_quality=signal_quality,
        anchor_contaminated=False,
        anchor_dominant_frequency_hz=None,
        anchor_peak_to_median_db=None,
        target_dominant_frequency_hz=None,
    )


def analyze_rolling_window(
    snapshot: BufferSnapshot,
    *,
    expected_fps: float = 30.0,
    timebase_source: str = "measured",
    nperseg_override: int | None = None,
    min_frequency_hz: float = 0.5,
    max_frequency_hz: float | None = None,
    target_roi: ROI | None = None,
    anchor_roi: ROI | None = None,
    baseline: BaselineRecord | None = None,
) -> RollingAnalysisResult:
    """Analyze a rolling window of motion samples into online vibration metrics."""
    warnings: list[str] = []
    buffer_filled = snapshot.count
    buffer_capacity = snapshot.capacity

    # 1. Preliminary sampling rate estimation to choose nperseg
    if timebase_source == "explicit_fps_override":
        fs_est = float(expected_fps)
    elif snapshot.count >= 2:
        dt_prelim = np.diff(snapshot.timestamps_s)
        median_dt_prelim = float(np.median(dt_prelim)) if len(dt_prelim) > 0 else 0.0
        fs_est = (1.0 / median_dt_prelim) if median_dt_prelim > 0 else float(expected_fps)
    else:
        fs_est = float(expected_fps)

    nperseg = select_adaptive_nperseg(fs_est, nperseg_override=nperseg_override)
    required_warmup_samples = 2 * nperseg

    # 2. Adaptive Active Analysis Window:
    # min(snapshot.count, max(2 * nperseg, 3 * nperseg)) capped at snapshot.capacity
    target_active_samples = min(snapshot.capacity, max(2 * nperseg, 3 * nperseg))
    active_window_samples = min(snapshot.count, target_active_samples)
    slice_start = snapshot.count - active_window_samples

    active_timestamps = snapshot.timestamps_s[slice_start:]
    active_rel_dx = snapshot.relative_dx_px[slice_start:]
    active_rel_dy = snapshot.relative_dy_px[slice_start:]
    active_anc_dx = snapshot.anchor_dx_px[slice_start:]
    active_anc_dy = snapshot.anchor_dy_px[slice_start:]
    active_tgt_dx = snapshot.target_dx_px[slice_start:]
    active_tgt_dy = snapshot.target_dy_px[slice_start:]
    active_tgt_resp = snapshot.target_response[slice_start:]
    active_anc_resp = snapshot.anchor_response[slice_start:]
    active_valid = snapshot.valid[slice_start:]

    n_active = len(active_timestamps)
    active_valid_ratio = float(np.mean(active_valid)) if n_active > 0 else 0.0
    active_duration_s = (
        float(active_timestamps[-1] - active_timestamps[0]) if n_active > 1 else 0.0
    )

    if n_active > 0:
        min_resp = np.minimum(active_tgt_resp, active_anc_resp)
        mean_min_phase_resp = float(np.mean(min_resp))
        mean_target_resp = float(np.mean(active_tgt_resp))
        mean_anchor_resp = float(np.mean(active_anc_resp))
    else:
        mean_min_phase_resp = None
        mean_target_resp = None
        mean_anchor_resp = None

    # 3. Principled Live-Stream Timing Gate on Active Window
    large_gap_count = 0
    drop_fraction = 0.0
    dropped_frames = None
    jitter_ratio = None
    max_tolerated_gap_ratio = 1.5
    max_tolerated_jitter = 0.15

    if timebase_source == "explicit_fps_override":
        measured_fps = float(expected_fps)
        timing_status = "ASSUMED_UNIFORM"
    else:
        if n_active >= 2:
            dt = np.diff(active_timestamps)
            has_non_monotonic = bool(np.any(dt <= 0))
            median_dt = float(np.median(dt)) if len(dt) > 0 else 0.0
            measured_fps = (1.0 / median_dt) if median_dt > 0 else float(expected_fps)

            if n_active < 32:
                if has_non_monotonic:
                    timing_status = "REJECTED_UNSTABLE"
                else:
                    timing_status = "BUFFERING"
            else:
                stability_report = calculate_timestamp_stability(
                    active_timestamps, nominal_fps=expected_fps
                )
                large_gap_count = stability_report.large_gap_count
                raw_dropped_count = stability_report.dropped_frames_count or 0
                raw_jitter = (
                    float(stability_report.jitter_ratio)
                    if np.isfinite(stability_report.jitter_ratio)
                    else 0.0
                )
                drop_fraction = float(raw_dropped_count) / max(1, n_active - 1)
                dropped_frames = raw_dropped_count
                jitter_ratio = raw_jitter

                # Hard DEGRADED: burst stall (> 2.5x median dt), non-monotonic, severe jitter (>= 0.22), or excessive drops (> 8%)
                is_hard_unstable = (
                    large_gap_count > 0
                    or has_non_monotonic
                    or raw_jitter >= 0.22
                    or drop_fraction > 0.08
                )

                if is_hard_unstable:
                    timing_status = "REJECTED_UNSTABLE"
                elif (
                    large_gap_count == 0
                    and drop_fraction <= 0.08
                    and raw_jitter < 0.22
                    and (raw_dropped_count > 0 or raw_jitter >= 0.05)
                ):
                    timing_status = "WARNING_JITTER"
                    warnings.append(
                        f"Minor browser frame jitter/skips ({drop_fraction:.1%} drops, jitter={raw_jitter:.1%}) — resampled onto uniform grid"
                    )
                    max_tolerated_gap_ratio = 2.5
                    max_tolerated_jitter = 0.22
                else:
                    timing_status = "STABLE"
        else:
            measured_fps = float(expected_fps)
            timing_status = "BUFFERING"

    fs = measured_fps if measured_fps > 0 else float(expected_fps)
    nyquist_hz = fs / 2.0
    usable_max_hz = min(
        max_frequency_hz if max_frequency_hz is not None else nyquist_hz * 0.9,
        nyquist_hz * 0.95,
    )

    is_severe_timing = (
        (timing_status == "REJECTED_UNSTABLE" and n_active >= 32)
        or (n_active >= 2 and np.any(np.diff(active_timestamps) <= 0))
        or large_gap_count > 0
    )
    if is_severe_timing:
        should_reset = large_gap_count > 0
        warnings.append(
            f"Severe timestamp instability detected (status={timing_status}, large_gap_count={large_gap_count})."
        )
        return RollingAnalysisResult(
            state="DEGRADED",
            buffer_filled=buffer_filled,
            buffer_capacity=buffer_capacity,
            required_warmup_samples=required_warmup_samples,
            window_duration_s=active_duration_s,
            valid_ratio=active_valid_ratio,
            measured_fps=measured_fps,
            nyquist_hz=nyquist_hz,
            usable_max_hz=usable_max_hz,
            timebase_source=timebase_source,
            timing_status=timing_status,
            jitter_ratio=jitter_ratio,
            dropped_frames=dropped_frames,
            nperseg_used=nperseg,
            x_axis=_unavailable_axis_metrics("DEGRADED"),
            y_axis=_unavailable_axis_metrics("DEGRADED"),
            frequencies_hz=[],
            x_psd=[],
            y_psd=[],
            mean_min_phase_response=mean_min_phase_resp,
            baseline_assessment=None,
            warnings=warnings,
            should_reset_buffer=should_reset,
            mean_target_response=mean_target_resp,
            mean_anchor_response=mean_anchor_resp,
        )

    if buffer_filled < nperseg:
        return RollingAnalysisResult(
            state="BUFFERING",
            buffer_filled=buffer_filled,
            buffer_capacity=buffer_capacity,
            required_warmup_samples=required_warmup_samples,
            window_duration_s=active_duration_s,
            valid_ratio=active_valid_ratio,
            measured_fps=measured_fps,
            nyquist_hz=nyquist_hz,
            usable_max_hz=usable_max_hz,
            timebase_source=timebase_source,
            timing_status=timing_status,
            jitter_ratio=jitter_ratio,
            dropped_frames=dropped_frames,
            nperseg_used=nperseg,
            x_axis=_unavailable_axis_metrics("BUFFERING"),
            y_axis=_unavailable_axis_metrics("BUFFERING"),
            frequencies_hz=[],
            x_psd=[],
            y_psd=[],
            mean_min_phase_response=mean_min_phase_resp,
            baseline_assessment=None,
            warnings=warnings,
            should_reset_buffer=False,
            mean_target_response=mean_target_resp,
            mean_anchor_response=mean_anchor_resp,
        )

    if active_valid_ratio < 0.85:
        rejection_reasons = []
        if mean_target_resp is not None and mean_target_resp < 0.15:
            rejection_reasons.append(f"target_low_response ({mean_target_resp:.2f} < 0.15)")
        elif n_active > 0 and np.count_nonzero(active_tgt_resp < 0.15) > 0:
            rejection_reasons.append(f"target_low_response ({mean_target_resp:.2f} < 0.15)" if mean_target_resp is not None else "target_low_response")

        if mean_anchor_resp is not None and mean_anchor_resp < 0.15:
            rejection_reasons.append(f"anchor_low_response ({mean_anchor_resp:.2f} < 0.15)")
        elif n_active > 0 and np.count_nonzero(active_anc_resp < 0.15) > 0:
            rejection_reasons.append(f"anchor_low_response ({mean_anchor_resp:.2f} < 0.15)" if mean_anchor_resp is not None else "anchor_low_response")

        if not rejection_reasons:
            rejection_reasons.append(f"correlation_peak_low ({mean_min_phase_resp:.2f} < 0.15)" if mean_min_phase_resp is not None else "insufficient response")

        reason_str = "; ".join(rejection_reasons)
        warnings.append(
            f"Low tracking validity ({active_valid_ratio:.1%} < 85.0%): {reason_str} — place ROIs on sharp high-contrast edges and keep camera/target rigid"
        )
        return RollingAnalysisResult(
            state="DEGRADED",
            buffer_filled=buffer_filled,
            buffer_capacity=buffer_capacity,
            required_warmup_samples=required_warmup_samples,
            window_duration_s=active_duration_s,
            valid_ratio=active_valid_ratio,
            measured_fps=measured_fps,
            nyquist_hz=nyquist_hz,
            usable_max_hz=usable_max_hz,
            timebase_source=timebase_source,
            timing_status=timing_status,
            jitter_ratio=jitter_ratio,
            dropped_frames=dropped_frames,
            nperseg_used=nperseg,
            x_axis=_unavailable_axis_metrics("DEGRADED"),
            y_axis=_unavailable_axis_metrics("DEGRADED"),
            frequencies_hz=[],
            x_psd=[],
            y_psd=[],
            mean_min_phase_response=mean_min_phase_resp,
            baseline_assessment=None,
            warnings=warnings,
            should_reset_buffer=False,
            mean_target_response=mean_target_resp,
            mean_anchor_response=mean_anchor_resp,
        )

    rel_dx = active_rel_dx.copy()
    rel_dy = active_rel_dy.copy()
    anc_dx = active_anc_dx.copy()
    anc_dy = active_anc_dy.copy()
    tgt_dx = active_tgt_dx.copy()
    tgt_dy = active_tgt_dy.copy()
    timestamps = active_timestamps.copy()

    if active_valid_ratio < 1.0:
        warnings.append(
            f"Tracking valid ratio is {active_valid_ratio:.1%}. Interpolated missing samples."
        )
        valid_idx = np.flatnonzero(active_valid)
        all_idx = np.arange(n_active)
        rel_dx = np.interp(all_idx, valid_idx, rel_dx[valid_idx])
        rel_dy = np.interp(all_idx, valid_idx, rel_dy[valid_idx])
        anc_dx = np.interp(all_idx, valid_idx, anc_dx[valid_idx])
        anc_dy = np.interp(all_idx, valid_idx, anc_dy[valid_idx])
        tgt_dx = np.interp(all_idx, valid_idx, tgt_dx[valid_idx])
        tgt_dy = np.interp(all_idx, valid_idx, tgt_dy[valid_idx])

    try:
        rel_x_res = analyse_displacement(
            timestamps,
            rel_dx,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=usable_max_hz,
            nperseg=nperseg,
            max_tolerated_gap_ratio=max_tolerated_gap_ratio,
            max_tolerated_jitter=max_tolerated_jitter,
        )
        rel_y_res = analyse_displacement(
            timestamps,
            rel_dy,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=usable_max_hz,
            nperseg=nperseg,
            max_tolerated_gap_ratio=max_tolerated_gap_ratio,
            max_tolerated_jitter=max_tolerated_jitter,
        )
        anc_x_res = analyse_displacement(
            timestamps,
            anc_dx,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=usable_max_hz,
            nperseg=nperseg,
            max_tolerated_gap_ratio=max_tolerated_gap_ratio,
            max_tolerated_jitter=max_tolerated_jitter,
        )
        anc_y_res = analyse_displacement(
            timestamps,
            anc_dy,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=usable_max_hz,
            nperseg=nperseg,
            max_tolerated_gap_ratio=max_tolerated_gap_ratio,
            max_tolerated_jitter=max_tolerated_jitter,
        )
        tgt_x_res = analyse_displacement(
            timestamps,
            tgt_dx,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=usable_max_hz,
            nperseg=nperseg,
            max_tolerated_gap_ratio=max_tolerated_gap_ratio,
            max_tolerated_jitter=max_tolerated_jitter,
        )
        tgt_y_res = analyse_displacement(
            timestamps,
            tgt_dy,
            min_frequency_hz=min_frequency_hz,
            max_frequency_hz=usable_max_hz,
            nperseg=nperseg,
            max_tolerated_gap_ratio=max_tolerated_gap_ratio,
            max_tolerated_jitter=max_tolerated_jitter,
        )
    except ValueError as exc:
        warnings.append(f"Spectral analysis failed: {exc}")
        return RollingAnalysisResult(
            state="DEGRADED",
            buffer_filled=buffer_filled,
            buffer_capacity=buffer_capacity,
            required_warmup_samples=required_warmup_samples,
            window_duration_s=active_duration_s,
            valid_ratio=active_valid_ratio,
            measured_fps=measured_fps,
            nyquist_hz=nyquist_hz,
            usable_max_hz=usable_max_hz,
            timebase_source=timebase_source,
            timing_status=timing_status,
            jitter_ratio=jitter_ratio,
            dropped_frames=dropped_frames,
            nperseg_used=nperseg,
            x_axis=_unavailable_axis_metrics("DEGRADED"),
            y_axis=_unavailable_axis_metrics("DEGRADED"),
            frequencies_hz=[],
            x_psd=[],
            y_psd=[],
            mean_min_phase_response=mean_min_phase_resp,
            baseline_assessment=None,
            warnings=warnings,
            should_reset_buffer=False,
            mean_target_response=mean_target_resp,
            mean_anchor_response=mean_anchor_resp,
        )
    except ValueError as exc:
        warnings.append(f"Spectral analysis failed: {exc}")
        return RollingAnalysisResult(
            state="DEGRADED",
            buffer_filled=buffer_filled,
            buffer_capacity=buffer_capacity,
            required_warmup_samples=required_warmup_samples,
            window_duration_s=active_duration_s,
            valid_ratio=active_valid_ratio,
            measured_fps=measured_fps,
            nyquist_hz=nyquist_hz,
            usable_max_hz=usable_max_hz,
            timebase_source=timebase_source,
            timing_status=timing_status,
            jitter_ratio=jitter_ratio,
            dropped_frames=dropped_frames,
            nperseg_used=nperseg,
            x_axis=_unavailable_axis_metrics("DEGRADED"),
            y_axis=_unavailable_axis_metrics("DEGRADED"),
            frequencies_hz=[],
            x_psd=[],
            y_psd=[],
            mean_min_phase_response=mean_min_phase_resp,
            baseline_assessment=None,
            warnings=warnings,
            should_reset_buffer=False,
        )

    x_contam = is_anchor_contaminated(rel_x_res, anc_x_res)
    y_contam = is_anchor_contaminated(rel_y_res, anc_y_res)

    x_qual = classify_signal_quality(
        rel_x_res, mean_phase_response=mean_min_phase_resp
    )
    y_qual = classify_signal_quality(
        rel_y_res, mean_phase_response=mean_min_phase_resp
    )

    x_sig_qual = "CONTAMINATED" if x_contam else x_qual
    y_sig_qual = "CONTAMINATED" if y_contam else y_qual

    x_metrics = RollingAxisMetrics(
        available=True,
        dominant_frequency_hz=float(rel_x_res.dominant_frequency_hz),
        rms_displacement_px=float(rel_x_res.rms_px),
        peak_to_median_db=float(rel_x_res.peak_to_median_db),
        second_harmonic_ratio=rel_x_res.second_harmonic_ratio,
        frequency_resolution_hz=float(rel_x_res.frequency_resolution_hz),
        sampling_rate_hz=float(rel_x_res.sampling_rate_hz),
        signal_quality=x_sig_qual,
        anchor_contaminated=x_contam,
        anchor_dominant_frequency_hz=float(anc_x_res.dominant_frequency_hz),
        anchor_peak_to_median_db=float(anc_x_res.peak_to_median_db),
        target_dominant_frequency_hz=float(tgt_x_res.dominant_frequency_hz),
    )

    y_metrics = RollingAxisMetrics(
        available=True,
        dominant_frequency_hz=float(rel_y_res.dominant_frequency_hz),
        rms_displacement_px=float(rel_y_res.rms_px),
        peak_to_median_db=float(rel_y_res.peak_to_median_db),
        second_harmonic_ratio=rel_y_res.second_harmonic_ratio,
        frequency_resolution_hz=float(rel_y_res.frequency_resolution_hz),
        sampling_rate_hz=float(rel_y_res.sampling_rate_hz),
        signal_quality=y_sig_qual,
        anchor_contaminated=y_contam,
        anchor_dominant_frequency_hz=float(anc_y_res.dominant_frequency_hz),
        anchor_peak_to_median_db=float(anc_y_res.peak_to_median_db),
        target_dominant_frequency_hz=float(tgt_y_res.dominant_frequency_hz),
    )

    if buffer_filled < 2 * nperseg:
        state = "WARMING_UP"
        warnings.append(
            f"Warming up: buffer contains {buffer_filled} samples (< 2 * nperseg = {2 * nperseg}). "
            "Preliminary spectral estimate with fewer than 3 Welch segments."
        )
    else:
        state = "ACTIVE"

    baseline_assessment = None
    if (
        baseline is not None
        and state == "ACTIVE"
        and target_roi is not None
        and anchor_roi is not None
    ):
        try:
            summary_dict = {
                "x_axis": {
                    "dominant_frequency_hz": x_metrics.dominant_frequency_hz,
                    "rms_displacement_px": x_metrics.rms_displacement_px,
                    "peak_to_median_db": x_metrics.peak_to_median_db,
                    "second_harmonic_ratio": x_metrics.second_harmonic_ratio,
                    "signal_quality": x_metrics.signal_quality,
                },
                "y_axis": {
                    "dominant_frequency_hz": y_metrics.dominant_frequency_hz,
                    "rms_displacement_px": y_metrics.rms_displacement_px,
                    "peak_to_median_db": y_metrics.peak_to_median_db,
                    "second_harmonic_ratio": y_metrics.second_harmonic_ratio,
                    "signal_quality": y_metrics.signal_quality,
                },
                "target_roi_xywh": {
                    "x": int(target_roi.x),
                    "y": int(target_roi.y),
                    "width": int(target_roi.width),
                    "height": int(target_roi.height),
                },
                "anchor_roi_xywh": {
                    "x": int(anchor_roi.x),
                    "y": int(anchor_roi.y),
                    "width": int(anchor_roi.width),
                    "height": int(anchor_roi.height),
                },
                "fps_used": float(fs),
                "sampling_rate_hz": float(fs),
            }
            eval_axis = "both"
            curr_x_valid = x_metrics.signal_quality == "VALID"
            curr_y_valid = y_metrics.signal_quality == "VALID"
            if curr_x_valid and not curr_y_valid:
                eval_axis = "x"
            elif curr_y_valid and not curr_x_valid:
                eval_axis = "y"

            eval_res = evaluate_run_against_baseline(
                summary_dict, baseline, axis=eval_axis
            )
            baseline_assessment = eval_res.to_dict()
            baseline_assessment["overall_status"] = eval_res.status
            dev_zs = [
                abs(v.get("z_robust", 0.0))
                for v in baseline_assessment.get("deviations", {}).values()
                if v and v.get("z_robust") is not None
            ]
            baseline_assessment["max_z_score"] = (
                max(dev_zs) if dev_zs else 0.0
            )
        except Exception as exc:
            warnings.append(f"Baseline assessment failed: {exc}")

    return RollingAnalysisResult(
        state=state,
        buffer_filled=buffer_filled,
        buffer_capacity=buffer_capacity,
        required_warmup_samples=required_warmup_samples,
        window_duration_s=active_duration_s,
        valid_ratio=active_valid_ratio,
        measured_fps=measured_fps,
        nyquist_hz=nyquist_hz,
        usable_max_hz=usable_max_hz,
        timebase_source=timebase_source,
        timing_status=timing_status,
        jitter_ratio=jitter_ratio,
        dropped_frames=dropped_frames,
        nperseg_used=nperseg,
        x_axis=x_metrics,
        y_axis=y_metrics,
        frequencies_hz=[float(f) for f in rel_x_res.frequencies_hz],
        x_psd=[float(p) for p in rel_x_res.psd_px2_per_hz],
        y_psd=[float(p) for p in rel_y_res.psd_px2_per_hz],
        mean_min_phase_response=mean_min_phase_resp,
        baseline_assessment=baseline_assessment,
        warnings=warnings,
        should_reset_buffer=False,
        mean_target_response=mean_target_resp,
        mean_anchor_response=mean_anchor_resp,
    )
