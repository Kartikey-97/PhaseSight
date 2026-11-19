from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

import cv2
import numpy as np
import streamlit as st

# Configure headless Matplotlib prior to any pyplot usage
os.environ.setdefault("MPLCONFIGDIR", tempfile.gettempdir())
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from phasesight.analysis import compare_inspection_summaries
from phasesight.baseline import (
    BaselineEvaluation,
    BaselineRecord,
    _rois_match,
    build_baseline,
    deserialize_baseline,
    evaluate_run_against_baseline,
    serialize_baseline,
)
from phasesight.capture import (
    CaptureResult,
    CaptureStabilityReport,
    capture_live_clip,
    grab_preview_frame,
    open_capture_source,
)
from phasesight.storage import (
    AssetRecord,
    InspectionRunRecord,
    ReviewEventRecord,
    RunArrays,
    StorageManager,
)
from phasesight.tracker import ROI, check_roi_texture, draw_rois_on_frame, validate_rois
from phasesight.ui_helpers import (
    DEFAULT_SAMPLE_ANCHOR_ROI,
    DEFAULT_SAMPLE_TARGET_ROI,
    SAMPLE_VIDEOS,
    get_video_metadata,
    plot_run_arrays,
    read_first_frame,
    run_arrays_from_csv,
    stability_badge,
    status_badge,
    sync_active_asset_rois,
)
from phasesight.video import analyse_video

st.set_page_config(
    page_title="PhaseSight — Video Vibration Screening",
    page_icon="🔍",
    layout="wide",
)


def get_storage_manager() -> StorageManager:
    """Retrieve or initialize StorageManager cached in session state."""
    if "storage_manager" not in st.session_state:
        st.session_state["storage_manager"] = StorageManager()
    return st.session_state["storage_manager"]


def init_session_state(sm: StorageManager) -> None:
    """Initialize default session state keys."""
    st.session_state.setdefault("selected_asset_id", None)
    st.session_state.setdefault("prev_selected_asset_id", None)
    st.session_state.setdefault("tx_input", int(DEFAULT_SAMPLE_TARGET_ROI.x))
    st.session_state.setdefault("ty_input", int(DEFAULT_SAMPLE_TARGET_ROI.y))
    st.session_state.setdefault("tw_input", int(DEFAULT_SAMPLE_TARGET_ROI.width))
    st.session_state.setdefault("th_input", int(DEFAULT_SAMPLE_TARGET_ROI.height))
    st.session_state.setdefault("ax_input", int(DEFAULT_SAMPLE_ANCHOR_ROI.x))
    st.session_state.setdefault("ay_input", int(DEFAULT_SAMPLE_ANCHOR_ROI.y))
    st.session_state.setdefault("aw_input", int(DEFAULT_SAMPLE_ANCHOR_ROI.width))
    st.session_state.setdefault("ah_input", int(DEFAULT_SAMPLE_ANCHOR_ROI.height))
    st.session_state.setdefault("fps_override_val", 60.0)
    st.session_state.setdefault("latest_summary", None)
    st.session_state.setdefault("latest_csv_path", None)


def main() -> None:
    sm = get_storage_manager()
    init_session_state(sm)

    active_asset = render_sidebar(sm)

    st.title("PhaseSight — Local Vibration Inspection Prototype")
    st.caption(
        "Measurement-screening prototype: estimates 2D relative translation in pixels using "
        "phase correlation and Welch spectral density. Output is in pixels, not millimetres or mm/s."
    )

    tab_inspect, tab_assets, tab_wizard, tab_history, tab_compare, tab_about = st.tabs(
        [
            "1. Video Inspection",
            "2. Asset Management",
            "3. Baseline Wizard",
            "4. Inspection History",
            "5. Baseline Comparison",
            "6. Technical Boundaries & Notes",
        ]
    )

    with tab_inspect:
        render_inspection_tab(sm, active_asset)

    with tab_assets:
        render_asset_management_tab(sm)

    with tab_wizard:
        render_baseline_wizard_tab(sm, active_asset)

    with tab_history:
        render_history_tab(sm, active_asset)

    with tab_compare:
        render_comparison_tab()

    with tab_about:
        render_about_tab()


# ---------------------------------------------------------------------------
# Global Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(sm: StorageManager) -> AssetRecord | None:
    st.sidebar.header("Machine Asset Anchor")

    assets = sm.list_assets()
    options = ["-- None (Ad-hoc Analysis) --"] + [f"{a.name} ({a.asset_id})" for a in assets]
    id_map = {f"{a.name} ({a.asset_id})": a.asset_id for a in assets}

    current_asset_id = st.session_state.get("selected_asset_id")
    current_index = 0
    if current_asset_id:
        for idx, a in enumerate(assets):
            if a.asset_id == current_asset_id:
                current_index = idx + 1
                break

    selected_option = st.sidebar.selectbox(
        "Active Machine Asset:",
        options,
        index=current_index,
        key="sidebar_asset_select",
    )

    new_asset_id = id_map.get(selected_option) if selected_option != options[0] else None

    # Sync ROIs on asset change
    if new_asset_id != st.session_state.get("prev_selected_asset_id"):
        st.session_state["selected_asset_id"] = new_asset_id
        st.session_state["prev_selected_asset_id"] = new_asset_id
        active = sm.get_asset(new_asset_id) if new_asset_id else None
        sync_active_asset_rois(active)

    active_asset = sm.get_asset(st.session_state["selected_asset_id"]) if st.session_state.get("selected_asset_id") else None

    if active_asset:
        st.sidebar.markdown(f"**Asset:** `{active_asset.name}`")
        if active_asset.nominal_speed_rpm:
            st.sidebar.caption(f"Nominal Speed: {active_asset.nominal_speed_rpm:.1f} RPM")
        st.sidebar.caption(f"Expected FPS: {active_asset.expected_fps:.1f}")

        t = active_asset.target_roi
        a = active_asset.anchor_roi
        st.sidebar.markdown(f"**Target ROI:** `{t.get('width')}x{t.get('height')} @ ({t.get('x')},{t.get('y')})`")
        st.sidebar.markdown(f"**Anchor ROI:** `{a.get('width')}x{a.get('height')} @ ({a.get('x')},{a.get('y')})`")

        latest_baseline = sm.get_latest_baseline_for_asset(active_asset.asset_id)
        if latest_baseline:
            st.sidebar.success(f"Baseline: `{latest_baseline.baseline_id}` (N={latest_baseline.run_count})")
        else:
            st.sidebar.warning("Baseline: None recorded")
    else:
        st.sidebar.info("Operating in ad-hoc analysis mode without linked asset presets.")

    # Storage Diagnostics
    st.sidebar.markdown("---")
    st.sidebar.subheader("Local Storage Diagnostics")
    try:
        info = sm.get_db_info()
        st.sidebar.caption(f"**Database:** `{Path(info['db_path']).name}`")
        st.sidebar.caption(f"**SQLite Version:** {info['sqlite_version']}")
        st.sidebar.caption(
            f"**Assets:** {info['asset_count']} | **Baselines:** {info['baseline_count']} | "
            f"**Runs:** {info['run_count']}"
        )
    except Exception:
        pass

    return active_asset


