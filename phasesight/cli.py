from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analysis import compare_inspection_summaries
from .baseline import (
    build_baseline,
    deserialize_baseline,
    evaluate_run_against_baseline,
    serialize_baseline,
)
from .synthetic import SyntheticConfig, make_scene, write_video
from .validation import run_validation_suite
from .video import analyse_video, parse_roi


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phasesight", description="PhaseSight validation prototype")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Run deterministic synthetic validation tests")
    validate.add_argument("--json", type=Path, default=Path("validation_results.json"))

    generate = sub.add_parser("generate-synthetic", help="Create a synthetic vibration MP4")
    generate.add_argument("output", type=Path)
    generate.add_argument("--frequency", type=float, default=8.5)
    generate.add_argument("--amplitude", type=float, default=0.35)
    generate.add_argument("--fps", type=int, default=60)
    generate.add_argument("--duration", type=float, default=10.0)
    generate.add_argument("--camera-shake", type=float, default=0.65)
    generate.add_argument("--camera-y-shake", type=float, default=0.25)
    generate.add_argument("--noise", type=float, default=1.5)
    generate.add_argument("--second-harmonic", type=float, default=0.0)
    generate.add_argument("--lighting-depth", type=float, default=0.08)
    generate.add_argument("--seed", type=int, default=7)

    inspect = sub.add_parser("inspect", help="Measure a video using target ROI minus anchor ROI motion")
    inspect.add_argument("video", type=Path)
    inspect.add_argument("--target", required=True, help="x,y,width,height")
    inspect.add_argument("--anchor", required=True, help="x,y,width,height")
    inspect.add_argument("--out", type=Path, default=Path("phasesight_output"))
    inspect.add_argument("--fps", type=float, default=None, help="Override video FPS metadata")
    inspect.add_argument("--min-frequency", type=float, default=0.5)
    inspect.add_argument("--max-frequency", type=float, default=None)
    inspect.add_argument("--nperseg", type=int, default=256)

    compare = sub.add_parser("compare", help="Compare two inspection summary JSON files")
    compare.add_argument("baseline", type=Path)
    compare.add_argument("current", type=Path)
    compare.add_argument("--axis", choices=["x", "y"], default="x")
    compare.add_argument("--warning-rms-change", type=float, default=25.0)
    compare.add_argument("--alert-rms-change", type=float, default=50.0)
    compare.add_argument("--noise-floor-summary", type=Path, default=None, help="Optional machine-off/no-motion summary for this camera setup")
    compare.add_argument("--noise-floor-multiple", type=float, default=3.0)
    compare.add_argument("--out", type=Path, default=Path("comparison.json"))

    ui = sub.add_parser("ui", help="Launch the local Streamlit inspection interface")
    ui.add_argument("--port", type=int, default=8501, help="Port to run Streamlit on")
    ui.add_argument("--host", type=str, default="localhost", help="Host address to bind to")

    build_base = sub.add_parser(
        "build-baseline",
        help="Aggregate >= 3 healthy inspection runs into an immutable BaselineRecord",
    )
    build_base.add_argument("runs", nargs="+", type=Path, help="Paths to >= 3 inspection summary JSON files")
    build_base.add_argument("--asset-id", type=str, default="default_asset", help="Asset identifier")
    build_base.add_argument("--min-runs", type=int, default=3, help="Minimum required runs")
    build_base.add_argument("--notes", type=str, default="", help="Optional notes on operating condition")
    build_base.add_argument("--out", type=Path, default=Path("baseline.json"), help="Output BaselineRecord JSON path")

    assess = sub.add_parser("assess", help="Screen a current inspection summary against a BaselineRecord")
    assess.add_argument("current", type=Path, help="Path to current inspection summary JSON")
    assess.add_argument("baseline", type=Path, help="Path to BaselineRecord JSON")
    assess.add_argument("--threshold", type=float, default=3.0, help="Robust z-score threshold (default: 3.0)")
    assess.add_argument("--axis", choices=["x", "y", "both"], default="both", help="Axis to evaluate")
    assess.add_argument("--out", type=Path, default=Path("assessment_report.json"), help="Output assessment JSON path")
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "validate":
        results = run_validation_suite()
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(results, indent=2), encoding="utf-8")
        for result in results:
            print(
                f"{result['status']:>6} | {result['name']:<36} | "
                f"peak={result['measured_frequency_hz']:.3f} Hz | "
                f"RMSE={result['displacement_rmse_px']:.4f} px | "
                f"r={result['displacement_correlation'] if result['displacement_correlation'] is not None else 'n/a'}"
            )
        print(f"\nSaved: {args.json}")
        return

    if args.command == "generate-synthetic":
        config = SyntheticConfig(
            fps=args.fps,
            duration_s=args.duration,
            vibration_frequency_hz=args.frequency,
            vibration_amplitude_px=args.amplitude,
            camera_amplitude_px=args.camera_shake,
            camera_y_amplitude_px=args.camera_y_shake,
            noise_sigma=args.noise,
            second_harmonic_amplitude_px=args.second_harmonic,
            lighting_flicker_depth=args.lighting_depth,
            seed=args.seed,
        )
        frames, _ = make_scene(config)
        write_video(args.output, frames, args.fps)
        print(f"Created {args.output} ({len(frames)} frames @ {args.fps} FPS)")
        return

    if args.command == "compare":
        baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
        current = json.loads(args.current.read_text(encoding="utf-8"))
        noise_summary = (
            json.loads(args.noise_floor_summary.read_text(encoding="utf-8"))
            if args.noise_floor_summary is not None
            else None
        )
        report = compare_inspection_summaries(
            baseline,
            current,
            axis=args.axis,
            warning_rms_change_percent=args.warning_rms_change,
            alert_rms_change_percent=args.alert_rms_change,
            noise_floor_summary=noise_summary,
            noise_floor_multiple=args.noise_floor_multiple,
            baseline_label=str(args.baseline),
            current_label=str(args.current),
        )
        args.out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))
        return

    if args.command == "inspect":
        summary = analyse_video(
            args.video,
            parse_roi(args.target),
            parse_roi(args.anchor),
            args.out,
            fps_override=args.fps,
            min_frequency_hz=args.min_frequency,
            max_frequency_hz=args.max_frequency,
            nperseg=args.nperseg,
        )
        print(json.dumps(summary, indent=2))
        return

    if args.command == "ui":
        import subprocess
        app_path = Path(__file__).parent / "app.py"
        cmd = [
            "streamlit",
            "run",
            str(app_path),
            f"--server.port={args.port}",
            f"--server.address={args.host}",
        ]
        print(f"Starting PhaseSight UI on http://{args.host}:{args.port}...")
        subprocess.run(cmd, check=True)
        return

    if args.command == "build-baseline":
        runs_data = [json.loads(p.read_text(encoding="utf-8")) for p in args.runs]
        baseline = build_baseline(
            runs_data,
            asset_id=args.asset_id,
            min_runs=args.min_runs,
            notes=args.notes,
        )
        serialize_baseline(baseline, args.out)
        print(f"\n================ BASELINE RECORD CREATED ================")
        print(f"Asset ID:        {baseline.asset_id}")
        print(f"Baseline ID:     {baseline.baseline_id}")
        print(f"Runs aggregated: {baseline.run_count}")
        print(f"Sampling rate:   {baseline.sampling_rate_hz:.2f} Hz")
        print(f"Target ROI:      {baseline.target_roi}")
        print(f"Anchor ROI:      {baseline.anchor_roi}")
        print(f"---------------------------------------------------------")
        print(
            f"X-Axis Dominant Freq: {baseline.x_axis.dominant_frequency_hz.median:.3f} Hz "
            f"(MAD: {baseline.x_axis.dominant_frequency_hz.mad:.4f})"
        )
        print(
            f"X-Axis RMS Motion:    {baseline.x_axis.rms_displacement_px.median:.4f} px "
            f"(MAD: {baseline.x_axis.rms_displacement_px.mad:.4f})"
        )
        print(
            f"X-Axis Peak dB:       {baseline.x_axis.peak_to_median_db.median:.1f} dB "
            f"(MAD: {baseline.x_axis.peak_to_median_db.mad:.2f})"
        )
        if (
            baseline.x_axis.second_harmonic_ratio
            and baseline.x_axis.second_harmonic_ratio.median is not None
        ):
            print(f"X-Axis 2x Harmonic:   {baseline.x_axis.second_harmonic_ratio.median:.4f}")
        print(f"---------------------------------------------------------")
        print(f"Saved BaselineRecord to: {args.out}")
        return

    if args.command == "assess":
        curr_data = json.loads(args.current.read_text(encoding="utf-8"))
        base_record = deserialize_baseline(args.baseline)
        evaluation = evaluate_run_against_baseline(
            curr_data,
            base_record,
            z_threshold=args.threshold,
            axis=args.axis,
        )
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(evaluation.to_json(indent=2), encoding="utf-8")

        print(f"\n================ BASELINE ASSESSMENT ================")
        print(f"Status:       {evaluation.status}")
        print(f"Asset ID:     {evaluation.asset_id}")
        print(f"Baseline ID:  {evaluation.baseline_id}")
        print(f"Evaluated At: {evaluation.evaluated_at}")
        print(f"Threshold:    |z| >= {evaluation.z_threshold:.1f}")
        print(f"-----------------------------------------------------")
        if not evaluation.confidence_passed:
            print("Confidence Gate: FAILED")
            for reason in evaluation.reasons:
                print(f"  - {reason}")
        else:
            print("Confidence Gate: PASSED")
            if evaluation.trigger_features:
                print(f"Triggers Flagged ({len(evaluation.trigger_features)}):")
                for trig in evaluation.trigger_features:
                    print(f"  - {trig}")
            else:
                print("No features exceeded robust threshold.")
        print(f"-----------------------------------------------------")
        print(f"Interpretation: {evaluation.interpretation}")
        print(f"Saved evaluation to: {args.out}")
        return


if __name__ == "__main__":
    main()
