"""Curated video presets for PhaseSight backend."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.schemas import PresetResponse

CURATED_PRESETS: dict[str, dict[str, Any]] = {
    "portable_baseline": {
        "preset_id": "portable_baseline",
        "label": "Portable Rig — Healthy Baseline (60 FPS)",
        "category": "synthetic_validation",
        "rel_path": "data/portable/baseline.mp4",
        "recommended_fps_override": None,
        "recommended_playback_rate": 1.0,
        "default_target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "default_anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
        "description": "Synthetic 8.5 Hz rotor benchmark with subpixel translation and natural lighting variations.",
    },
    "portable_changed": {
        "preset_id": "portable_changed",
        "label": "Portable Rig — Changed Condition (60 FPS)",
        "category": "synthetic_validation",
        "rel_path": "data/portable/changed.mp4",
        "recommended_fps_override": None,
        "recommended_playback_rate": 1.0,
        "default_target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "default_anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
        "description": "Synthetic altered vibration state with increased amplitude and harmonic emergence.",
    },
    "portable_camera_only": {
        "preset_id": "portable_camera_only",
        "label": "Portable Rig — Environmental Camera Motion Only (60 FPS)",
        "category": "synthetic_validation",
        "rel_path": "data/portable/camera_only.mp4",
        "recommended_fps_override": None,
        "recommended_playback_rate": 1.0,
        "default_target_roi": {"x": 360, "y": 110, "width": 160, "height": 160},
        "default_anchor_roi": {"x": 60, "y": 100, "width": 160, "height": 160},
        "description": "Environmental shake test clip to verify relative anchor cancellation.",
    },
    "rotor_1000rpm_unb1": {
        "preset_id": "rotor_1000rpm_unb1",
        "label": "Mendeley Rotor Benchmark — 1000 RPM (500 FPS)",
        "category": "rotor_benchmark",
        "rel_path": "data/rotor_dataset/Raw videos/1000rpm-Unb1.avi",
        "recommended_fps_override": 500.0,
        "recommended_playback_rate": 0.08,
        "default_target_roi": {"x": 850, "y": 460, "width": 64, "height": 64},
        "default_anchor_roi": {"x": 600, "y": 560, "width": 64, "height": 64},
        "description": "High-speed rotor test at 1000 RPM (fundamental 16.67 Hz). Note: AVI container advertises 100 FPS vs 500 FPS physical capture.",
    },
    "rotor_2000rpm_unb1": {
        "preset_id": "rotor_2000rpm_unb1",
        "label": "Mendeley Rotor Benchmark — 2000 RPM (500 FPS)",
        "category": "rotor_benchmark",
        "rel_path": "data/rotor_dataset/Raw videos/2000rpm-Unb1.avi",
        "recommended_fps_override": 500.0,
        "recommended_playback_rate": 0.08,
        "default_target_roi": {"x": 850, "y": 460, "width": 64, "height": 64},
        "default_anchor_roi": {"x": 600, "y": 560, "width": 64, "height": 64},
        "description": "High-speed rotor test at 2000 RPM (fundamental 33.33 Hz). Note: AVI container advertises 100 FPS vs 500 FPS physical capture.",
    },
    "rotor_3000rpm_unb1": {
        "preset_id": "rotor_3000rpm_unb1",
        "label": "Mendeley Rotor Benchmark — 3000 RPM (500 FPS)",
        "category": "rotor_benchmark",
        "rel_path": "data/rotor_dataset/Raw videos/3000rpm-Unb1.avi",
        "recommended_fps_override": 500.0,
        "recommended_playback_rate": 0.08,
        "default_target_roi": {"x": 850, "y": 460, "width": 64, "height": 64},
        "default_anchor_roi": {"x": 600, "y": 560, "width": 64, "height": 64},
        "description": "High-speed rotor test at 3000 RPM (fundamental 50.00 Hz). Note: AVI container advertises 100 FPS vs 500 FPS physical capture.",
    },
}


def get_preset(preset_id: str, base_dir: Path | None = None) -> dict[str, Any] | None:
    """Retrieve preset config by preset_id."""
    raw = CURATED_PRESETS.get(preset_id)
    if not raw:
        return None
    root = base_dir or Path.cwd()
    data = dict(raw)
    data["exists"] = (root / data["rel_path"]).is_file()
    return data


def list_presets(base_dir: Path | None = None) -> list[PresetResponse]:
    """List all curated presets with live existence checks."""
    root = base_dir or Path.cwd()
    results: list[PresetResponse] = []
    for raw in CURATED_PRESETS.values():
        p_path = root / raw["rel_path"]
        results.append(
            PresetResponse(
                preset_id=raw["preset_id"],
                label=raw["label"],
                category=raw["category"],
                rel_path=raw["rel_path"],
                exists=p_path.is_file(),
                recommended_fps_override=raw["recommended_fps_override"],
                recommended_playback_rate=raw["recommended_playback_rate"],
                default_target_roi=raw["default_target_roi"],
                default_anchor_roi=raw["default_anchor_roi"],
                description=raw["description"],
            )
        )
    return results


def resolve_video_path(
    preset_id: str | None,
    upload_id: str | None,
    uploads_dir: Path,
    base_dir: Path | None = None,
) -> Path:
    """Resolve an allowlisted preset path or uploaded video file safely."""
    root = base_dir or Path.cwd()
    clean_upload_id = (
        upload_id.strip()
        if upload_id and upload_id.strip() and upload_id.strip() != "null"
        else None
    )
    clean_preset_id = (
        preset_id.strip()
        if preset_id and preset_id.strip() and preset_id.strip() != "null"
        else None
    )

    # Prioritize uploaded video if upload_id is provided
    if clean_upload_id:
        matches = list(uploads_dir.glob(f"{clean_upload_id}.*"))
        if not matches:
            raise FileNotFoundError(f"Uploaded video '{clean_upload_id}' not found")
        return matches[0].resolve()

    if clean_preset_id:
        preset = get_preset(clean_preset_id, base_dir=root)
        if not preset:
            raise ValueError(f"Unknown preset_id '{clean_preset_id}'")
        resolved = (root / preset["rel_path"]).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"Preset file not found on disk: {resolved}")
        return resolved

    raise ValueError("Either preset_id or upload_id must be provided")