# ---------------------------------------------------------------------------
# Tab 1: Video Inspection
# ---------------------------------------------------------------------------

def render_inspection_tab(sm: StorageManager, active_asset: AssetRecord | None) -> None:
    st.subheader("Video Source & ROI Selection")

    if active_asset:
        st.info(
            f"📌 Active Asset: **{active_asset.name}** (`{active_asset.asset_id}`). "
            f"ROIs and Expected FPS ({active_asset.expected_fps:.1f}) loaded from asset record."
        )

    col_source1, col_source2 = st.columns([1, 2])
    with col_source1:
        source_mode = st.radio(
            "Select video input source:",
            ["Sample portable clips", "Upload video file", "Live Webcam Stream"],
            horizontal=False,
        )

    video_path: Path | None = None
    live_stability: CaptureStabilityReport | None = None

    if source_mode == "Sample portable clips":
        with col_source2:
            sample_choice = st.selectbox("Choose sample clip:", list(SAMPLE_VIDEOS.keys()))
            if sample_choice:
                chosen_path = SAMPLE_VIDEOS[sample_choice]
                if chosen_path.exists():
                    video_path = chosen_path
                else:
                    st.error(f"Sample file not found at: {chosen_path}")
    elif source_mode == "Upload video file":
        with col_source2:
            uploaded_file = st.file_uploader(
                "Upload video (MP4, AVI, MOV):",
                type=["mp4", "avi", "mov", "mkv"],
            )
            if uploaded_file is not None:
                upload_dir = Path("output/uploads")
                upload_dir.mkdir(parents=True, exist_ok=True)
                clean_name = Path(uploaded_file.name).name
                saved_path = upload_dir / clean_name
                saved_path.write_bytes(uploaded_file.getbuffer())
                video_path = saved_path
    else:  # Live Webcam Stream
        with col_source2:
            st.markdown("#### Live Camera & Acquisition Controls")
            col_wc1, col_wc2, col_wc3 = st.columns(3)
            with col_wc1:
                cam_source = st.text_input(
                    "Camera Index / Source:",
                    value="0",
                    help="Camera integer index (e.g. 0, 1), device string, or 'mock:0' for virtual test stream.",
                    key="webcam_source_val",
                )
            with col_wc2:
                cam_duration = st.slider(
                    "Duration (seconds):",
                    min_value=2.0,
                    max_value=20.0,
                    value=5.0,
                    step=0.5,
                    key="webcam_duration_val",
                )
            with col_wc3:
                cam_fps = st.selectbox(
                    "Target FPS:",
                    [30.0, 60.0, 15.0],
                    index=0,
                    key="webcam_fps_val",
                )

            col_btn_prev, col_btn_rec = st.columns(2)
            with col_btn_prev:
                if st.button("📸 Grab Preview Frame", key="btn_grab_preview"):
                    try:
                        p_frame = grab_preview_frame(cam_source)
                        st.session_state["webcam_preview_frame"] = p_frame
                        st.session_state["webcam_preview_source"] = cam_source
                        st.success("Preview frame acquired.")
                    except Exception as exc:
                        st.error(f"Failed to grab preview: {exc}")

            with col_btn_rec:
                if st.button("🔴 Record Live Capture", type="primary", key="btn_record_live"):
                    prog = st.progress(0.0)
                    stat_txt = st.empty()

                    def _cb(pct: float) -> None:
                        prog.progress(pct)
                        stat_txt.text(f"Acquiring live frames... {pct * 100:.0f}%")

                    import datetime

                    now_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    out_dir = Path("output/webcam_captures")
                    out_dir.mkdir(parents=True, exist_ok=True)
                    target_mp4 = out_dir / f"webcam_{now_str}.mp4"

                    try:
                        res = capture_live_clip(
                            source=cam_source,
                            duration_s=float(cam_duration),
                            target_fps=float(cam_fps),
                            output_path=target_mp4,
                            progress_callback=_cb,
                        )
                        st.session_state["webcam_capture_result"] = res
                        st.session_state["webcam_capture_path"] = res.video_path
                        if res.stability.measured_fps > 0:
                            st.session_state["fps_override_val"] = float(round(res.stability.measured_fps, 2))
                        st.success(f"Capture completed: {len(res.frames)} frames saved.")
                    except Exception as exc:
                        st.error(f"Live capture failed: {exc}")

            if "webcam_capture_result" in st.session_state:
                res = st.session_state["webcam_capture_result"]
                video_path = st.session_state.get("webcam_capture_path")
                live_stability = res.stability

    # Frame-Rate Stability Card (CAP-03, CAP-04, CAP-05)
    if live_stability is not None:
        st.markdown("---")
        st.markdown("### ⏱️ Frame-Rate Stability Card")
        col_st1, col_st2, col_st3, col_st4 = st.columns(4)
        with col_st1:
            st.markdown(f"**Timing Status:** {stability_badge(live_stability.status)}")
        with col_st2:
            st.metric("Measured FPS", f"{live_stability.measured_fps:.2f} Hz", help="Empirical 1/median(dt)")
        with col_st3:
            st.metric("Timing Jitter", f"{live_stability.jitter_ratio * 100:.2f}%", help="std(dt) / median(dt)")
        with col_st4:
            st.metric("Dropped Frames", f"{live_stability.dropped_frames_count}", help="Intervals > 1.5x median")

        if live_stability.status == "REJECTED_UNSTABLE":
            st.error(
                "❌ **Acquisition Unstable:** Frame-rate timing irregular. "
                "Webcam auto-exposure throttling, high CPU load, or USB bandwidth saturation detected. "
                "Measurement is blocked to prevent false vibration peaks."
            )
            for r in live_stability.status_reasons:
                st.write(f"- {r}")
        elif live_stability.status == "WARNING_JITTER":
            st.warning("⚠️ **Moderate Jitter:** Small timing jitter or dropped frames detected. Analysis permitted with caution.")
            for r in live_stability.status_reasons:
                st.write(f"- {r}")
        else:
            st.success("✅ **Stable Acquisition:** High-regularity frame arrival verified. Ready for spectral analysis.")

    # Determine first frame for ROI configuration
    first_frame = None
    if video_path is not None and Path(video_path).exists():
        try:
            meta = get_video_metadata(video_path)
            first_frame = read_first_frame(video_path)
        except Exception as exc:
            st.error(f"Failed to load video: {exc}")
            return
    elif source_mode == "Live Webcam Stream" and "webcam_preview_frame" in st.session_state:
        first_frame = st.session_state["webcam_preview_frame"]
        meta = {
            "fps": float(st.session_state.get("webcam_fps_val", 30.0)),
            "frame_count": 1,
            "duration_s": 0.0,
        }

    if first_frame is None:
        if source_mode == "Live Webcam Stream":
            st.info("💡 Click **'📸 Grab Preview Frame'** to inspect live camera view and configure ROIs, or **'🔴 Record Live Capture'** to acquire a clip.")
        else:
            st.info("Select or upload a video file to proceed.")
        return

    frame_h, frame_w = first_frame.shape[:2]
    file_display = video_path.name if video_path is not None else "Live Preview Frame"
    st.write(
        f"**File / Stream:** `{file_display}` | **Dimensions:** {frame_w}x{frame_h} px | "
        f"**FPS:** {meta['fps']:.2f} | **Frames:** {meta['frame_count']} "
        f"({meta['duration_s']:.2f} s)"
    )

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
            tx = st.number_input("Target X", min_value=0, max_value=max(0, frame_w - 32), step=5, key="tx_input")
            ty = st.number_input("Target Y", min_value=0, max_value=max(0, frame_h - 32), step=5, key="ty_input")
        with col_t2:
            tw = st.number_input("Target Width", min_value=32, max_value=frame_w, step=5, key="tw_input")
            th = st.number_input("Target Height", min_value=32, max_value=frame_h, step=5, key="th_input")

    with col_roi_a:
        st.markdown("**Static Anchor ROI (Background)** — Orange Box")
        col_a1, col_a2 = st.columns(2)
        with col_a1:
            ax = st.number_input("Anchor X", min_value=0, max_value=max(0, frame_w - 32), step=5, key="ax_input")
            ay = st.number_input("Anchor Y", min_value=0, max_value=max(0, frame_h - 32), step=5, key="ay_input")
        with col_a2:
            aw = st.number_input("Anchor Width", min_value=32, max_value=frame_w, step=5, key="aw_input")
            ah = st.number_input("Anchor Height", min_value=32, max_value=frame_h, step=5, key="ah_input")

    target_roi = ROI(int(tx), int(ty), int(tw), int(th))
    anchor_roi = ROI(int(ax), int(ay), int(aw), int(ah))

    # Real-time ROI validation
    roi_errors = validate_rois(first_frame, target_roi, anchor_roi, min_size=32, min_texture_std=2.0)

    # Frame preview with overlaid bounding boxes
    annotated_frame = draw_rois_on_frame(first_frame, target_roi, anchor_roi)
    rgb_preview = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
    st.image(rgb_preview, caption="First Frame with Target (Green) & Anchor (Orange) ROIs", use_container_width=True)

    if roi_errors:
        for err in roi_errors:
            st.error(f"⚠️ {err}")
        st.warning("Fix the ROI settings above before running analysis.")
    else:
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
            step=1.0,
            key="fps_override_val",
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
    run_disabled = (
        bool(roi_errors)
        or video_path is None
        or (live_stability is not None and live_stability.status == "REJECTED_UNSTABLE")
    )
    if video_path is None and source_mode == "Live Webcam Stream":
        st.info("💡 Configure ROIs on the preview frame, then click **'🔴 Record Live Capture'** above to acquire a clip for vibration analysis.")
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
                st.session_state["latest_csv_path"] = str(Path(summary["outputs"]["csv"]))
                st.session_state["latest_video_name"] = video_path.name
                st.success("Analysis complete!")
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

    # Display results if available
    if st.session_state.get("latest_summary"):
        display_inspection_results(sm, active_asset, st.session_state["latest_summary"])


