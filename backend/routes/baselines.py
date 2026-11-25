"""Statistical baseline management endpoints."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from backend.deps import get_storage
from backend.schemas import BaselineBuildRequest, sanitize_json
from phasesight.baseline import build_baseline
from phasesight.storage import StorageManager

router = APIRouter(prefix="/baselines", tags=["baselines"])


def _flatten_axis(axis_dict: dict[str, Any] | None) -> dict[str, Any] | None:
    if not axis_dict:
        return None
    res = dict(axis_dict)
    for feat in ("dominant_frequency_hz", "rms_displacement_px", "peak_to_median_db", "second_harmonic_ratio"):
        sub = axis_dict.get(feat)
        if isinstance(sub, dict):
            res[f"{feat}_median"] = sub.get("median")
            res[f"{feat}_mad"] = sub.get("mad_scaled")
    return res


@router.get("")
def list_baselines(
    asset_id: str | None = None, storage: StorageManager = Depends(get_storage)
) -> list[dict[str, Any]]:
    """List stored baselines, optionally filtered by asset."""
    if asset_id:
        baselines = storage.list_baselines_for_asset(asset_id)
    else:
        assets = storage.list_assets()
        baselines = []
        for a in assets:
            baselines.extend(storage.list_baselines_for_asset(a.asset_id))

    res_list = []
    for b in baselines:
        d = b.to_dict()
        rec = d.get("baseline_record") or {}
        d["x_baseline"] = _flatten_axis(rec.get("x_axis"))
        d["y_baseline"] = _flatten_axis(rec.get("y_axis"))
        d["run_ids"] = rec.get("baseline_run_ids", [])
        res_list.append(sanitize_json(d))

    return res_list


@router.post("/build", status_code=status.HTTP_201_CREATED)
def build_new_baseline(
    request: BaselineBuildRequest, storage: StorageManager = Depends(get_storage)
) -> dict[str, Any]:
    """Aggregate N >= 3 healthy inspection runs into an immutable statistical baseline."""
    asset = storage.get_asset(request.asset_id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{request.asset_id}' not found.",
        )

    runs: list[dict[str, Any]] = []
    for rid in request.run_ids:
        rec = storage.get_inspection_run(rid)
        if not rec:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Run '{rid}' not found.",
            )
        runs.append(rec.summary)

    try:
        baseline_record = build_baseline(
            runs=runs,
            asset_id=request.asset_id,
            require_valid_axes=request.require_valid_axes,
            notes=request.notes,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )

    stored = storage.create_baseline(
        asset_id=request.asset_id,
        baseline_record=baseline_record,
        notes=request.notes,
    )
    result = stored.to_dict()
    result["x_baseline"] = _flatten_axis(baseline_record.x_axis.to_dict())
    result["y_baseline"] = _flatten_axis(baseline_record.y_axis.to_dict())
    result["run_ids"] = baseline_record.baseline_run_ids
    return sanitize_json(result)
