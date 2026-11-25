"""Batch video inspection run endpoints."""

from __future__ import annotations

import asyncio
import csv
import json
from pathlib import Path
from typing import Any
import uuid

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request, status
from starlette.datastructures import UploadFile

from backend.deps import get_manager, get_storage
from backend.manager import MonitoringManager
from backend.presets import resolve_video_path
from backend.schemas import sanitize_json
from phasesight.analysis import analyse_displacement
from phasesight.baseline import evaluate_run_against_baseline
from phasesight.storage import RunArrays, StorageManager
from phasesight.tracker import ROI
from phasesight.video import analyse_video

router = APIRouter(prefix="/runs", tags=["runs"])


def _parse_roi_input(raw: Any, name: str) -> ROI:
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
        except Exception as exc:
            raise ValueError(f"Invalid JSON for {name}: {exc}")
    elif isinstance(raw, dict):
        data = raw
    else:
        raise ValueError(f"Missing or invalid {name}")

    for k in ("x", "y", "width", "height"):
        if k not in data:
            raise ValueError(f"{name} missing required key '{k}'")

    return ROI(
        x=int(data["x"]),
        y=int(data["y"]),
        width=int(data["width"]),
        height=int(data["height"]),
    )


def _execute_analysis(
    video_path: Path,
    target_roi: ROI,
    anchor_roi: ROI,
    output_dir: Path,
    fps_override: float | None,
    nperseg: int,
) -> tuple[dict[str, Any], RunArrays]:
    """Execute analyse_video and assemble RunArrays."""
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = analyse_video(
        video_path=video_path,
        target_roi=target_roi,
        anchor_roi=anchor_roi,
        output_dir=output_dir,
        fps_override=fps_override,
        nperseg=nperseg,
    )

    csv_path = Path(summary["outputs"]["csv"])
    timestamps, tgt_dx, tgt_dy, anc_dx, anc_dy, rel_dx, rel_dy = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
    )
    tgt_resp, anc_resp = [], []

    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            timestamps.append(float(row["timestamp_s"]))
            tgt_dx.append(float(row["target_dx_px"]))
            tgt_dy.append(float(row["target_dy_px"]))
            anc_dx.append(float(row["anchor_dx_px"]))
            anc_dy.append(float(row["anchor_dy_px"]))
            rel_dx.append(float(row["relative_dx_px"]))
            rel_dy.append(float(row["relative_dy_px"]))
            tgt_resp.append(float(row["target_response"]))
            anc_resp.append(float(row["anchor_response"]))

    t_arr = np.asarray(timestamps, dtype=np.float64)
    x_arr = np.asarray(rel_dx, dtype=np.float64)
    y_arr = np.asarray(rel_dy, dtype=np.float64)

    fs = float(summary.get("fps_used", 30.0))
    nyquist = fs / 2.0
    usable_max = min(nyquist * 0.9, nyquist * 0.95)

    x_res = analyse_displacement(
        t_arr, x_arr, min_frequency_hz=0.5, max_frequency_hz=usable_max, nperseg=nperseg
    )
    y_res = analyse_displacement(
        t_arr, y_arr, min_frequency_hz=0.5, max_frequency_hz=usable_max, nperseg=nperseg
    )

    arrays = RunArrays(
        timestamps_s=t_arr,
        relative_dx_px=x_arr,
        relative_dy_px=y_arr,
        target_dx_px=np.asarray(tgt_dx, dtype=np.float64),
        target_dy_px=np.asarray(tgt_dy, dtype=np.float64),
        anchor_dx_px=np.asarray(anc_dx, dtype=np.float64),
        anchor_dy_px=np.asarray(anc_dy, dtype=np.float64),
        target_response=np.asarray(tgt_resp, dtype=np.float64),
        anchor_response=np.asarray(anc_resp, dtype=np.float64),
        x_frequencies_hz=x_res.frequencies_hz,
        x_psd_px2_per_hz=x_res.psd_px2_per_hz,
        y_frequencies_hz=y_res.frequencies_hz,
        y_psd_px2_per_hz=y_res.psd_px2_per_hz,
    )
    return summary, arrays