def display_inspection_results(
    sm: StorageManager, active_asset: AssetRecord | None, summary: dict
) -> None:
    st.markdown("---")
    st.subheader(f"Measurement Results: {Path(summary['video']).name}")

    st.warning(
        "⚠️ **Disclaimer:** "
        + summary.get(
            "interpretation",
            "Screening measurement in pixels; not a calibrated vibration diagnosis.",
        )
    )

    x_data = summary["x_axis"]
    y_data = summary["y_axis"]

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        st.markdown("### X-Axis Relative Motion")
        q = x_data["signal_quality"]
        if q == "VALID":
            st.success("**Quality Status:** VALID")
        elif q == "CONTAMINATED":
            st.error("**Quality Status:** CONTAMINATED (shared peak with anchor)")
        else:
            st.warning("**Quality Status:** LOW_SIGNAL (no prominent peak)")

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
            st.success("**Quality Status:** VALID")
        elif qy == "CONTAMINATED":
            st.error("**Quality Status:** CONTAMINATED (shared peak with anchor)")
        else:
            st.warning("**Quality Status:** LOW_SIGNAL (no prominent peak)")

        st.metric("Dominant Frequency", f"{y_data['dominant_frequency_hz']:.3f} Hz")
        st.metric("Displacement RMS", f"{y_data['rms_displacement_px']:.4f} px")
        st.metric("Spectral Prominence", f"{y_data['peak_to_median_db']:.2f} dB")
        if y_data.get("second_harmonic_ratio") is not None:
            st.metric("2x Harmonic Ratio", f"{y_data['second_harmonic_ratio']:.4f}")
        st.caption(
            f"Anchor peak: {y_data['anchor_dominant_frequency_hz']:.2f} Hz ({y_data['anchor_peak_to_median_db']:.1f} dB) | "
            f"Target peak: {y_data['target_dominant_frequency_hz']:.2f} Hz"
        )

    # 1-Click Auto-Assessment against Stored Baseline (HIST-05)
    evaluation_result: BaselineEvaluation | None = None
    latest_baseline = sm.get_latest_baseline_for_asset(active_asset.asset_id) if active_asset else None

    if active_asset and latest_baseline:
        st.markdown("---")
        st.markdown("### ⚡ Stored Baseline Auto-Assessment")
        st.write(
            f"Reference Baseline: `{latest_baseline.baseline_id}` "
            f"({latest_baseline.run_count} healthy runs, recorded {latest_baseline.created_at[:19]})."
        )

        col_assess_btn, col_assess_info = st.columns([1, 3])
        with col_assess_btn:
            do_assess = st.button("Evaluate Against Stored Baseline", type="secondary")

        if do_assess or st.session_state.get("auto_evaluated_for") == summary["video"]:
            st.session_state["auto_evaluated_for"] = summary["video"]
            evaluation_result = evaluate_run_against_baseline(
                summary,
                latest_baseline.baseline_record,
                z_threshold=3.0,
                axis="x",
            )
            st.session_state["latest_evaluation"] = evaluation_result

            # Display verdict banner
            v = evaluation_result.status
            if v == "Normal":
                st.success("🟢 **Verdict: NORMAL** — All monitored features within baseline 3-MAD bounds.")
            elif v == "Review":
                st.error("🔴 **Verdict: REVIEW REQUIRED** — Significant deviation detected from healthy baseline.")
            else:
                st.warning("🟡 **Verdict: LOW CONFIDENCE** — Measurement suppressed due to signal quality check.")

            if evaluation_result.reasons:
                for r in evaluation_result.reasons:
                    st.write(f"- {r}")

            # Deviations table
            dev_rows = []
            for k, d in evaluation_result.deviations.items():
                cur_val = f"{d.current_value:.4f}" if d.current_value is not None else "n/a"
                med_val = f"{d.baseline_median:.4f}" if d.baseline_median is not None else "n/a"
                z_val = f"{d.z_robust:+.2f}z" if d.z_robust is not None else "n/a"
                flag = "🔴 EXCEEDED" if d.is_trigger else "✅ Normal"
                dev_rows.append({
                    "Feature": d.feature_name,
                    "Axis": d.axis.upper(),
                    "Current": cur_val,
                    "Baseline Median": med_val,
                    "Robust Shift": z_val,
                    "Status": flag,
                })
            if dev_rows:
                st.table(dev_rows)

    # Persistence action: Save Run to Asset History
    st.markdown("---")
    st.markdown("### 💾 Asset History Persistence")
    if active_asset:
        col_save_btn, col_save_msg = st.columns([1, 3])
        with col_save_btn:
            save_clicked = st.button("Save Run to Asset History", type="primary")

        if save_clicked:
            csv_path = Path(summary["outputs"]["csv"])
            arrays = run_arrays_from_csv(csv_path, fps=summary["fps_used"])
            status_to_store = "Unassessed"
            if evaluation_result:
                status_to_store = evaluation_result.status
            elif "latest_evaluation" in st.session_state:
                status_to_store = st.session_state["latest_evaluation"].status

            run_rec = sm.create_inspection_run(
                asset_id=active_asset.asset_id,
                video_path=summary["video"],
                measured_fps=summary["fps_used"],
                duration_s=summary["duration_s"],
                frames_analysed=summary["frames_analysed"],
                summary=summary,
                baseline_id=latest_baseline.baseline_id if latest_baseline else None,
                arrays=arrays,
                status=status_to_store,
            )
            st.success(f"✅ Saved Inspection Run `{run_rec.run_id}` linked to `{active_asset.name}` (Status: {status_to_store}).")
    else:
        st.info("💡 Select an Active Machine Asset in the sidebar to save this run to local history.")

    # Plot display
    plot_path = Path(summary["outputs"]["plot"])
    if plot_path.exists():
        st.image(
            str(plot_path),
            caption="Displacement Traces (Top) and Welch Power Spectral Density (Bottom)",
            use_container_width=True,
        )

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


