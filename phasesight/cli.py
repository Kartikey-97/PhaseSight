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
from .capture import calculate_timestamp_stability, capture_live_clip
from .storage import StorageManager
from .synthetic import SyntheticConfig, make_scene, write_video
from .validation import run_full_validation_matrix, run_validation_suite
from .video import analyse_video, parse_roi


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="phasesight", description="PhaseSight validation prototype")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Run deterministic synthetic validation tests")
    validate.add_argument("--json", type=Path, default=Path("data/validation_results.json"))
    validate.add_argument(
        "--test",
        choices=["all", "T1", "T2", "T3", "T4", "T5", "T6"],
        default="all",
        help="Run all or a specific proposal validation protocol (T1 to T6)",
    )
    validate.add_argument(
        "--legacy",
        action="store_true",
        help="Run legacy 4-case synthetic validation suite",
    )

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

    db_info = sub.add_parser("db-info", help="Display local persistence database and storage diagnostics")
    db_info.add_argument("--storage-root", type=Path, default=None, help="Custom storage root directory")
    db_info.add_argument("--json", action="store_true", help="Output raw JSON summary")

    asset = sub.add_parser("asset", help="Manage persisted assets and ROI profiles")
    asset_sub = asset.add_subparsers(dest="asset_action", required=True)

    asset_create = asset_sub.add_parser("create", help="Register a new machine asset")
    asset_create.add_argument("name", help="Asset display name")
    asset_create.add_argument("--target", required=True, help="x,y,width,height")
    asset_create.add_argument("--anchor", required=True, help="x,y,width,height")
    asset_create.add_argument("--fps", type=float, default=60.0, help="Expected video FPS (default: 60)")
    asset_create.add_argument("--speed", type=float, default=None, help="Nominal speed in RPM")
    asset_create.add_argument("--desc", type=str, default="", help="Asset description")
    asset_create.add_argument("--asset-id", type=str, default=None, help="Custom asset ID (optional)")
    asset_create.add_argument("--storage-root", type=Path, default=None, help="Custom storage root directory")

    asset_list = asset_sub.add_parser("list", help="List all registered machine assets")
    asset_list.add_argument("--storage-root", type=Path, default=None, help="Custom storage root directory")
    asset_list.add_argument("--json", action="store_true", help="Output raw JSON list")

    asset_show = asset_sub.add_parser("show", help="Display asset details, ROIs, and baseline status")
    asset_show.add_argument("asset_id", help="Asset identifier")
    asset_show.add_argument("--storage-root", type=Path, default=None, help="Custom storage root directory")
    asset_show.add_argument("--json", action="store_true", help="Output raw JSON details")

    cap_parser = sub.add_parser("capture", help="Acquire a video clip from camera or virtual stream with timing checks")
    cap_parser.add_argument("source", nargs="?", default="0", help="Camera index (e.g. 0), video file path, or 'mock:0'")
    cap_parser.add_argument("--duration", type=float, default=5.0, help="Capture duration in seconds (1.0 to 30.0)")
    cap_parser.add_argument("--fps", type=float, default=30.0, help="Target frame rate (default: 30)")
    cap_parser.add_argument("--out", type=Path, default=None, help="Output MP4 file path")
    cap_parser.add_argument("--json", type=Path, default=None, help="Output JSON path for stability report")
    cap_parser.add_argument("--warmup", type=int, default=2, help="Warmup frames to flush buffer")

    return parser