@router.post("/analyze")
async def analyze_video_run(
    request: Request,
    storage: StorageManager = Depends(get_storage),
    manager: MonitoringManager = Depends(get_manager),
) -> dict[str, Any]:
    """Run batch offline vibration analysis on a video."""
    content_type = request.headers.get("content-type", "")

    file_obj: UploadFile | None = None
    preset_id: str | None = None
    upload_id: str | None = None
    raw_target_roi: Any = None
    raw_anchor_roi: Any = None
    fps_override: float | None = None
    asset_id: str | None = None
    nperseg = 256

    if "multipart/form-data" in content_type:
        form = await request.form()
        preset_id = form.get("preset_id")  # type: ignore
        upload_id = form.get("upload_id")  # type: ignore
        raw_target_roi = form.get("target_roi")
        raw_anchor_roi = form.get("anchor_roi")
        fps_override_val = form.get("fps_override")
        if fps_override_val:
            fps_override = float(fps_override_val)  # type: ignore
        asset_id = form.get("asset_id")  # type: ignore
        nperseg_val = form.get("nperseg")
        if nperseg_val:
            nperseg = int(nperseg_val)  # type: ignore

        if "file" in form and isinstance(form["file"], UploadFile):
            file_obj = form["file"]
    else:
        body = await request.json()
        preset_id = body.get("preset_id")
        upload_id = body.get("upload_id")
        raw_target_roi = body.get("target_roi")
        raw_anchor_roi = body.get("anchor_roi")
        fps_override = (
            float(body["fps_override"]) if body.get("fps_override") is not None else None
        )
        asset_id = body.get("asset_id")
        nperseg = int(body.get("nperseg", 256))

    if file_obj is not None and file_obj.filename:
        upload_id = f"upl_{uuid.uuid4().hex[:10]}"
        ext = Path(file_obj.filename).suffix or ".mp4"
        dest_path = manager.uploads_dir / f"{upload_id}{ext}"
        content = await file_obj.read()
        dest_path.write_bytes(content)
        resolved_path = dest_path
        preset_id = None
    else:
        try:
            resolved_path = resolve_video_path(
                preset_id, upload_id, manager.uploads_dir
            )
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
            )

    try:
        target_roi = _parse_roi_input(raw_target_roi, "target_roi")
        anchor_roi = _parse_roi_input(raw_anchor_roi, "anchor_roi")
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    output_dir = storage.storage_root / "batch_outputs" / run_id

    try:
        summary, arrays = await asyncio.to_thread(
            _execute_analysis,
            resolved_path,
            target_roi,
            anchor_roi,
            output_dir,
            fps_override,
            nperseg,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Video analysis failed: {exc}",
        )

    effective_asset_id = asset_id or "quick_bench"
    if not storage.get_asset(effective_asset_id):
        storage.create_asset(
            name="Quick Bench Asset"
            if effective_asset_id == "quick_bench"
            else effective_asset_id,
            target_roi=target_roi,
            anchor_roi=anchor_roi,
            expected_fps=float(summary.get("fps_used", 30.0)),
            description="Auto-generated default asset for batch analysis runs.",
            asset_id=effective_asset_id,
        )

    # Evaluate against active baseline if available
    baseline_assessment = None
    stored_b = storage.get_latest_baseline_for_asset(effective_asset_id)
    run_status = "Unassessed"
    if stored_b:
        try:
            eval_axis = "both"
            curr_x_valid = summary.get("x_axis", {}).get("signal_quality") == "VALID"
            curr_y_valid = summary.get("y_axis", {}).get("signal_quality") == "VALID"
            if curr_x_valid and not curr_y_valid:
                eval_axis = "x"
            elif curr_y_valid and not curr_x_valid:
                eval_axis = "y"

            eval_res = evaluate_run_against_baseline(
                summary, stored_b.baseline_record, axis=eval_axis
            )
            eval_dict = eval_res.to_dict()
            eval_dict["overall_status"] = eval_res.status
            dev_zs = [
                abs(v.z_robust)
                for v in eval_res.deviations.values()
                if v.z_robust is not None
            ]
            eval_dict["max_z_score"] = max(dev_zs) if dev_zs else 0.0
            baseline_assessment = eval_dict
            run_status = eval_res.status
        except Exception:
            pass

    # Persist into storage
    run_rec = storage.create_inspection_run(
        asset_id=effective_asset_id,
        video_path=str(resolved_path),
        measured_fps=float(summary.get("fps_used", 30.0)),
        duration_s=float(summary.get("duration_s", 0.0)),
        frames_analysed=int(summary.get("frames_analysed", 0)),
        summary=summary,
        baseline_id=stored_b.baseline_id if stored_b else None,
        arrays=arrays,
        valid_patch_ratio=float(summary.get("valid_patch_ratio", 1.0)),
        status=run_status,
        run_id=run_id,
    )

    return sanitize_json(
        {
            "run_id": run_rec.run_id,
            "asset_id": run_rec.asset_id,
            "measured_fps": float(summary.get("fps_used", 30.0)),
            "duration_s": float(summary.get("duration_s", 0.0)),
            "frames_analysed": int(summary.get("frames_analysed", 0)),
            "x_metrics": summary.get("x_axis"),
            "y_metrics": summary.get("y_axis"),
            "temporal_stability": summary.get("temporal_stability"),
            "summary": summary,
            "baseline_assessment": baseline_assessment,
            "arrays": {
                "timestamps_s": arrays.timestamps_s,
                "times_s": arrays.timestamps_s,
                "relative_dx_px": arrays.relative_dx_px,
                "rel_dx_px": arrays.relative_dx_px,
                "relative_dy_px": arrays.relative_dy_px,
                "rel_dy_px": arrays.relative_dy_px,
                "x_frequencies_hz": arrays.x_frequencies_hz,
                "x_psd_px2_per_hz": arrays.x_psd_px2_per_hz,
                "y_frequencies_hz": arrays.y_frequencies_hz,
                "y_psd_px2_per_hz": arrays.y_psd_px2_per_hz,
            },
        }
    )