# ---------------------------------------------------------------------------
# Tab 2: Asset Management
# ---------------------------------------------------------------------------

def render_asset_management_tab(sm: StorageManager) -> None:
    st.subheader("Asset Directory & Configuration")
    st.caption(
        "Manage monitored machine assets and their baseline ROI boundaries. "
        "Configuring assets ensures repeatable vibration screening across inspections."
    )

    assets = sm.list_assets()

    # Asset Catalog
    if not assets:
        st.info("No machine assets registered yet. Register your first machine asset below.")
    else:
        st.markdown(f"#### Registered Machine Assets ({len(assets)})")
        rows = []
        for a in assets:
            baselines = sm.list_baselines_for_asset(a.asset_id)
            runs = sm.list_inspection_runs(a.asset_id)
            rpm_str = f"{a.nominal_speed_rpm:.1f}" if a.nominal_speed_rpm else "n/a"
            rows.append({
                "ID": a.asset_id,
                "Name": a.name,
                "Expected FPS": f"{a.expected_fps:.1f}",
                "Nominal RPM": rpm_str,
                "Target ROI": f"{a.target_roi.get('width')}x{a.target_roi.get('height')} @ ({a.target_roi.get('x')},{a.target_roi.get('y')})",
                "Anchor ROI": f"{a.anchor_roi.get('width')}x{a.anchor_roi.get('height')} @ ({a.anchor_roi.get('x')},{a.anchor_roi.get('y')})",
                "Baselines": len(baselines),
                "Runs": len(runs),
                "Updated": a.updated_at[:19],
            })
        st.dataframe(rows, use_container_width=True)

    st.markdown("---")
    col_reg, col_edit = st.columns(2)

    # Asset Registration
    with col_reg:
        st.markdown("### ➕ Register New Machine Asset")
        with st.form("register_asset_form"):
            new_name = st.text_input("Asset Name*", placeholder="e.g. Chilled Water Pump 1")
            new_desc = st.text_area("Description", placeholder="Location, service, motor model...")
            col_s1, col_s2 = st.columns(2)
            with col_s1:
                new_fps = st.number_input("Expected Video FPS*", min_value=1.0, max_value=1000.0, value=60.0, step=1.0)
            with col_s2:
                new_rpm = st.number_input("Nominal Speed (RPM)", min_value=0.0, max_value=50000.0, value=0.0, step=50.0)

            st.markdown("**Target ROI (Machine)**")
            col_nt1, col_nt2 = st.columns(2)
            with col_nt1:
                nt_x = st.number_input("Target X", min_value=0, value=int(st.session_state.get("tx_input", DEFAULT_SAMPLE_TARGET_ROI.x)), step=5)
                nt_y = st.number_input("Target Y", min_value=0, value=int(st.session_state.get("ty_input", DEFAULT_SAMPLE_TARGET_ROI.y)), step=5)
            with col_nt2:
                nt_w = st.number_input("Target W", min_value=32, value=int(st.session_state.get("tw_input", DEFAULT_SAMPLE_TARGET_ROI.width)), step=5)
                nt_h = st.number_input("Target H", min_value=32, value=int(st.session_state.get("th_input", DEFAULT_SAMPLE_TARGET_ROI.height)), step=5)

            st.markdown("**Anchor ROI (Background)**")
            col_na1, col_na2 = st.columns(2)
            with col_na1:
                na_x = st.number_input("Anchor X", min_value=0, value=int(st.session_state.get("ax_input", DEFAULT_SAMPLE_ANCHOR_ROI.x)), step=5)
                na_y = st.number_input("Anchor Y", min_value=0, value=int(st.session_state.get("ay_input", DEFAULT_SAMPLE_ANCHOR_ROI.y)), step=5)
            with col_na2:
                na_w = st.number_input("Anchor W", min_value=32, value=int(st.session_state.get("aw_input", DEFAULT_SAMPLE_ANCHOR_ROI.width)), step=5)
                na_h = st.number_input("Anchor H", min_value=32, value=int(st.session_state.get("ah_input", DEFAULT_SAMPLE_ANCHOR_ROI.height)), step=5)

            new_asset_id_input = st.text_input("Custom Asset ID (optional)", placeholder="Auto-generated if blank")

            submit_reg = st.form_submit_button("Register Asset", type="primary")

            if submit_reg:
                if not new_name.strip():
                    st.error("Asset name is required.")
                else:
                    try:
                        created = sm.create_asset(
                            name=new_name.strip(),
                            target_roi={"x": int(nt_x), "y": int(nt_y), "width": int(nt_w), "height": int(nt_h)},
                            anchor_roi={"x": int(na_x), "y": int(na_y), "width": int(na_w), "height": int(na_h)},
                            expected_fps=float(new_fps),
                            description=new_desc.strip(),
                            nominal_speed_rpm=float(new_rpm) if new_rpm > 0 else None,
                            asset_id=new_asset_id_input.strip() if new_asset_id_input.strip() else None,
                        )
                        st.session_state["selected_asset_id"] = created.asset_id
                        st.success(f"Asset '{created.name}' registered with ID `{created.asset_id}`!")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to register asset: {exc}")

    # Parameter Editor & Deletion
    with col_edit:
        st.markdown("### ✏️ Edit or Delete Asset")
        if not assets:
            st.info("No assets to edit.")
        else:
            asset_to_edit_id = st.selectbox(
                "Select Asset to Manage:",
                [a.asset_id for a in assets],
                format_func=lambda x: f"{next(a.name for a in assets if a.asset_id == x)} ({x})",
            )
            target_asset = sm.get_asset(asset_to_edit_id)

            if target_asset:
                with st.form("edit_asset_form"):
                    ed_name = st.text_input("Name", value=target_asset.name)
                    ed_desc = st.text_area("Description", value=target_asset.description)
                    ed_rpm = st.number_input(
                        "Nominal RPM",
                        value=float(target_asset.nominal_speed_rpm or 0.0),
                        step=50.0,
                    )
                    ed_fps = st.number_input(
                        "Expected FPS",
                        value=float(target_asset.expected_fps),
                        step=1.0,
                    )
                    save_edit = st.form_submit_button("Update Asset Parameters")
                    if save_edit:
                        try:
                            sm.update_asset(
                                target_asset.asset_id,
                                name=ed_name,
                                description=ed_desc,
                                nominal_speed_rpm=float(ed_rpm) if ed_rpm > 0 else None,
                                expected_fps=float(ed_fps),
                            )
                            st.success(f"Asset `{target_asset.asset_id}` updated!")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Failed to update asset: {exc}")

                st.markdown("#### 🗑️ Danger Zone: Delete Asset")
                del_cascade = st.checkbox(
                    "Cascade delete associated baselines, inspection runs, and NPZ files from disk",
                    value=True,
                )
                if st.button("Permanently Delete Asset", type="secondary"):
                    if sm.delete_asset(target_asset.asset_id, delete_files=del_cascade):
                        if st.session_state.get("selected_asset_id") == target_asset.asset_id:
                            st.session_state["selected_asset_id"] = None
                        st.success(f"Asset `{target_asset.asset_id}` deleted.")
                        st.rerun()


