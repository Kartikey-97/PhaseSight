from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from phasesight.analysis import compare_inspection_summaries
from phasesight.baseline import (
    BaselineEvaluation,
    BaselineRecord,
    build_baseline,
    deserialize_baseline,
    evaluate_run_against_baseline,
    serialize_baseline,
)
from phasesight.tracker import ROI, check_roi_texture, draw_rois_on_frame, validate_rois
from phasesight.ui_helpers import (
    DEFAULT_SAMPLE_ANCHOR_ROI,
    DEFAULT_SAMPLE_TARGET_ROI,
    SAMPLE_VIDEOS,
    get_video_metadata,
    read_first_frame,
)
from phasesight.video import analyse_video

st.set_page_config(
    page_title="PhaseSight — Video Vibration Screening",
    page_icon="🔍",
    layout="wide",
)


def main() -> None:
    st.title("PhaseSight — Local Vibration Inspection Prototype")
    st.caption(
        "Measurement-screening prototype: estimates 2D relative translation in pixels using "
        "phase correlation and Welch spectral density. Output is in pixels, not millimetres or mm/s."
    )

    tab_inspect, tab_compare, tab_about = st.tabs(
        ["1. Video Inspection", "2. Baseline Comparison", "3. Technical Boundaries & Notes"]
    )

    with tab_inspect:
        render_inspection_tab()

    with tab_compare:
        render_comparison_tab()

    with tab_about:
        render_about_tab()


