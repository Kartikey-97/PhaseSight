"""Asset management endpoints."""

from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, status

from backend.deps import get_storage
from backend.schemas import AssetCreateRequest, AssetResponse
from phasesight.storage import StorageManager
from phasesight.tracker import ROI

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=list[AssetResponse])
def list_assets(storage: StorageManager = Depends(get_storage)) -> list[AssetResponse]:
    """List all registered assets."""
    assets = storage.list_assets()
    responses: list[AssetResponse] = []
    for a in assets:
        baseline = storage.get_latest_baseline_for_asset(a.asset_id)
        runs = storage.list_inspection_runs(asset_id=a.asset_id, limit=1)
        # Count total runs for this asset
        run_count = len(storage.list_inspection_runs(asset_id=a.asset_id, limit=1000))
        responses.append(
            AssetResponse(
                asset_id=a.asset_id,
                name=a.name,
                description=a.description,
                nominal_speed_rpm=a.nominal_speed_rpm,
                target_roi=a.target_roi,
                anchor_roi=a.anchor_roi,
                expected_fps=a.expected_fps,
                scale_calibration=a.scale_calibration,
                created_at=a.created_at,
                updated_at=a.updated_at,
                active_baseline=baseline.to_dict() if baseline else None,
                run_count=run_count,
            )
        )
    return responses


@router.post("", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def create_asset(
    request: AssetCreateRequest, storage: StorageManager = Depends(get_storage)
) -> AssetResponse:
    """Create a new machine asset."""
    target_roi = ROI(
        x=request.target_roi.x,
        y=request.target_roi.y,
        width=request.target_roi.width,
        height=request.target_roi.height,
    )
    anchor_roi = ROI(
        x=request.anchor_roi.x,
        y=request.anchor_roi.y,
        width=request.anchor_roi.width,
        height=request.anchor_roi.height,
    )
    try:
        rec = storage.create_asset(
            name=request.name,
            target_roi=target_roi,
            anchor_roi=anchor_roi,
            expected_fps=request.expected_fps,
            description=request.description,
            nominal_speed_rpm=request.nominal_speed_rpm,
            scale_calibration=request.scale_calibration,
            asset_id=request.asset_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return AssetResponse(
        asset_id=rec.asset_id,
        name=rec.name,
        description=rec.description,
        nominal_speed_rpm=rec.nominal_speed_rpm,
        target_roi=rec.target_roi,
        anchor_roi=rec.anchor_roi,
        expected_fps=rec.expected_fps,
        scale_calibration=rec.scale_calibration,
        created_at=rec.created_at,
        updated_at=rec.updated_at,
        active_baseline=None,
        run_count=0,
    )


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(
    asset_id: str, storage: StorageManager = Depends(get_storage)
) -> AssetResponse:
    """Fetch an asset by ID with its latest baseline and run count."""
    a = storage.get_asset(asset_id)
    if not a:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    baseline = storage.get_latest_baseline_for_asset(a.asset_id)
    run_count = len(storage.list_inspection_runs(asset_id=a.asset_id, limit=1000))
    return AssetResponse(
        asset_id=a.asset_id,
        name=a.name,
        description=a.description,
        nominal_speed_rpm=a.nominal_speed_rpm,
        target_roi=a.target_roi,
        anchor_roi=a.anchor_roi,
        expected_fps=a.expected_fps,
        scale_calibration=a.scale_calibration,
        created_at=a.created_at,
        updated_at=a.updated_at,
        active_baseline=baseline.to_dict() if baseline else None,
        run_count=run_count,
    )


@router.delete("/{asset_id}")
def delete_asset(
    asset_id: str, storage: StorageManager = Depends(get_storage)
) -> dict[str, Any]:
    """Delete asset and its cascaded baselines and runs."""
    deleted = storage.delete_asset(asset_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset '{asset_id}' not found.",
        )
    return {"status": "deleted", "asset_id": asset_id}