# ---------------------------------------------------------------------------
# Tab 3: Baseline Wizard
# ---------------------------------------------------------------------------

def render_baseline_wizard_tab(sm: StorageManager, active_asset: AssetRecord | None) -> None:
    st.subheader("Baseline Recording Wizard (N ≥ 3)")
    st.caption(
        "Establish an immutable statistical reference baseline for the active asset. "
        "Aggregates ≥ 3 healthy runs to compute robust Median and MAD parameters."
    )

    if not active_asset:
        st.warning("⚠️ Please select an **Active Machine Asset** in the sidebar before recording a baseline.")
        return

    st.info(
        f"Configuring baseline for **{active_asset.name}** (`{active_asset.asset_id}`). "
        f"Expected FPS: {active_asset.expected_fps:.1f} | Target ROI: {active_asset.target_roi} | "
        f"Anchor ROI: {active_asset.anchor_roi}"
    )

    # Step 1: Candidate Runs Selection
    st.markdown("#### Step 1: Select Candidate Healthy Runs")
    cand_mode = st.radio(
        "Candidate Run Source:",
        ["Select from Active Asset History", "Upload Inspection Summary JSON Files"],
        horizontal=True,
    )

    candidate_runs: list[dict[str, Any]] = []

    if cand_mode == "Select from Active Asset History":
        history_runs = sm.list_inspection_runs(active_asset.asset_id)
        if not history_runs:
            st.warning(f"No inspection runs found in history for '{active_asset.name}'. Record or upload runs first.")
        else:
            run_options = [r.run_id for r in history_runs]
            selected_run_ids = st.multiselect(
                "Choose healthy runs to aggregate (select ≥ 3):",
                run_options,
                format_func=lambda x: f"{x} ({next(r.timestamp[:19] for r in history_runs if r.run_id == x)}) - {next(r.status for r in history_runs if r.run_id == x)}",
            )
            for r in history_runs:
                if r.run_id in selected_run_ids:
                    candidate_runs.append(r.summary)
    else:
        uploaded_files = st.file_uploader(
            "Upload ≥ 3 healthy inspection summary JSON files:",
            type=["json"],
            accept_multiple_files=True,
        )
        if uploaded_files:
            for f in uploaded_files:
                try:
                    candidate_runs.append(json.loads(f.getvalue().decode("utf-8")))
                except Exception as exc:
                    st.error(f"Failed to parse {f.name}: {exc}")

    if not candidate_runs:
        st.info("Select or upload at least 3 candidate runs to continue.")
        return

    # Candidate Run Preview
    st.markdown(f"**Candidate Runs Loaded:** {len(candidate_runs)}")

    # Step 2: Live Validation Engine
    st.markdown("#### Step 2: Live Validation Checks")
    quorum_ok = len(candidate_runs) >= 3
    if quorum_ok:
        st.success(f"✅ Quorum Check: {len(candidate_runs)} runs selected (N ≥ 3 satisfied)")
    else:
        st.error(f"❌ Quorum Failure: {len(candidate_runs)} runs selected. Minimum 3 required for robust statistics.")

    # Spatial ROI consistency check
    roi_mismatches = 0
    for idx, r in enumerate(candidate_runs):
        t_match = _rois_match(r.get("target_roi_xywh", {}), active_asset.target_roi, tolerance=2)
        a_match = _rois_match(r.get("anchor_roi_xywh", {}), active_asset.anchor_roi, tolerance=2)
        if not (t_match and a_match):
            roi_mismatches += 1

    if roi_mismatches == 0:
        st.success("✅ Spatial ROI Consistency: All candidate runs match active asset ROI coordinates (±2 px).")
    else:
        st.error(f"❌ Spatial ROI Divergence: {roi_mismatches} run(s) differ from configured asset ROIs by >2 pixels.")

    # Sampling rate check
    fps_mismatches = 0
    for r in candidate_runs:
        used_fps = float(r.get("fps_used", 0.0))
        if abs(used_fps - active_asset.expected_fps) / active_asset.expected_fps > 0.02:
            fps_mismatches += 1

    if fps_mismatches == 0:
        st.success(f"✅ Sampling Rate Consistency: All runs within ±2% of expected FPS ({active_asset.expected_fps:.1f}).")
    else:
        st.error(f"❌ Sampling Rate Inconsistency: {fps_mismatches} run(s) deviate from expected FPS.")

    # Signal quality check
    quality_ok = True
    for r in candidate_runs:
        q_x = r.get("x_axis", {}).get("signal_quality")
        q_y = r.get("y_axis", {}).get("signal_quality")
        if q_x != "VALID" and q_y != "VALID":
            quality_ok = False

    if quality_ok:
        st.success("✅ Signal Quality Gate: All runs contain at least one VALID machine axis.")
    else:
        st.error("❌ Signal Quality Gate: One or more candidate runs lack a VALID signal axis.")

    all_valid = quorum_ok and (roi_mismatches == 0) and (fps_mismatches == 0) and quality_ok

    # Step 3: Statistical Preview
    if all_valid:
        st.markdown("#### Step 3: Statistical Baseline Preview")
        try:
            preview_baseline = build_baseline(candidate_runs, asset_id=active_asset.asset_id)
            x_b = preview_baseline.x_axis
            y_b = preview_baseline.y_axis

            prev_rows = [
                {
                    "Feature": "Dominant Frequency (Hz)",
                    "X Median": f"{x_b.dominant_frequency_hz.median:.3f}",
                    "X MAD": f"{x_b.dominant_frequency_hz.mad:.4f}",
                    "Y Median": f"{y_b.dominant_frequency_hz.median:.3f}",
                    "Y MAD": f"{y_b.dominant_frequency_hz.mad:.4f}",
                },
                {
                    "Feature": "Displacement RMS (px)",
                    "X Median": f"{x_b.rms_displacement_px.median:.4f}",
                    "X MAD": f"{x_b.rms_displacement_px.mad:.4f}",
                    "Y Median": f"{y_b.rms_displacement_px.median:.4f}",
                    "Y MAD": f"{y_b.rms_displacement_px.mad:.4f}",
                },
                {
                    "Feature": "Peak-to-Median (dB)",
                    "X Median": f"{x_b.peak_to_median_db.median:.2f}",
                    "X MAD": f"{x_b.peak_to_median_db.mad:.2f}",
                    "Y Median": f"{y_b.peak_to_median_db.median:.2f}",
                    "Y MAD": f"{y_b.peak_to_median_db.mad:.2f}",
                },
            ]
            st.table(prev_rows)

            # Step 4: Commit Baseline
            st.markdown("#### Step 4: Commit Stored Baseline")
            baseline_notes = st.text_input(
                "Baseline Notes",
                placeholder="e.g. Initial reference baseline under normal operating load.",
            )
            if st.button("💾 Save Stored Baseline to Asset", type="primary"):
                stored = sm.create_baseline(
                    asset_id=active_asset.asset_id,
                    baseline_record=preview_baseline,
                    notes=baseline_notes,
                )
                st.success(f"✅ Baseline `{stored.baseline_id}` saved successfully for '{active_asset.name}'!")
                st.rerun()
        except Exception as exc:
            st.error(f"Failed to generate statistical baseline: {exc}")