def render_inspection_tab() -> None:
    st.subheader("Video Source & ROI Selection")

    col_source1, col_source2 = st.columns(2)
    with col_source1:
        source_mode = st.radio(
            "Select video input source:",
            ["Sample portable clips", "Upload video file"],
            horizontal=True,
        )

    video_path: Path | None = None
    if source_mode == "Sample portable clips":
        with col_source2:
            sample_choice = st.selectbox("Choose sample clip:", list(SAMPLE_VIDEOS.keys()))
            if sample_choice:
                chosen_path = SAMPLE_VIDEOS[sample_choice]
                if chosen_path.exists():
                    video_path = chosen_path
                else:
                    st.error(f"Sample file not found at: {chosen_path}")
    else:
        with col_source2:
            uploaded_file = st.file_uploader(
                "Upload video (MP4, AVI, MOV):",
                type=["mp4", "avi", "mov", "mkv"],
            )
            if uploaded_file is not None:
                upload_dir = Path("output/uploads")
                upload_dir.mkdir(parents=True, exist_ok=True)
                saved_path = upload_dir / uploaded_file.name
                saved_path.write_bytes(uploaded_file.getbuffer())
                video_path = saved_path

    if video_path is None:
        st.info("Select or upload a video file to proceed.")
        return

    # Video metadata and first frame
    try:
        meta = get_video_metadata(video_path)
        first_frame = read_first_frame(video_path)
    except Exception as exc:
        st.error(f"Failed to load video: {exc}")
        return

    frame_h, frame_w = first_frame.shape[:2]
    st.write(
        f"**File:** `{video_path.name}` | **Dimensions:** {frame_w}x{frame_h} px | "
        f"**FPS:** {meta['fps']:.2f} | **Frames:** {meta['frame_count']} "
        f"({meta['duration_s']:.2f} s)"
    )

    # Defaults for ROIs
    is_sample = str(video_path).startswith("data/portable")
    default_tx = DEFAULT_SAMPLE_TARGET_ROI.x if is_sample else min(frame_w // 2, max(0, frame_w - 160))
    default_ty = DEFAULT_SAMPLE_TARGET_ROI.y if is_sample else min(frame_h // 4, max(0, frame_h - 160))
    default_tw = DEFAULT_SAMPLE_TARGET_ROI.width if is_sample else min(160, frame_w // 3)
    default_th = DEFAULT_SAMPLE_TARGET_ROI.height if is_sample else min(160, frame_h // 3)

    default_ax = DEFAULT_SAMPLE_ANCHOR_ROI.x if is_sample else 10
    default_ay = DEFAULT_SAMPLE_ANCHOR_ROI.y if is_sample else 10
    default_aw = DEFAULT_SAMPLE_ANCHOR_ROI.width if is_sample else min(160, frame_w // 3)
    default_ah = DEFAULT_SAMPLE_ANCHOR_ROI.height if is_sample else min(160, frame_h // 3)

    st.markdown("#### Configure Regions of Interest (ROIs)")
    st.caption(
        "**Target ROI:** rigid, textured machine region. **Anchor ROI:** rigid, static background "
        "(wall, pillar) to subtract camera shake."
    )

    col_roi_t, col_roi_a = st.columns(2)
    with col_roi_t:
        st.markdown("**Target ROI (Machine)** — Green Box")
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            tx = st.number_input("Target X", min_value=0, max_value=max(0, frame_w - 32), value=int(default_tx), step=5)
            ty = st.number_input("Target Y", min_value=0, max_value=max(0, frame_h - 32), value=int(default_ty), step=5)
        with col_t2:
            tw = st.number_input("Target Width", min_value=32, max_value=frame_w, value=int(default_tw), step=5)
            th = st.number_input("Target Height", min_value=32, max_value=frame_h, value=int(default_th), step=5)

    with col_roi_a:
        st.markdown("**Static Anchor ROI (Background)** — Orange Box")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            ax = st.number_input("Anchor X", min_value=0, max_value=max(0, frame_w - 32), value=int(default_ax), step=5)
            ay = st.number_input("Anchor Y", min_value=0, max_value=max(0, frame_h - 32), value=int(default_ay), step=5)
        with col_a2:
            aw = st.number_input("Anchor Width", min_value=32, max_value=frame_w, value=int(default_aw), step=5)
            ah = st.number_input("Anchor Height", min_value=32, max_value=frame_h, value=int(default_ah), step=5)

    target_roi = ROI(int(tx), int(ty), int(tw), int(th))
    anchor_roi = ROI(int(ax), int(ay), int(aw), int(ah))

    # Real-time ROI validation
    roi_errors = validate_rois(first_frame, target_roi, anchor_roi, min_size=32, min_texture_std=2.0)

    # Frame preview with overlaid bounding boxes
    annotated_frame = draw_rois_on_frame(first_frame, target_roi, anchor_roi)
    # Convert BGR to RGB for Streamlit image display
    rgb_preview = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
    st.image(rgb_preview, caption="First Frame with Target (Green) & Anchor (Orange) ROIs", use_container_width=True)

    if roi_errors:
        for err in roi_errors:
            st.error(f"⚠️ {err}")
        st.warning("Fix the ROI settings above before running analysis.")
    else:
        # Display texture check details
        _, t_std = check_roi_texture(first_frame, target_roi)
        _, a_std = check_roi_texture(first_frame, anchor_roi)
        st.success(
            f"✅ ROIs are valid: in bounds, non-overlapping, ≥32x32. "
            f"(Target texture std={t_std:.2f}, Anchor texture std={a_std:.2f})"
        )

    # Analysis parameters
    st.markdown("#### Analysis Parameters")
    col_p1, col_p2, col_p3, col_p4 = st.columns(4)
    with col_p1:
        fps_override_val = st.number_input(
            "FPS Override (0 = use metadata)",
            min_value=0.0,
            max_value=1000.0,
            value=0.0,
            step=1.0,
            help="Pass explicit frame rate if metadata FPS is incorrect or variable.",
        )
    with col_p2:
        min_freq = st.number_input(
            "Min Frequency (Hz)",
            min_value=0.1,
            max_value=50.0,
            value=1.0,
            step=0.5,
        )
    with col_p3:
        max_freq_default = min(20.0, meta["fps"] * 0.45 if meta["fps"] > 0 else 20.0)
        max_freq = st.number_input(
            "Max Frequency (Hz)",
            min_value=1.0,
            max_value=500.0,
            value=float(max_freq_default),
            step=1.0,
        )
    with col_p4:
        nperseg = st.selectbox(
            "Welch Segment Length (nperseg)",
            [64, 128, 256, 512],
            index=2,
            help="Length of each FFT segment in Welch PSD. Higher gives finer frequency resolution.",
        )

    fps_override = float(fps_override_val) if fps_override_val > 0 else None

    # Run Analysis Button
    run_disabled = bool(roi_errors)
    if st.button("Run Vibration Analysis", type="primary", disabled=run_disabled):
        output_dir = Path("output") / video_path.stem
        with st.spinner("Processing video frames and computing Welch PSD..."):
            try:
                summary = analyse_video(
                    video_path,
                    target_roi,
                    anchor_roi,
                    output_dir,
                    fps_override=fps_override,
                    min_frequency_hz=float(min_freq),
                    max_frequency_hz=float(max_freq),
                    nperseg=int(nperseg),
                )
                st.session_state["latest_summary"] = summary
                st.session_state["latest_video_name"] = video_path.name
                st.success("Analysis complete!")
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

    # Display results if available
    if "latest_summary" in st.session_state:
        display_inspection_results(st.session_state["latest_summary"])


def display_inspection_results(summary: dict) -> None:
    st.markdown("---")
    st.subheader(f"Measurement Results: {Path(summary['video']).name}")

    st.warning(
        "⚠️ **Disclaimer:** " + summary.get("interpretation", "Screening measurement in pixels; not a calibrated vibration diagnosis.")
    )

    x_data = summary["x_axis"]
    y_data = summary["y_axis"]

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("### X-Axis Relative Motion")
        q = x_data["signal_quality"]
        if q == "VALID":
            st.success(f"**Quality Status:** VALID")
        elif q == "CONTAMINATED":
            st.error(f"**Quality Status:** CONTAMINATED (shared peak with anchor)")
        else:
            st.warning(f"**Quality Status:** LOW_SIGNAL (no prominent peak)")

        st.metric("Dominant Frequency", f"{x_data['dominant_frequency_hz']:.3f} Hz")
        st.metric("Displacement RMS", f"{x_data['rms_displacement_px']:.4f} px")
        st.metric("Spectral Prominence", f"{x_data['peak_to_median_db']:.2f} dB")
        if x_data.get("second_harmonic_ratio") is not None:
            st.metric("2x Harmonic Ratio", f"{x_data['second_harmonic_ratio']:.4f}")
        st.caption(
            f"Anchor peak: {x_data['anchor_dominant_frequency_hz']:.2f} Hz ({x_data['anchor_peak_to_median_db']:.1f} dB) | "
            f"Target peak: {x_data['target_dominant_frequency_hz']:.2f} Hz"
        )

    with col_m2:
        st.markdown("### Y-Axis Relative Motion")
        qy = y_data["signal_quality"]
        if qy == "VALID":
            st.success(f"**Quality Status:** VALID")
        elif qy == "CONTAMINATED":
            st.error(f"**Quality Status:** CONTAMINATED (shared peak with anchor)")
        else:
            st.warning(f"**Quality Status:** LOW_SIGNAL (no prominent peak)")

        st.metric("Dominant Frequency", f"{y_data['dominant_frequency_hz']:.3f} Hz")
        st.metric("Displacement RMS", f"{y_data['rms_displacement_px']:.4f} px")
        st.metric("Spectral Prominence", f"{y_data['peak_to_median_db']:.2f} dB")
        if y_data.get("second_harmonic_ratio") is not None:
            st.metric("2x Harmonic Ratio", f"{y_data['second_harmonic_ratio']:.4f}")
        st.caption(
            f"Anchor peak: {y_data['anchor_dominant_frequency_hz']:.2f} Hz ({y_data['anchor_peak_to_median_db']:.1f} dB) | "
            f"Target peak: {y_data['target_dominant_frequency_hz']:.2f} Hz"
        )

    # Plot display
    plot_path = Path(summary["outputs"]["plot"])
    if plot_path.exists():
        st.image(str(plot_path), caption="Displacement Traces (Top) and Welch Power Spectral Density (Bottom)", use_container_width=True)

    # Downloads
    st.markdown("#### Export Results")
    col_d1, col_d2, col_d3 = st.columns(3)
    csv_path = Path(summary["outputs"]["csv"])
    summary_path = Path(summary["outputs"]["summary"])

    with col_d1:
        if csv_path.exists():
            st.download_button(
                "📥 Download Displacement CSV",
                data=csv_path.read_bytes(),
                file_name=csv_path.name,
                mime="text/csv",
                use_container_width=True,
            )
    with col_d2:
        if plot_path.exists():
            st.download_button(
                "📥 Download Spectra Plot (PNG)",
                data=plot_path.read_bytes(),
                file_name=plot_path.name,
                mime="image/png",
                use_container_width=True,
            )
    with col_d3:
        if summary_path.exists():
            st.download_button(
                "📥 Download Summary (JSON)",
                data=summary_path.read_bytes(),
                file_name=summary_path.name,
                mime="application/json",
                use_container_width=True,
            )


def render_comparison_tab() -> None:
    st.subheader("Baseline Screening & Deviation Comparison")
    st.caption(
        "Screen an inspection run against an established baseline. "
        "A Review status indicates a measured statistical shift, not a diagnosed machine fault."
    )

    comp_mode = st.radio(
        "Comparison Methodology:",
        [
            "Statistical Baseline Engine (Median + MAD z-score, N ≥ 3)",
            "Pairwise Single-Run Compare (Percentage Thresholds)",
        ],
        horizontal=True,
    )

    if comp_mode == "Statistical Baseline Engine (Median + MAD z-score, N ≥ 3)":
        render_statistical_baseline_section()
    else:
        render_pairwise_comparison_section()


def render_statistical_baseline_section() -> None:
    col1, col2 = st.columns(2)
    baseline_record: BaselineRecord | None = None
    current_data: dict | None = None

    with col1:
        st.markdown("#### Reference Baseline Record")
        base_src = st.radio(
            "Baseline Source:",
            [
                "Use sample baseline (portable_motor)",
                "Upload BaselineRecord JSON",
                "Aggregate ≥ 3 summary JSON files on-the-fly",
            ],
            key="stat_base_src",
        )

        if base_src == "Use sample baseline (portable_motor)":
            sample_file = Path("data/portable/out_baseline/baseline_summary.json")
            if sample_file.exists():
                sample_run = json.loads(sample_file.read_text(encoding="utf-8"))
                baseline_record = build_baseline([sample_run, sample_run, sample_run], asset_id="portable_motor")
                st.info(f"Loaded reference baseline (Asset: `portable_motor`, 3 runs, 60 FPS).")
            else:
                st.warning("Sample baseline summary not found.")
        elif base_src == "Upload BaselineRecord JSON":
            base_json_file = st.file_uploader("Upload baseline JSON:", type=["json"], key="stat_upload_base_rec")
            if base_json_file is not None:
                try:
                    baseline_record = deserialize_baseline(base_json_file.getvalue().decode("utf-8"))
                    st.success(f"Loaded baseline `{baseline_record.baseline_id}` ({baseline_record.run_count} runs).")
                except Exception as exc:
                    st.error(f"Invalid BaselineRecord JSON: {exc}")
        elif base_src == "Aggregate ≥ 3 summary JSON files on-the-fly":
            multi_files = st.file_uploader(
                "Upload ≥ 3 healthy inspection summary JSON files:",
                type=["json"],
                accept_multiple_files=True,
                key="stat_multi_runs",
            )
            if multi_files and len(multi_files) >= 3:
                try:
                    runs_data = [json.loads(f.getvalue().decode("utf-8")) for f in multi_files]
                    baseline_record = build_baseline(runs_data, asset_id="uploaded_asset")
                    st.success(f"Aggregated {len(runs_data)} runs into BaselineRecord `{baseline_record.baseline_id}`.")
                except Exception as exc:
                    st.error(f"Failed to build baseline: {exc}")
            elif multi_files:
                st.warning(f"Uploaded {len(multi_files)} runs. At least 3 are required for robust statistical aggregation.")

    with col2:
        st.markdown("#### Current Inspection Run")
        curr_src = st.radio(
            "Current Run Source:",
            [
                "Use latest analysis result",
                "Upload inspection JSON",
                "Use sample changed.mp4 result",
                "Use sample camera_only.mp4 result",
            ],
            key="stat_curr_src",
        )

        if curr_src == "Use latest analysis result":
            if "latest_summary" in st.session_state:
                current_data = st.session_state["latest_summary"]
                st.info(f"Using latest analysis: {st.session_state.get('latest_video_name', 'current')}")
            else:
                st.warning("No video has been analysed yet in tab 1. Run an analysis or upload a summary.")
        elif curr_src == "Upload inspection JSON":
            curr_file = st.file_uploader("Upload current JSON:", type=["json"], key="stat_upload_curr_json")
            if curr_file is not None:
                try:
                    current_data = json.loads(curr_file.getvalue().decode("utf-8"))
                    st.success(f"Loaded current run: {curr_file.name}")
                except Exception as exc:
                    st.error(f"Invalid JSON: {exc}")
        elif curr_src == "Use sample changed.mp4 result":
            sample_changed = Path("data/portable/out_changed/changed_summary.json")
            if sample_changed.exists():
                current_data = json.loads(sample_changed.read_text(encoding="utf-8"))
                st.info(f"Loaded sample changed result (`data/portable/changed.mp4`).")
        elif curr_src == "Use sample camera_only.mp4 result":
            sample_null = Path("data/portable/out_camera_only/camera_only_summary.json")
            if sample_null.exists():
                current_data = json.loads(sample_null.read_text(encoding="utf-8"))
                st.info(f"Loaded sample camera-only null result (`data/portable/camera_only.mp4`).")

    st.markdown("#### Screening Thresholds")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        eval_axis = st.selectbox("Axis to Evaluate:", ["x", "y", "both"], index=0, help="Evaluate machine vibration axis.")
    with col_p2:
        z_thresh = st.number_input(
            "Robust z-score threshold (|z|)",
            min_value=1.0,
            max_value=10.0,
            value=3.0,
            step=0.5,
            help="Statistical deviation threshold. 3.0 aligns with approximately 3 standard deviations in Gaussian theory.",
        )

    if st.button("Evaluate Against Statistical Baseline", type="primary"):
        if baseline_record is None or current_data is None:
            st.error("Both a valid BaselineRecord and a current inspection run are required.")
            return

        try:
            evaluation = evaluate_run_against_baseline(
                current_data,
                baseline_record,
                z_threshold=float(z_thresh),
                axis=eval_axis,
            )
        except Exception as exc:
            st.error(f"Evaluation failed: {exc}")
            return

        st.markdown("---")
        st.subheader("Statistical Screening Verdict")

        # Verdict Banner
        status = evaluation.status
        if status == "Normal":
            st.success(f"### Status: NORMAL")
            st.caption("All monitored vibration features are within normal baseline statistical bounds (|z| < 3.0).")
        elif status == "Review":
            st.error(f"### Status: REVIEW")
            st.caption("One or more vibration features exceed the robust baseline deviation threshold.")
        elif status == "Low confidence":
            st.warning(f"### Status: LOW CONFIDENCE")
            st.caption("Signal quality gate failed. Cannot reliably compare against baseline.")

        if not evaluation.confidence_passed:
            st.markdown("##### Confidence Gate Failure Reasons:")
            for reason in evaluation.reasons:
                st.write(f"- ⚠️ {reason}")

        if evaluation.trigger_features:
            st.markdown("##### Trigger Features (|z| ≥ threshold):")
            for trig in evaluation.trigger_features:
                st.write(f"- 🚨 **{trig}**")

        # Feature Deviations Table
        if evaluation.deviations:
            st.markdown("##### Detailed Feature Deviation Table")
            rows = []
            z_chart_data = {}
            for name, dev in evaluation.deviations.items():
                z_val = f"{dev.z_robust:+.2f}" if dev.z_robust is not None else "N/A"
                c_val = f"{dev.current_value:.4f}" if dev.current_value is not None else "None"
                b_med = f"{dev.baseline_median:.4f}" if dev.baseline_median is not None else "None"
                b_mad = f"{dev.baseline_mad:.4f}" if dev.baseline_mad is not None else "None"
                rows.append({
                    "Feature": dev.feature_name,
                    "Axis": dev.axis.upper(),
                    "Current": c_val,
                    "Baseline Median": b_med,
                    "Baseline MAD": b_mad,
                    "z_robust": z_val,
                    "Flag": "🚨 TRIGGER" if dev.is_trigger else "✅ Normal",
                })
                if dev.z_robust is not None:
                    z_chart_data[f"{dev.axis.upper()} {dev.feature_name}"] = dev.z_robust

            st.dataframe(rows, use_container_width=True)

            if z_chart_data:
                st.markdown("##### Standardized Robust Deviations (z-score)")
                st.bar_chart(z_chart_data)
                st.caption(f"Horizontal reference threshold is ±{z_thresh:.1f} z.")

        st.warning(f"⚠️ **Disclaimer:** {evaluation.interpretation}")

        report_json = evaluation.to_json(indent=2)
        st.download_button(
            "📥 Download Baseline Assessment Report (JSON)",
            data=report_json.encode("utf-8"),
            file_name=f"assessment_{evaluation.asset_id}.json",
            mime="application/json",
        )


def render_pairwise_comparison_section() -> None:

    with col1:
        st.markdown("#### Baseline Summary")
        base_source = st.radio(
            "Baseline source:",
            ["Upload JSON summary", "Use sample baseline.mp4 result"],
            key="base_source",
        )
        if base_source == "Upload JSON summary":
            base_file = st.file_uploader("Upload baseline JSON:", type=["json"], key="upload_baseline")
            if base_file is not None:
                try:
                    baseline_data = json.loads(base_file.getvalue().decode("utf-8"))
                    st.success(f"Loaded baseline: {base_file.name}")
                except Exception as exc:
                    st.error(f"Invalid JSON: {exc}")
        else:
            sample_base_summary = Path("out_portable_baseline/baseline_summary.json")
            if sample_base_summary.exists():
                baseline_data = json.loads(sample_base_summary.read_text(encoding="utf-8"))
                st.info(f"Loaded reference sample baseline from `{sample_base_summary}`")
            else:
                st.warning("Sample baseline output file not found in out_portable_baseline/")

    with col2:
        st.markdown("#### Current Summary")
        curr_source = st.radio(
            "Current source:",
            ["Use latest analysis result", "Upload JSON summary", "Use sample changed.mp4 result", "Use sample camera_only.mp4 result"],
            key="curr_source",
        )
        if curr_source == "Use latest analysis result":
            if "latest_summary" in st.session_state:
                current_data = st.session_state["latest_summary"]
                st.info(f"Using latest analysis: {st.session_state.get('latest_video_name', 'current')}")
            else:
                st.warning("No video has been analysed yet in tab 1. Run an analysis or upload a summary.")
        elif curr_source == "Upload JSON summary":
            curr_file = st.file_uploader("Upload current JSON:", type=["json"], key="upload_current")
            if curr_file is not None:
                try:
                    current_data = json.loads(curr_file.getvalue().decode("utf-8"))
                    st.success(f"Loaded current: {curr_file.name}")
                except Exception as exc:
                    st.error(f"Invalid JSON: {exc}")
        elif curr_source == "Use sample changed.mp4 result":
            sample_changed = Path("out_portable_changed/changed_summary.json")
            if sample_changed.exists():
                current_data = json.loads(sample_changed.read_text(encoding="utf-8"))
                st.info(f"Loaded reference sample changed from `{sample_changed}`")
        elif curr_source == "Use sample camera_only.mp4 result":
            sample_null = Path("out_portable_camera_only/camera_only_summary.json")
            if sample_null.exists():
                current_data = json.loads(sample_null.read_text(encoding="utf-8"))
                st.info(f"Loaded reference sample camera_only from `{sample_null}`")

    st.markdown("#### Comparison Parameters")
    col_cp1, col_cp2, col_cp3 = st.columns(3)
    with col_cp1:
        cmp_axis = st.selectbox("Axis to compare:", ["x", "y"], index=0)
    with col_cp2:
        warn_pct = st.number_input("Warning RMS Change (%)", min_value=1.0, max_value=200.0, value=25.0, step=5.0)
    with col_cp3:
        alert_pct = st.number_input("Alert RMS Change (%)", min_value=1.0, max_value=500.0, value=50.0, step=5.0)

    # Optional noise-floor upload
    st.markdown("##### Optional Noise-Floor Reference (Machine-Off)")
    noise_file = st.file_uploader("Upload machine-off summary for noise floor gating (optional):", type=["json"], key="upload_noise")
    noise_data = None
    if noise_file is not None:
        try:
            noise_data = json.loads(noise_file.getvalue().decode("utf-8"))
        except Exception:
            st.error("Invalid noise floor JSON")

    if st.button("Compare Summaries", type="primary"):
        if baseline_data is None or current_data is None:
            st.error("Both baseline and current summary must be provided.")
            return

        try:
            report = compare_inspection_summaries(
                baseline_data,
                current_data,
                axis=cmp_axis,
                warning_rms_change_percent=float(warn_pct),
                alert_rms_change_percent=float(alert_pct),
                noise_floor_summary=noise_data,
                baseline_label="Baseline",
                current_label="Current",
            )
        except Exception as exc:
            st.error(f"Comparison failed: {exc}")
            return

        status = report["status"]
        st.markdown("### Comparison Result")

        if status == "NO_MAJOR_CHANGE":
            st.success(f"### Status: {status}")
            st.caption("No significant RMS change or frequency shift detected relative to baseline.")
        elif status == "WARNING_CHANGE":
            st.warning(f"### Status: {status}")
            st.caption("Measured change exceeds the warning threshold against baseline.")
        elif status == "ALERT_CHANGE":
            st.error(f"### Status: {status}")
            st.caption("Measured change exceeds the alert threshold against baseline.")
        elif status == "INSUFFICIENT_SIGNAL":
            st.info(f"### Status: {status}")
            st.caption("One or both captures had insufficient signal quality (low signal, anchor contamination, or below noise floor).")
        else:
            st.error(f"### Status: {status}")

        col_r1, col_r2, col_r3, col_r4 = st.columns(4)
        with col_r1:
            st.metric("Baseline RMS", f"{report['baseline_rms_px']:.4f} px")
        with col_r2:
            st.metric("Current RMS", f"{report['current_rms_px']:.4f} px")
        with col_r3:
            change_str = f"{report['rms_change_percent']:+.2f}%" if report['rms_change_percent'] is not None else "N/A"
            st.metric("RMS Change", change_str)
        with col_r4:
            freq_str = f"{report['frequency_change_hz']:.3f} Hz" if report['frequency_change_hz'] is not None else "N/A"
            st.metric("Dominant Freq Shift", freq_str)

        st.caption(
            f"Baseline Freq: {report['baseline_frequency_hz']:.3f} Hz | "
            f"Current Freq: {report['current_frequency_hz']:.3f} Hz | "
            f"Axis: {report['axis'].upper()}"
        )
        st.warning(f"⚠️ {report['interpretation']}")

        report_json = json.dumps(report, indent=2)
        st.download_button(
            "📥 Download Comparison Report (JSON)",
            data=report_json.encode("utf-8"),
            file_name="comparison_report.json",
            mime="application/json",
        )


def render_about_tab() -> None:
    st.subheader("Technical Boundaries & Safe Usage Guidelines")
    st.markdown(
        """
### Non-negotiable Technical Boundaries
1. **Pixel-Domain Measurements Only:**
   - Current output is strictly in image pixels.
   - It is **not** calibrated in millimetres, micrometres, mm/s velocity, or acceleration.
   - Converting to metric units requires precise physical scale calibration and optical geometry.

2. **2D Translation Only:**
   - Tracking uses OpenCV `phaseCorrelate` (Fourier shift theorem) between target and anchor ROIs.
   - Does **not** correct for camera rotation, perspective tilt, optical zoom, parallax, rolling shutter, or motion blur.

3. **Static Anchor Assumptions:**
   - The anchor ROI cancels common camera translation *only* if the anchor is genuinely stationary and has visible surface texture.
   - Do not place the anchor on vibrating machine structures.

4. **Screening vs. Fault Diagnosis:**
   - `WARNING_CHANGE` and `ALERT_CHANGE` labels represent measured signal changes relative to baseline.
   - They do **not** diagnose bearing defects, gear faults, unbalance, looseness, or remaining useful life (RUL).

5. **Provisional Signal Quality Gates:**
   - A 10 dB spectral prominence gate and same-frequency anchor contamination check are provisional bench heuristics.
   - They must be evaluated against physical camera null clips.
        """
    )


if __name__ == "__main__":
    main()