def _serialize_run_record(run_rec: Any) -> dict[str, Any]:
    """Serialize an inspection run record with flattened summary fields for frontend tables."""
    d = run_rec.to_dict()
    summ = d.get("summary") or {}
    x_ax = summ.get("x_axis") or {}
    y_ax = summ.get("y_axis") or {}

    # Determine execution mode
    mode = "LIVE" if summ.get("session_mode") == "continuous_monitoring" else "BATCH"

    d["mode"] = mode
    d["source_type"] = summ.get("source_type") or ("video_file" if mode == "BATCH" else "browser_webcam")
    d["fps"] = float(d.get("measured_fps") or summ.get("fps_used") or 30.0)
    d["x_frequency_hz"] = x_ax.get("dominant_frequency_hz")
    d["y_frequency_hz"] = y_ax.get("dominant_frequency_hz")
    d["x_dominant_frequency_hz"] = x_ax.get("dominant_frequency_hz")
    d["y_dominant_frequency_hz"] = y_ax.get("dominant_frequency_hz")
    d["x_rms_px"] = x_ax.get("rms_displacement_px")
    d["y_rms_px"] = y_ax.get("rms_displacement_px")
    d["x_signal_quality"] = x_ax.get("signal_quality")
    d["y_signal_quality"] = y_ax.get("signal_quality")
    return sanitize_json(d)


@router.get("")
def list_runs(
    asset_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    storage: StorageManager = Depends(get_storage),
) -> list[dict[str, Any]]:
    """List inspection runs with filtering."""
    runs = storage.list_inspection_runs(
        asset_id=asset_id, limit=limit, offset=offset
    )
    if status is not None:
        runs = [r for r in runs if r.status == status]
    return [_serialize_run_record(r) for r in runs]


@router.get("/{run_id}")
def get_run(
    run_id: str, storage: StorageManager = Depends(get_storage)
) -> dict[str, Any]:
    """Fetch run metadata, summary, review events, and numerical arrays."""
    run = storage.get_inspection_run(run_id)
    if not run:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found.",
        )

    arrays_dict = None
    if run.npz_rel_path:
        try:
            arrs = storage.load_run_arrays(run.npz_rel_path)
            arrays_dict = {
                "timestamps_s": arrs.timestamps_s,
                "times_s": arrs.timestamps_s,
                "relative_dx_px": arrs.relative_dx_px,
                "rel_dx_px": arrs.relative_dx_px,
                "relative_dy_px": arrs.relative_dy_px,
                "rel_dy_px": arrs.relative_dy_px,
                "target_dx_px": arrs.target_dx_px,
                "target_dy_px": arrs.target_dy_px,
                "anchor_dx_px": arrs.anchor_dx_px,
                "anchor_dy_px": arrs.anchor_dy_px,
                "x_frequencies_hz": arrs.x_frequencies_hz,
                "x_psd_px2_per_hz": arrs.x_psd_px2_per_hz,
                "y_frequencies_hz": arrs.y_frequencies_hz,
                "y_psd_px2_per_hz": arrs.y_psd_px2_per_hz,
            }
        except Exception:
            pass

    reviews = storage.list_review_events_for_run(run_id)
    result = _serialize_run_record(run)
    result["review_events"] = [r.to_dict() for r in reviews]
    result["arrays"] = arrays_dict
    if run.summary:
        result["x_metrics"] = run.summary.get("x_axis")
        result["y_metrics"] = run.summary.get("y_axis")
        if arrays_dict and result["x_metrics"] and "x_frequencies_hz" in arrays_dict:
            result["x_metrics"]["frequencies"] = arrays_dict.get("x_frequencies_hz")
            result["x_metrics"]["psd"] = arrays_dict.get("x_psd_px2_per_hz")
        if arrays_dict and result["y_metrics"] and "y_frequencies_hz" in arrays_dict:
            result["y_metrics"]["frequencies"] = arrays_dict.get("y_frequencies_hz")
            result["y_metrics"]["psd"] = arrays_dict.get("y_psd_px2_per_hz")
    return sanitize_json(result)