# ---------------------------------------------------------------------------
# Tab 4: Inspection History
# ---------------------------------------------------------------------------

def render_history_tab(sm: StorageManager, active_asset: AssetRecord | None) -> None:
    st.subheader("Historical Inspection Runs & Review Events")
    st.caption("Chronological audit log of vibration inspection runs, spectra, and operator reviews.")

    if not active_asset:
        st.warning("⚠️ Select an **Active Machine Asset** in the sidebar to view its inspection history.")
        return

    runs = sm.list_inspection_runs(active_asset.asset_id)
    if not runs:
        st.info(f"No inspection runs recorded for asset '{active_asset.name}' yet.")
        return

    # Filter Bar
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        status_filter = st.selectbox(
            "Filter by Status:",
            ["All", "Normal", "Review", "Low confidence", "Unassessed"],
        )
    with col_f2:
        max_runs = st.selectbox("Max Runs to Display:", [10, 25, 50, 100], index=1)

    filtered_runs = [r for r in runs if status_filter == "All" or r.status == status_filter][:max_runs]

    # History Table
    rows = []
    for r in filtered_runs:
        summary = r.summary
        x_freq = summary.get("x_axis", {}).get("dominant_frequency_hz", 0.0)
        x_rms = summary.get("x_axis", {}).get("rms_displacement_px", 0.0)
        rows.append({
            "Status": status_badge(r.status),
            "Timestamp": r.timestamp[:19],
            "Run ID": r.run_id,
            "Video": Path(r.video_path).name,
            "FPS": f"{r.measured_fps:.1f}",
            "Duration (s)": f"{r.duration_s:.1f}",
            "X Freq (Hz)": f"{x_freq:.2f}",
            "X RMS (px)": f"{x_rms:.4f}",
            "Baseline": r.baseline_id or "(None)",
        })
    st.table(rows)

    # Deep-Dive Run Inspector
    st.markdown("---")
    st.markdown("### 🔍 Deep-Dive Run Inspector")
    run_choice = st.selectbox(
        "Select Run to Inspect:",
        [r.run_id for r in filtered_runs],
        format_func=lambda x: f"{x} - {next(r.timestamp[:19] for r in filtered_runs if r.run_id == x)} ({next(r.status for r in filtered_runs if r.run_id == x)})",
    )
    inspected_run = next((r for r in filtered_runs if r.run_id == run_choice), None)

    if inspected_run:
        col_meta, col_actions = st.columns([2, 1])
        with col_meta:
            st.write(
                f"**Run ID:** `{inspected_run.run_id}` | **Status:** {status_badge(inspected_run.status)} | "
                f"**Timestamp:** {inspected_run.timestamp}"
            )
            st.write(
                f"**FPS:** {inspected_run.measured_fps:.2f} | **Frames:** {inspected_run.frames_analysed} | "
                f"**Duration:** {inspected_run.duration_s:.2f} s"
            )

        # On-Demand NPZ Array Loading & Visualization
        if inspected_run.npz_rel_path:
            try:
                arrays = sm.load_run_arrays(inspected_run.npz_rel_path)
                fig = plot_run_arrays(arrays, title=f"Run {inspected_run.run_id} — {Path(inspected_run.video_path).name}")
                st.pyplot(fig)
                plt.close(fig)

                # NPZ Download button
                npz_abs = sm.resolve_path(inspected_run.npz_rel_path)
                if npz_abs.is_file():
                    st.download_button(
                        "📥 Download Compressed Run NPZ",
                        data=npz_abs.read_bytes(),
                        file_name=f"{inspected_run.run_id}.npz",
                        mime="application/octet-stream",
                    )
            except Exception as exc:
                st.error(f"Failed to load run arrays from NPZ: {exc}")
        else:
            st.info("No NPZ arrays were saved with this run.")

        # Operator Review Event Logging Form
        st.markdown("---")
        st.markdown("### 📝 Log Operator Review Event")
        with st.form("review_event_form"):
            col_rev1, col_rev2 = st.columns(2)
            with col_rev1:
                rev_status = st.radio(
                    "Disposition Status*:",
                    ["Normal", "Review", "Low confidence"],
                    horizontal=True,
                )
            with col_rev2:
                operator_id = st.text_input("Operator ID", value="operator")

            operator_note = st.text_area(
                "Review Notes / Findings*",
                placeholder="Observed slight spectral shift around 8.5 Hz. Condition verified normal.",
            )

            submit_review = st.form_submit_button("Submit Review Event", type="primary")

            if submit_review:
                if not operator_note.strip():
                    st.error("Operator note is required.")
                else:
                    try:
                        event = sm.create_review_event(
                            run_id=inspected_run.run_id,
                            status=rev_status,
                            operator_note=operator_note.strip(),
                            operator_id=operator_id.strip(),
                        )
                        st.success(f"Review Event `{event.event_id}` logged! Run status updated to '{rev_status}'.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Failed to log review event: {exc}")

        # Past Review Events Timeline
        reviews = sm.list_review_events_for_run(inspected_run.run_id)
        if reviews:
            st.markdown("#### Review Event History")
            for rev in reviews:
                st.markdown(
                    f"**{status_badge(rev.status)}** | `{rev.created_at[:19]}` by **{rev.operator_id}**\n\n"
                    f"> {rev.operator_note}"
                )