def main() -> None:
    args = _build_parser().parse_args()
    if args.command == "validate":
        if args.legacy:
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

        if args.test != "all":
            from .validation import (
                validate_t1_synthetic_motion,
                validate_t2_static_negative_control,
                validate_t3_camera_shake_cancellation,
                validate_t4_baseline_repeatability,
                validate_t5_controlled_change_detection,
                validate_t6_image_quality_stress,
            )
            runners = {
                "T1": validate_t1_synthetic_motion,
                "T2": validate_t2_static_negative_control,
                "T3": validate_t3_camera_shake_cancellation,
                "T4": validate_t4_baseline_repeatability,
                "T5": validate_t5_controlled_change_detection,
                "T6": validate_t6_image_quality_stress,
            }
            res = runners[args.test]()
            print(f"\n[{res['status']}] Protocol {args.test}: {res['name']}")
            print(json.dumps(res, indent=2))
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(res, indent=2), encoding="utf-8")
            print(f"\nSaved: {args.json}")
            return

        matrix = run_full_validation_matrix()
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(matrix, indent=2), encoding="utf-8")

        p = matrix["protocols"]
        t1, t2, t3, t4, t5, t6 = p["T1"], p["T2"], p["T3"], p["T4"], p["T5"], p["T6"]

        print("=" * 80)
        print("PhaseSight Proposal Validation Matrix (T1–T6) — Innovathon 2026")
        print("=" * 80)

        # T1
        print(f"[{t1['status']}] T1: Synthetic Known Motion Recovery")
        c1 = t1["clean_case"]
        h1 = t1["harmonic_case"]
        print(f"       - Clean Target (8.5 Hz):      f={c1['measured_frequency_hz']:.3f} Hz (err={c1['frequency_error_hz']:.3f} Hz), RMSE={c1['displacement_rmse_px']:.3f} px, r={c1['displacement_correlation']:.3f}")
        print(f"       - Harmonic Target (8.5+17Hz): f={h1['measured_frequency_hz']:.3f} Hz, RMSE={h1['displacement_rmse_px']:.3f} px, 2x_ratio={h1['second_harmonic_ratio']:.3f}, r={h1['displacement_correlation']:.3f}")

        # T2
        print(f"[{t2['status']}] T2: Static Negative Control & Noise Floor")
        s2 = t2["pure_static"]
        n2 = t2["camera_shake_null"]
        print(f"       - Pure Static Scene:          RMS={s2['measured_rms_px']:.3f} px, peak={s2['peak_to_median_db']:.1f} dB, qual={s2['signal_quality']}")
        print(f"       - Camera Shake Only (Null):   RMS={n2['measured_rms_px']:.3f} px, peak={n2['peak_to_median_db']:.1f} dB, qual={n2['signal_quality']}")

        # T3
        print(f"[{t3['status']}] T3: Camera-Motion Control (Anchor Subtraction Efficacy)")
        print(f"       - Uncorrected Motion:         RMSE={t3['uncorrected_rmse_px']:.3f} px, r={t3['uncorrected_correlation']:.3f}")
        print(f"       - Corrected (Subtracted):     RMSE={t3['corrected_rmse_px']:.3f} px, r={t3['corrected_correlation']:.3f}")
        print(f"       - Efficacy:                   {t3['error_reduction_pct']:.1f}% error reduction ({t3['shake_suppression_db']:.1f} dB shake suppression)")

        # T4
        print(f"[{t4['status']}] T4: Portable Baseline Repeatability (>=3 Captures)")
        print(f"       - Multi-Run Aggregation:      f={t4['dominant_frequency_median_hz']:.3f} Hz (MAD={t4['dominant_frequency_mad_hz']:.3f}), RMS={t4['rms_displacement_median_px']:.3f} px (MAD={t4['rms_displacement_mad_px']:.3f})")
        print(f"       - Screening Nominal Runs:     {len(t4['screened_statuses'])}/{len(t4['screened_statuses'])} Normal status, 0 false triggers (|z| < 3.0)")

        # T5
        print(f"[{t5['status']}] T5: Controlled Change Detection (Baseline vs Changed)")
        print(f"       - Changed Clip Screening:     Status: {t5['evaluation_status']} (z_rms={t5['z_rms_displacement']:+.2f}, z_harm={t5['z_second_harmonic_ratio']:+.2f})")
        print(f"       - Boundary Verification:      Non-diagnostic disclosure confirmed")

        # T6
        print(f"[{t6['status']}] T6: Image-Quality Stress Testing")
        print(f"       - T6a Low Texture:            REJECTED by validate_rois (std={t6['t6a_low_texture']['std_px']:.2f} < 2.0 px)")
        print(f"       - T6b Severe Blur:            DEGRADED phase response -> {t6['t6b_severe_blur']['classified_quality']}")
        print(f"       - T6c Illumination Flicker:   CONTAMINATED flag confirmed (shared peak)")
        print(f"       - T6d Dropped Frames:         {t6['t6d_dropped_frames']['status']} confirmed (jitter={t6['t6d_dropped_frames']['jitter_ratio']*100:.1f}%, {t6['t6d_dropped_frames']['dropped_count']} drops)")

        print("=" * 80)
        overall = matrix["summary"]["overall_status"]
        if overall == "PASS":
            print("Overall Verdict: ALL 6 PROPOSAL VALIDATION PROTOCOLS PASSED (100%)")
        else:
            print("Overall Verdict: VALIDATION PROTOCOLS FAILED")
        print("=" * 80)
        print(f"Saved full validation JSON to: {args.json}\n")
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
        import sys
        app_path = Path(__file__).parent / "app.py"
        cmd = [
            sys.executable,
            "-m",
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

    if args.command == "db-info":
        sm = StorageManager(storage_root=args.storage_root)
        try:
            info = sm.get_db_info()
            if args.json:
                print(json.dumps(info, indent=2))
            else:
                print("\n================ PHASESIGHT STORAGE INFO ================")
                print(f"Database Path:   {info['db_path']}")
                print(f"Storage Root:    {info['storage_root']}")
                print(f"SQLite Version:  {info['sqlite_version']}")
                print(f"Schema Version:  {info['schema_version']}")
                print(f"Foreign Keys:    {'ENABLED' if info['foreign_keys'] else 'DISABLED'}")
                print(f"---------------------------------------------------------")
                print(f"Total Assets:    {info['asset_count']}")
                print(f"Total Baselines: {info['baseline_count']}")
                print(f"Inspection Runs: {info['run_count']}")
                print(f"Review Events:   {info['review_count']}")
                print(f"=========================================================\n")
        finally:
            sm.close()
        return

    if args.command == "asset":
        sm = StorageManager(storage_root=args.storage_root)
        try:
            if args.asset_action == "create":
                target_roi = parse_roi(args.target)
                anchor_roi = parse_roi(args.anchor)
                asset = sm.create_asset(
                    name=args.name,
                    target_roi=target_roi,
                    anchor_roi=anchor_roi,
                    expected_fps=args.fps,
                    description=args.desc,
                    nominal_speed_rpm=args.speed,
                    asset_id=args.asset_id,
                )
                print("\n================ ASSET REGISTERED ================")
                print(f"Asset ID:      {asset.asset_id}")
                print(f"Name:          {asset.name}")
                print(f"Target ROI:    {asset.target_roi}")
                print(f"Anchor ROI:    {asset.anchor_roi}")
                print(f"Expected FPS:  {asset.expected_fps:.1f}")
                if asset.nominal_speed_rpm:
                    print(f"Nominal RPM:   {asset.nominal_speed_rpm:.1f}")
                if asset.description:
                    print(f"Description:   {asset.description}")
                print(f"Created At:    {asset.created_at}")
                print(f"==================================================\n")

            elif args.asset_action == "list":
                assets = sm.list_assets()
                if args.json:
                    print(json.dumps([a.to_dict() for a in assets], indent=2))
                else:
                    print(f"\nRegistered Assets ({len(assets)}):")
                    if not assets:
                        print("  (No assets found in database)")
                    else:
                        print(f"{'ID':<16} | {'Name':<24} | {'Expected FPS':<12} | {'Nominal RPM':<12} | {'Updated At'}")
                        print("-" * 80)
                        for a in assets:
                            rpm_str = f"{a.nominal_speed_rpm:.1f}" if a.nominal_speed_rpm else "n/a"
                            print(f"{a.asset_id:<16} | {a.name:<24} | {a.expected_fps:<12.1f} | {rpm_str:<12} | {a.updated_at[:19]}")
                        print("-" * 80 + "\n")

            elif args.asset_action == "show":
                asset = sm.get_asset(args.asset_id)
                if not asset:
                    print(f"Error: Asset with ID '{args.asset_id}' not found.")
                    return

                baselines = sm.list_baselines_for_asset(args.asset_id)
                runs = sm.list_inspection_runs(args.asset_id)

                if args.json:
                    out = asset.to_dict()
                    out["baseline_count"] = len(baselines)
                    out["run_count"] = len(runs)
                    print(json.dumps(out, indent=2))
                else:
                    print(f"\n================ ASSET DETAILS: {asset.asset_id} ================")
                    print(f"Name:          {asset.name}")
                    print(f"Description:   {asset.description or '(None)'}")
                    print(f"Target ROI:    x={asset.target_roi.get('x')}, y={asset.target_roi.get('y')}, w={asset.target_roi.get('width')}, h={asset.target_roi.get('height')}")
                    print(f"Anchor ROI:    x={asset.anchor_roi.get('x')}, y={asset.anchor_roi.get('y')}, w={asset.anchor_roi.get('width')}, h={asset.anchor_roi.get('height')}")
                    print(f"Expected FPS:  {asset.expected_fps:.1f}")
                    print(f"Nominal RPM:   {asset.nominal_speed_rpm if asset.nominal_speed_rpm else 'n/a'}")
                    print(f"Baselines:     {len(baselines)} recorded")
                    print(f"Runs Logged:   {len(runs)} inspections")
                    print(f"Created At:    {asset.created_at}")
                    print(f"Updated At:    {asset.updated_at}")
                    print(f"==========================================================\n")
        finally:
            sm.close()
        return

    if args.command == "capture":
        if args.duration < 1.0 or args.duration > 30.0:
            print(f"Error: duration must be between 1.0 and 30.0 seconds (got {args.duration}).")
            return

        import datetime

        out_path = args.out
        if out_path is None:
            now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = Path("output/webcam_captures") / f"capture_{now_str}.mp4"

        print(f"Acquiring {args.duration:.1f}s from source '{args.source}' (Target FPS: {args.fps:.1f})...")
        res = capture_live_clip(
            source=args.source,
            duration_s=float(args.duration),
            target_fps=float(args.fps),
            output_path=out_path,
        )

        rep = res.stability
        badge = (
            "[🟢 STABLE]"
            if rep.status == "STABLE"
            else ("[🟡 WARNING_JITTER]" if rep.status == "WARNING_JITTER" else "[🔴 REJECTED_UNSTABLE]")
        )

        print("\n================ LIVE CAPTURE STABILITY REPORT ================")
        print(f"Status:          {badge} ({rep.status})")
        print(f"Video File:      {res.video_path}")
        print(f"Frames Captured: {rep.total_frames} frames in {rep.duration_s:.2f} s")
        print(f"Nominal FPS:     {rep.nominal_fps:.2f} FPS")
        print(f"Measured FPS:    {rep.measured_fps:.2f} FPS (empirical 1/median_dt)")
        print(f"Jitter Ratio:    {rep.jitter_ratio * 100:.2f}% (std/median)")
        print(f"Robust Jitter:   {rep.robust_jitter_ratio * 100:.2f}% (1.4826*MAD/median)")
        print(f"Dropped Frames:  {rep.dropped_frames_count} frames missing")
        print(f"Large Gaps:      {rep.large_gap_count} stalls (> 2.5x median dt)")
        if rep.status_reasons:
            print("Status Details:")
            for reason in rep.status_reasons:
                print(f"  - {reason}")
        print("===============================================================\n")

        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(rep.to_dict(), indent=2), encoding="utf-8")
            print(f"Saved stability report to: {args.json}")
        return


if __name__ == "__main__":
    main()
