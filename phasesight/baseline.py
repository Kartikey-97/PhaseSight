"""PhaseSight Statistical Baseline Engine.

Aggregates multiple baseline video inspection runs (N >= 3) into an immutable BaselineRecord
using robust statistics (Median and Median Absolute Deviation scaled by 1.4826).
Provides two-stage screening (Confidence Gate followed by Review Gate) against healthy baselines
in the 2D pixel domain without physical unit conversions or mechanical fault diagnosis.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

import numpy as np

NORMAL_SCALE_FACTOR: float = 1.482602218505602

DEFAULT_FEATURE_EPSILONS: dict[str, float] = {
    "dominant_frequency_hz": 0.020,
    "rms_displacement_px": 0.005,
    "peak_to_median_db": 1.000,
    "second_harmonic_ratio": 0.010,
}

NON_DIAGNOSTIC_INTERPRETATION: str = (
    "A Review status indicates a measured statistical shift relative to the reference baseline, "
    "not a diagnosed machine fault or failure mode."
)


@dataclass(frozen=True)
class FeatureStats:
    """Robust statistical parameters for a single scalar vibration feature."""

    median: float | None
    mad: float | None
    scale_factor: float
    epsilon: float
    sample_count: int
    raw_values: list[float] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "median": float(self.median) if self.median is not None else None,
            "mad": float(self.mad) if self.mad is not None else None,
            "scale_factor": float(self.scale_factor),
            "epsilon": float(self.epsilon),
            "sample_count": int(self.sample_count),
            "raw_values": [float(v) for v in self.raw_values],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureStats:
        return cls(
            median=float(data["median"]) if data.get("median") is not None else None,
            mad=float(data["mad"]) if data.get("mad") is not None else None,
            scale_factor=float(data.get("scale_factor", NORMAL_SCALE_FACTOR)),
            epsilon=float(data["epsilon"]),
            sample_count=int(data["sample_count"]),
            raw_values=[float(x) for x in data.get("raw_values", [])],
        )


@dataclass(frozen=True)
class AxisBaseline:
    """Baseline parameters for all tracked vibration features on a single spatial axis."""

    dominant_frequency_hz: FeatureStats
    rms_displacement_px: FeatureStats
    peak_to_median_db: FeatureStats
    second_harmonic_ratio: FeatureStats | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "dominant_frequency_hz": self.dominant_frequency_hz.to_dict(),
            "rms_displacement_px": self.rms_displacement_px.to_dict(),
            "peak_to_median_db": self.peak_to_median_db.to_dict(),
            "second_harmonic_ratio": (
                self.second_harmonic_ratio.to_dict()
                if self.second_harmonic_ratio is not None
                else None
            ),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AxisBaseline:
        harm_data = data.get("second_harmonic_ratio")
        harm = FeatureStats.from_dict(harm_data) if harm_data is not None else None
        return cls(
            dominant_frequency_hz=FeatureStats.from_dict(data["dominant_frequency_hz"]),
            rms_displacement_px=FeatureStats.from_dict(data["rms_displacement_px"]),
            peak_to_median_db=FeatureStats.from_dict(data["peak_to_median_db"]),
            second_harmonic_ratio=harm,
        )


@dataclass(frozen=True)
class BaselineRecord:
    """Immutable statistical baseline capturing healthy machine vibration behavior."""

    baseline_id: str
    asset_id: str
    created_at: str
    run_count: int
    target_roi: dict[str, int]
    anchor_roi: dict[str, int]
    sampling_rate_hz: float
    x_axis: AxisBaseline
    y_axis: AxisBaseline
    baseline_run_ids: list[str] = field(default_factory=list)
    notes: str = ""
    version: str = "1.0"

    def to_dict(self) -> dict[str, Any]:
        return {
            "baseline_id": str(self.baseline_id),
            "asset_id": str(self.asset_id),
            "created_at": str(self.created_at),
            "run_count": int(self.run_count),
            "target_roi": {k: int(v) for k, v in self.target_roi.items()},
            "anchor_roi": {k: int(v) for k, v in self.anchor_roi.items()},
            "sampling_rate_hz": float(self.sampling_rate_hz),
            "x_axis": self.x_axis.to_dict(),
            "y_axis": self.y_axis.to_dict(),
            "baseline_run_ids": [str(x) for x in self.baseline_run_ids],
            "notes": str(self.notes),
            "version": str(self.version),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineRecord:
        return cls(
            baseline_id=str(data["baseline_id"]),
            asset_id=str(data["asset_id"]),
            created_at=str(data["created_at"]),
            run_count=int(data["run_count"]),
            target_roi={k: int(v) for k, v in data["target_roi"].items()},
            anchor_roi={k: int(v) for k, v in data["anchor_roi"].items()},
            sampling_rate_hz=float(data["sampling_rate_hz"]),
            x_axis=AxisBaseline.from_dict(data["x_axis"]),
            y_axis=AxisBaseline.from_dict(data["y_axis"]),
            baseline_run_ids=[str(x) for x in data.get("baseline_run_ids", [])],
            notes=str(data.get("notes", "")),
            version=str(data.get("version", "1.0")),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> BaselineRecord:
        return cls.from_dict(json.loads(json_str))


@dataclass(frozen=True)
class FeatureDeviation:
    """Standardized deviation scoring for a single feature on an axis."""

    feature_name: str
    axis: str
    current_value: float | None
    baseline_median: float | None
    baseline_mad: float | None
    z_robust: float | None
    is_trigger: bool
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature_name": str(self.feature_name),
            "axis": str(self.axis),
            "current_value": float(self.current_value) if self.current_value is not None else None,
            "baseline_median": float(self.baseline_median) if self.baseline_median is not None else None,
            "baseline_mad": float(self.baseline_mad) if self.baseline_mad is not None else None,
            "z_robust": float(self.z_robust) if self.z_robust is not None else None,
            "is_trigger": bool(self.is_trigger),
            "notes": str(self.notes),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FeatureDeviation:
        return cls(
            feature_name=str(data["feature_name"]),
            axis=str(data["axis"]),
            current_value=float(data["current_value"]) if data.get("current_value") is not None else None,
            baseline_median=float(data["baseline_median"]) if data.get("baseline_median") is not None else None,
            baseline_mad=float(data["baseline_mad"]) if data.get("baseline_mad") is not None else None,
            z_robust=float(data["z_robust"]) if data.get("z_robust") is not None else None,
            is_trigger=bool(data["is_trigger"]),
            notes=str(data.get("notes", "")),
        )


@dataclass(frozen=True)
class BaselineEvaluation:
    """Two-stage evaluation result screening an inspection run against a BaselineRecord."""

    status: str  # 'Normal', 'Review', or 'Low confidence'
    confidence_passed: bool
    reasons: list[str]
    trigger_features: list[str]
    deviations: dict[str, FeatureDeviation]
    z_threshold: float
    baseline_id: str
    asset_id: str
    evaluated_at: str
    interpretation: str = NON_DIAGNOSTIC_INTERPRETATION

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": str(self.status),
            "confidence_passed": bool(self.confidence_passed),
            "reasons": [str(r) for r in self.reasons],
            "trigger_features": [str(t) for t in self.trigger_features],
            "deviations": {k: v.to_dict() for k, v in self.deviations.items()},
            "z_threshold": float(self.z_threshold),
            "baseline_id": str(self.baseline_id),
            "asset_id": str(self.asset_id),
            "evaluated_at": str(self.evaluated_at),
            "interpretation": str(self.interpretation),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BaselineEvaluation:
        devs = {
            k: FeatureDeviation.from_dict(v)
            for k, v in data.get("deviations", {}).items()
        }
        return cls(
            status=str(data["status"]),
            confidence_passed=bool(data["confidence_passed"]),
            reasons=[str(r) for r in data.get("reasons", [])],
            trigger_features=[str(t) for t in data.get("trigger_features", [])],
            deviations=devs,
            z_threshold=float(data["z_threshold"]),
            baseline_id=str(data["baseline_id"]),
            asset_id=str(data["asset_id"]),
            evaluated_at=str(data["evaluated_at"]),
            interpretation=str(
                data.get("interpretation", NON_DIAGNOSTIC_INTERPRETATION)
            ),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> BaselineEvaluation:
        return cls.from_dict(json.loads(json_str))


def compute_robust_stats(
    values: list[float | None],
    epsilon: float,
    scale_factor: float = NORMAL_SCALE_FACTOR,
) -> FeatureStats:
    """Calculate sample median and scaled MAD across scalar values, ignoring None and non-finite numbers."""
    valid_vals = [
        float(v) for v in values if v is not None and np.isfinite(v)
    ]
    if not valid_vals:
        return FeatureStats(
            median=None,
            mad=None,
            scale_factor=float(scale_factor),
            epsilon=float(epsilon),
            sample_count=0,
            raw_values=[],
        )
    arr = np.asarray(valid_vals, dtype=np.float64)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    return FeatureStats(
        median=med,
        mad=mad,
        scale_factor=float(scale_factor),
        epsilon=float(epsilon),
        sample_count=len(valid_vals),
        raw_values=[float(x) for x in valid_vals],
    )


def serialize_baseline(baseline: BaselineRecord, filepath: str | Path | None = None) -> str:
    """Serialize BaselineRecord to formatted JSON string and optionally save to file."""
    payload = baseline.to_json(indent=2)
    if filepath is not None:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(payload, encoding="utf-8")
    return payload


def deserialize_baseline(source: str | Path | dict[str, Any]) -> BaselineRecord:
    """Load BaselineRecord from JSON string, JSON file path, or dictionary."""
    if isinstance(source, dict):
        return BaselineRecord.from_dict(source)
    if isinstance(source, Path):
        content = source.read_text(encoding="utf-8")
        return BaselineRecord.from_json(content)
    if isinstance(source, str):
        trimmed = source.strip()
        if trimmed.startswith("{"):
            return BaselineRecord.from_json(trimmed)
        path = Path(source)
        if path.exists():
            return BaselineRecord.from_json(path.read_text(encoding="utf-8"))
        return BaselineRecord.from_json(source)
    raise TypeError(f"Unsupported source type for deserialize_baseline: {type(source)}")


def _extract_roi(run: dict[str, Any], roi_type: str) -> dict[str, int]:
    """Extract ROI dictionary from summary under target_roi_xywh or target_roi."""
    for key in (f"{roi_type}_roi_xywh", f"{roi_type}_roi"):
        if key in run:
            roi_val = run[key]
            if isinstance(roi_val, dict):
                return {k: int(v) for k, v in roi_val.items()}
            if isinstance(roi_val, (list, tuple)) and len(roi_val) == 4:
                return {"x": int(roi_val[0]), "y": int(roi_val[1]), "width": int(roi_val[2]), "height": int(roi_val[3])}
    raise ValueError(f"Run missing {roi_type}_roi_xywh or {roi_type}_roi")


def _rois_match(r1: dict[str, int], r2: dict[str, int], tolerance: int = 2) -> bool:
    """Check if two ROIs match within pixel tolerance."""
    return (
        abs(r1["x"] - r2["x"]) <= tolerance
        and abs(r1["y"] - r2["y"]) <= tolerance
        and abs(r1["width"] - r2["width"]) <= tolerance
        and abs(r1["height"] - r2["height"]) <= tolerance
    )


def build_baseline(
    runs: list[dict[str, Any]],
    *,
    asset_id: str = "default_asset",
    min_runs: int = 3,
    require_valid_axes: list[str] | None = None,
    feature_epsilons: dict[str, float] | None = None,
    notes: str = "",
) -> BaselineRecord:
    """Aggregate N >= 3 healthy inspection runs into an immutable BaselineRecord using Median and scaled MAD."""
    import datetime

    if len(runs) < min_runs:
        raise ValueError(
            f"Building a baseline requires at least {min_runs} runs, got {len(runs)}"
        )

    eps = dict(DEFAULT_FEATURE_EPSILONS)
    if feature_epsilons:
        eps.update(feature_epsilons)

    ref_run = runs[0]
    ref_target_roi = _extract_roi(ref_run, "target")
    ref_anchor_roi = _extract_roi(ref_run, "anchor")
    ref_fps = float(ref_run.get("fps_used", ref_run.get("sampling_rate_hz", 0.0)))

    run_ids: list[str] = []
    x_freqs, x_rmss, x_dbs, x_harms = [], [], [], []
    y_freqs, y_rmss, y_dbs, y_harms = [], [], [], []

    valid_x_count = 0
    valid_y_count = 0

    for idx, run in enumerate(runs):
        run_id = run.get("video", f"run_{idx + 1}")
        run_ids.append(str(run_id))

        if "x_axis" not in run or "y_axis" not in run:
            raise ValueError(f"Run {idx + 1} is missing x_axis or y_axis")

        # Track valid quality per axis
        x_q = run["x_axis"].get("signal_quality", "UNKNOWN")
        y_q = run["y_axis"].get("signal_quality", "UNKNOWN")
        if x_q == "VALID":
            valid_x_count += 1
        if y_q == "VALID":
            valid_y_count += 1

        if require_valid_axes:
            for req_ax in require_valid_axes:
                q = run[f"{req_ax.lower()}_axis"].get("signal_quality", "UNKNOWN")
                if q != "VALID":
                    raise ValueError(
                        f"Baseline run {idx + 1} {req_ax.upper()}-axis signal quality is '{q}', expected 'VALID'."
                    )

        # Check ROI spatial consistency
        t_roi = _extract_roi(run, "target")
        a_roi = _extract_roi(run, "anchor")
        if not _rois_match(ref_target_roi, t_roi, tolerance=2):
            raise ValueError(
                f"Target ROI in run {idx + 1} ({t_roi}) diverges from reference ROI ({ref_target_roi})"
            )
        if not _rois_match(ref_anchor_roi, a_roi, tolerance=2):
            raise ValueError(
                f"Anchor ROI in run {idx + 1} ({a_roi}) diverges from reference ROI ({ref_anchor_roi})"
            )

        # Check sampling rate consistency (+/- 2%)
        fps = float(run.get("fps_used", run.get("sampling_rate_hz", 0.0)))
        if ref_fps > 0 and abs(fps - ref_fps) / ref_fps > 0.02:
            raise ValueError(
                f"Sampling rate in run {idx + 1} ({fps:.2f} Hz) differs by >2% from reference ({ref_fps:.2f} Hz)"
            )

        # Extract features
        x_freqs.append(run["x_axis"].get("dominant_frequency_hz"))
        x_rmss.append(run["x_axis"].get("rms_displacement_px"))
        x_dbs.append(run["x_axis"].get("peak_to_median_db"))
        x_harms.append(run["x_axis"].get("second_harmonic_ratio"))

        y_freqs.append(run["y_axis"].get("dominant_frequency_hz"))
        y_rmss.append(run["y_axis"].get("rms_displacement_px"))
        y_dbs.append(run["y_axis"].get("peak_to_median_db"))
        y_harms.append(run["y_axis"].get("second_harmonic_ratio"))

    # When require_valid_axes is not explicitly provided, at least one axis must be VALID across all runs
    if not require_valid_axes and valid_x_count < len(runs) and valid_y_count < len(runs):
        raise ValueError(
            "Baseline runs must have consistently valid signal quality on at least one axis "
            f"(X valid runs: {valid_x_count}/{len(runs)}, Y valid runs: {valid_y_count}/{len(runs)})."
        )

    x_harm_stats = (
        compute_robust_stats(x_harms, epsilon=eps["second_harmonic_ratio"])
        if any(h is not None for h in x_harms)
        else None
    )
    y_harm_stats = (
        compute_robust_stats(y_harms, epsilon=eps["second_harmonic_ratio"])
        if any(h is not None for h in y_harms)
        else None
    )

    x_axis = AxisBaseline(
        dominant_frequency_hz=compute_robust_stats(x_freqs, epsilon=eps["dominant_frequency_hz"]),
        rms_displacement_px=compute_robust_stats(x_rmss, epsilon=eps["rms_displacement_px"]),
        peak_to_median_db=compute_robust_stats(x_dbs, epsilon=eps["peak_to_median_db"]),
        second_harmonic_ratio=x_harm_stats,
    )
    y_axis = AxisBaseline(
        dominant_frequency_hz=compute_robust_stats(y_freqs, epsilon=eps["dominant_frequency_hz"]),
        rms_displacement_px=compute_robust_stats(y_rmss, epsilon=eps["rms_displacement_px"]),
        peak_to_median_db=compute_robust_stats(y_dbs, epsilon=eps["peak_to_median_db"]),
        second_harmonic_ratio=y_harm_stats,
    )

    baseline_id = (
        f"base_{asset_id}_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    )

    return BaselineRecord(
        baseline_id=baseline_id,
        asset_id=str(asset_id),
        created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        run_count=len(runs),
        target_roi=ref_target_roi,
        anchor_roi=ref_anchor_roi,
        sampling_rate_hz=ref_fps,
        x_axis=x_axis,
        y_axis=y_axis,
        baseline_run_ids=run_ids,
        notes=str(notes),
        version="1.0",
    )


def _compute_feature_deviation(
    feature_name: str,
    axis: str,
    current_val: float | None,
    stats: FeatureStats,
    z_threshold: float,
) -> FeatureDeviation:
    """Compute z_robust = (x_curr - median) / (1.4826 * MAD + epsilon)."""
    if current_val is None or stats.median is None or stats.mad is None:
        return FeatureDeviation(
            feature_name=feature_name,
            axis=axis,
            current_value=None,
            baseline_median=stats.median,
            baseline_mad=stats.mad,
            z_robust=None,
            is_trigger=False,
            notes="Feature unavailable or unobservable",
        )

    c_val = float(current_val)
    med = float(stats.median)
    mad = float(stats.mad)
    denom = stats.scale_factor * mad + stats.epsilon
    z = (c_val - med) / denom
    is_trigger = abs(z) >= z_threshold

    return FeatureDeviation(
        feature_name=feature_name,
        axis=axis,
        current_value=c_val,
        baseline_median=med,
        baseline_mad=mad,
        z_robust=float(z),
        is_trigger=is_trigger,
        notes=f"{'Trigger' if is_trigger else 'Normal'} (|z|={abs(z):.2f})",
    )


def _compute_harmonic_deviation(
    axis: str,
    current_harm: float | None,
    base_harm_stats: FeatureStats | None,
    z_threshold: float,
) -> FeatureDeviation | None:
    """Handle tri-state second harmonic ratio deviation logic cleanly."""
    eps = DEFAULT_FEATURE_EPSILONS["second_harmonic_ratio"]
    if current_harm is None and (base_harm_stats is None or base_harm_stats.median is None):
        return None

    # Case 1: Harmonic emergence (absent in baseline, present in current)
    if (base_harm_stats is None or base_harm_stats.median is None) and current_harm is not None:
        c_val = float(current_harm)
        z = c_val / eps
        is_trigger = abs(z) >= z_threshold
        return FeatureDeviation(
            feature_name="second_harmonic_ratio",
            axis=axis,
            current_value=c_val,
            baseline_median=0.0,
            baseline_mad=0.0,
            z_robust=float(z),
            is_trigger=is_trigger,
            notes="Harmonic emergence (previously absent in baseline)",
        )

    # Case 2: Harmonic disappeared (present in baseline, absent in current)
    if base_harm_stats is not None and base_harm_stats.median is not None and current_harm is None:
        med = float(base_harm_stats.median)
        mad = float(base_harm_stats.mad or 0.0)
        denom = base_harm_stats.scale_factor * mad + eps
        z = -med / denom
        is_trigger = abs(z) >= z_threshold
        return FeatureDeviation(
            feature_name="second_harmonic_ratio",
            axis=axis,
            current_value=None,
            baseline_median=med,
            baseline_mad=mad,
            z_robust=float(z),
            is_trigger=is_trigger,
            notes="Harmonic absent in current capture (present in baseline)",
        )

    # Case 3: Both present
    if base_harm_stats is not None and current_harm is not None:
        return _compute_feature_deviation(
            "second_harmonic_ratio",
            axis,
            current_harm,
            base_harm_stats,
            z_threshold,
        )

    return None


def evaluate_run_against_baseline(
    current: dict[str, Any],
    baseline: BaselineRecord,
    *,
    z_threshold: float = 3.0,
    axis: str = "both",
) -> BaselineEvaluation:
    """Screen an inspection run against a BaselineRecord using Confidence and Review Gates."""
    import datetime

    reasons: list[str] = []
    confidence_passed = True

    if "x_axis" not in current or "y_axis" not in current:
        reasons.append("Current run dictionary is missing 'x_axis' or 'y_axis'")
        confidence_passed = False

    if confidence_passed:
        curr_t_roi = _extract_roi(current, "target")
        curr_a_roi = _extract_roi(current, "anchor")
        if not _rois_match(baseline.target_roi, curr_t_roi, tolerance=2):
            reasons.append(
                f"Target ROI ({curr_t_roi}) does not match baseline Target ROI ({baseline.target_roi})"
            )
            confidence_passed = False
        if not _rois_match(baseline.anchor_roi, curr_a_roi, tolerance=2):
            reasons.append(
                f"Anchor ROI ({curr_a_roi}) does not match baseline Anchor ROI ({baseline.anchor_roi})"
            )
            confidence_passed = False

    axes_to_eval = ["x", "y"] if axis.lower() == "both" else [axis.lower()]

    if confidence_passed:
        for ax in axes_to_eval:
            q = current[f"{ax}_axis"].get("signal_quality", "UNKNOWN")
            if q != "VALID":
                reasons.append(
                    f"Current {ax.upper()}-axis signal quality is '{q}' "
                    f"(prominence {current[f'{ax}_axis'].get('peak_to_median_db', 0.0):.1f} dB)"
                )
                confidence_passed = False

    if not confidence_passed:
        return BaselineEvaluation(
            status="Low confidence",
            confidence_passed=False,
            reasons=reasons,
            trigger_features=[],
            deviations={},
            z_threshold=float(z_threshold),
            baseline_id=str(baseline.baseline_id),
            asset_id=str(baseline.asset_id),
            evaluated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            interpretation=NON_DIAGNOSTIC_INTERPRETATION,
        )

    axes_to_eval = ["x", "y"] if axis.lower() == "both" else [axis.lower()]
    deviations: dict[str, FeatureDeviation] = {}
    triggers: list[str] = []

    for ax in axes_to_eval:
        curr_axis_data = current[f"{ax}_axis"]
        base_axis_stats = getattr(baseline, f"{ax}_axis")

        dev_freq = _compute_feature_deviation(
            "dominant_frequency_hz",
            ax,
            curr_axis_data.get("dominant_frequency_hz"),
            base_axis_stats.dominant_frequency_hz,
            z_threshold,
        )
        deviations[f"{ax}_dominant_frequency_hz"] = dev_freq
        if dev_freq.is_trigger:
            triggers.append(f"{ax.upper()} Dominant Frequency ({dev_freq.z_robust:+.2f} z)")

        dev_rms = _compute_feature_deviation(
            "rms_displacement_px",
            ax,
            curr_axis_data.get("rms_displacement_px"),
            base_axis_stats.rms_displacement_px,
            z_threshold,
        )
        deviations[f"{ax}_rms_displacement_px"] = dev_rms
        if dev_rms.is_trigger:
            triggers.append(f"{ax.upper()} RMS Displacement ({dev_rms.z_robust:+.2f} z)")

        dev_db = _compute_feature_deviation(
            "peak_to_median_db",
            ax,
            curr_axis_data.get("peak_to_median_db"),
            base_axis_stats.peak_to_median_db,
            z_threshold,
        )
        deviations[f"{ax}_peak_to_median_db"] = dev_db
        if dev_db.is_trigger:
            triggers.append(f"{ax.upper()} Peak Prominence dB ({dev_db.z_robust:+.2f} z)")

        curr_harm = curr_axis_data.get("second_harmonic_ratio")
        base_harm_stats = base_axis_stats.second_harmonic_ratio
        dev_harm = _compute_harmonic_deviation(ax, curr_harm, base_harm_stats, z_threshold)
        if dev_harm is not None:
            deviations[f"{ax}_second_harmonic_ratio"] = dev_harm
            if dev_harm.is_trigger:
                triggers.append(f"{ax.upper()} 2x Harmonic Ratio ({dev_harm.z_robust:+.2f} z)")

    status = "Review" if len(triggers) > 0 else "Normal"

    return BaselineEvaluation(
        status=status,
        confidence_passed=True,
        reasons=[],
        trigger_features=triggers,
        deviations=deviations,
        z_threshold=float(z_threshold),
        baseline_id=str(baseline.baseline_id),
        asset_id=str(baseline.asset_id),
        evaluated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        interpretation=NON_DIAGNOSTIC_INTERPRETATION,
    )