# ---------------------------------------------------------------------------
# Tab 5: Baseline Comparison
# ---------------------------------------------------------------------------

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
                st.info("Loaded reference baseline (Asset: `portable_motor`, 3 runs, 60 FPS).")
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
            if "latest_summary" in st.session_state and st.session_state["latest_summary"]:
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
                st.info("Loaded sample changed result (`data/portable/changed.mp4`).")
        elif curr_src == "Use sample camera_only.mp4 result":
            sample_null = Path("data/portable/out_camera_only/camera_only_summary.json")
            if sample_null.exists():
                current_data = json.loads(sample_null.read_text(encoding="utf-8"))
                st.info("Loaded sample camera-only null result (`data/portable/camera_only.mp4`).")

    st.markdown("#### Screening Thresholds")
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        eval_axis = st.selectbox(
            "Axis to Evaluate:",
            ["x", "y", "both"],
            index=0,
            help="Evaluate machine vibration axis.",
        )
    with col_p2:
        z_thresh = st.number_input(
            "Robust z-score threshold (|z|)",
            min_value=1.0,
            max_value=10.0,
            value=3.0,
            step=0.5,
            help="Number of MAD deviations above median before flagging Review.",
        )

    if baseline_record is None or current_data is None:
        st.info("Provide both a Reference Baseline Record and a Current Inspection Run to evaluate.")
        return

    st.markdown("---")
    st.subheader("Statistical Screening Assessment")

    try:
        evaluation = evaluate_run_against_baseline(
            current_data,
            baseline_record,
            z_threshold=float(z_thresh),
            axis=eval_axis,
        )

        st.caption(f"Asset: `{evaluation.asset_id}` | Baseline: `{evaluation.baseline_id}` | Threshold: |z| ≥ {evaluation.z_threshold:.1f}")

        status = evaluation.status
        if status == "Normal":
            st.success("🟢 **Screening Status: NORMAL** — All monitored features within robust threshold.")
        elif status == "Review":
            st.error("🔴 **Screening Status: REVIEW** — One or more features significantly deviate from baseline.")
        else:
            st.warning("🟡 **Screening Status: LOW CONFIDENCE** — Signal quality check failed.")

        st.info(f"**Interpretation:** {evaluation.interpretation}")

        if not evaluation.confidence_passed:
            st.error("#### ⚠️ Confidence Gate Triggered")
            for reason in evaluation.reasons:
                st.write(f"- {reason}")

        if evaluation.trigger_features:
            st.error(f"#### 🚨 Triggered Features ({len(evaluation.trigger_features)})")
            for trig in evaluation.trigger_features:
                st.write(f"- **{trig}**")

        st.markdown("#### Feature Deviation Matrix")
        matrix_rows = []
        for key, dev in evaluation.deviations.items():
            curr_str = f"{dev.current_value:.4f}" if dev.current_value is not None else "n/a"
            base_med = f"{dev.baseline_median:.4f}" if dev.baseline_median is not None else "n/a"
            base_mad = f"{dev.baseline_mad:.4f}" if dev.baseline_mad is not None else "n/a"
            z_str = f"{dev.z_robust:+.2f}z" if dev.z_robust is not None else "n/a"
            flag = "🔴 EXCEEDED" if dev.is_trigger else "✅ Normal"
            matrix_rows.append({
                "Feature": dev.feature_name,
                "Axis": dev.axis.upper(),
                "Current Value": curr_str,
                "Baseline Median": base_med,
                "Baseline MAD": base_mad,
                "Robust z-score": z_str,
                "Status": flag,
                "Notes": dev.notes or "-",
            })

        st.table(matrix_rows)

        # Plot z-scores
        z_scores = {k: dev.z_robust for k, dev in evaluation.deviations.items() if dev.z_robust is not None}
        if z_scores:
            st.markdown("#### Normalized Robust Deviation Scores (|z|)")
            fig, ax = plt.subplots(figsize=(8, 3.5), constrained_layout=True)
            names = list(z_scores.keys())
            vals = [z_scores[k] for k in names]
            colors = ["#d62728" if abs(v) >= z_thresh else "#2ca02c" for v in vals]
            y_pos = np.arange(len(names))
            ax.barh(y_pos, vals, color=colors, align="center")
            ax.axvline(x=z_thresh, color="red", linestyle="--", alpha=0.7, label=f"+{z_thresh}z threshold")
            ax.axvline(x=-z_thresh, color="red", linestyle="--", alpha=0.7, label=f"-{z_thresh}z threshold")
            ax.set_yticks(y_pos)
            ax.set_yticklabels(names)
            ax.set_xlabel("Robust z-score")
            ax.set_title("Standardized Feature Drift Relative to Baseline")
            ax.legend(loc="lower right")
            st.pyplot(fig)
            plt.close(fig)

        # Download report
        st.download_button(
            "📥 Download Evaluation Report (JSON)",
            data=evaluation.to_json(indent=2),
            file_name=f"assessment_{evaluation.baseline_id}.json",
            mime="application/json",
            use_container_width=True,
        )

    except Exception as exc:
        st.error(f"Evaluation failed: {exc}")


def render_pairwise_comparison_section() -> None:
    st.markdown("#### Pairwise Comparison Parameters")
    col_p1, col_p2, col_p3 = st.columns(3)
    with col_p1:
        axis_choice = st.selectbox("Axis to compare", ["x", "y"], index=0, key="pair_axis")
    with col_p2:
        warning_thresh = st.number_input(
            "Warning RMS Change (%)",
            min_value=1.0,
            max_value=200.0,
            value=25.0,
            step=5.0,
            key="pair_warn",
        )
    with col_p3:
        alert_thresh = st.number_input(
            "Alert RMS Change (%)",
            min_value=1.0,
            max_value=500.0,
            value=50.0,
            step=5.0,
            key="pair_alert",
        )

    col_b, col_c = st.columns(2)
    with col_b:
        st.markdown("**1. Reference Baseline Summary**")
        baseline_file = st.file_uploader("Upload baseline JSON:", type=["json"], key="pair_base_file")
    with col_c:
        st.markdown("**2. Current Inspection Summary**")
        current_file = st.file_uploader("Upload current JSON:", type=["json"], key="pair_curr_file")

    if baseline_file and current_file:
        try:
            baseline_data = json.loads(baseline_file.getvalue().decode("utf-8"))
            current_data = json.loads(current_file.getvalue().decode("utf-8"))
            report = compare_inspection_summaries(
                baseline_data,
                current_data,
                axis=axis_choice,
                warning_rms_change_percent=float(warning_thresh),
                alert_rms_change_percent=float(alert_thresh),
                baseline_label=baseline_file.name,
                current_label=current_file.name,
            )
            st.markdown("---")
            st.markdown(f"### Comparison Status: **{report['status']}**")
            st.write(f"**Interpretation:** {report['interpretation']}")
            st.json(report)
        except Exception as exc:
            st.error(f"Failed to compare summaries: {exc}")


# ---------------------------------------------------------------------------
# Tab 6: Technical Boundaries
# ---------------------------------------------------------------------------

def render_about_tab() -> None:
    st.subheader("Technical Boundaries & Measurement Principles")
    st.markdown(
        """
        PhaseSight is an exploratory engineering prototype demonstrating camera-based vibration screening.
        
        #### Non-Negotiable Technical Boundaries
        1. **Pixel-Domain Measurements Only:** All displacements, amplitudes, and spectra are reported in
           **image pixels**, not millimetres (mm), velocity (mm/s), or acceleration ($g$).
        2. **2D Translation Only:** Tracking measures planar horizontal and vertical translation using
           OpenCV `phaseCorrelate`. It does not compensate for camera rotation, perspective changes, zoom,
           parallax, or rolling-shutter artifacts.
        3. **Differential Static Anchor:** Common camera translation is subtracted using a stationary
           background anchor. The anchor must be physically non-moving and visually textured.
        4. **Screening, Not Fault Diagnosis:** Output flags (`Normal`, `Review`, `Low confidence`)
           represent statistical deviations from an established baseline. They do not diagnose specific
           machine fault modes (bearing wear, unbalance, misalignment, or gear mesh failure).
        5. **Separation of Measurement and Magnification:** Riesz motion magnification is an optional
           visual preview and does not feed the numerical measurement or alert engine.
        """
    )


if __name__ == "__main__":
    main()
