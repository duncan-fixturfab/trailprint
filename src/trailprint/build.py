"""Orchestrate: config -> DEM -> masks -> meshes -> files."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from . import dem as dem_mod
from . import osm as osm_mod
from .config import AreaConfig
from .geo import ModelGrid
from .label import label_solid
from .mesh import export_stl, heightfield_solid
from .preview import render_preview
from .raster import mm_to_px, rasterize_ways

log = logging.getLogger(__name__)

DEFAULT_CACHE = Path.home() / ".cache" / "trailprint"


@dataclass
class BuildResult:
    out_dir: Path
    files: dict[str, Path] = field(default_factory=dict)
    stats: dict = field(default_factory=dict)


def plan(area: AreaConfig) -> dict:
    """Dry-run numbers: grid size, zoom level, ground scale."""
    grid = ModelGrid.from_bbox(area.bbox, area.model.width_mm, area.model.resolution_mm)
    target_m_per_px = grid.ground_m_per_mm * grid.mm_per_cell
    zoom = dem_mod.choose_zoom(grid.lat_center, target_m_per_px)
    return {
        "grid": [grid.ny, grid.nx],
        "footprint_mm": [round(grid.width_mm, 1), round(grid.depth_mm, 1)],
        "ground_m_per_mm": round(grid.ground_m_per_mm, 1),
        "ground_extent_m": [
            round(grid.width_mm * grid.ground_m_per_mm),
            round(grid.depth_mm * grid.ground_m_per_mm),
        ],
        "dem_zoom": zoom,
        "dem_m_per_px": round(dem_mod.tile_resolution_m(zoom, grid.lat_center), 1),
        "cell_ground_m": round(target_m_per_px, 1),
    }


def build(
    area: AreaConfig,
    out_dir: Path,
    cache_dir: Path = DEFAULT_CACHE,
    mode: str | None = None,
    preview_only: bool = False,
) -> BuildResult:
    mode = mode or area.model.mode
    spec = area.model
    out_dir = Path(out_dir) / area.slug
    out_dir.mkdir(parents=True, exist_ok=True)
    result = BuildResult(out_dir=out_dir)

    grid = ModelGrid.from_bbox(area.bbox, spec.width_mm, spec.resolution_mm)
    info = plan(area)
    log.info(
        "grid %dx%d nodes, footprint %.0fx%.0f mm, 1 mm = %.0f m, DEM zoom %d",
        grid.nx,
        grid.ny,
        grid.width_mm,
        grid.depth_mm,
        grid.ground_m_per_mm,
        info["dem_zoom"],
    )

    # --- elevation --------------------------------------------------------------------
    dem = dem_mod.fetch_dem(area.bbox, info["dem_zoom"], cache_dir)
    xs, ys = grid.node_coords()
    elev = dem.sample(xs, ys).astype(np.float64)
    if spec.smooth_mm > 0:
        elev = dem_mod.smooth(elev, spec.smooth_mm / grid.mm_per_cell)
    elev_min, elev_max = float(elev.min()), float(elev.max())
    z = spec.base_mm + (elev - elev_min) * spec.z_scale / grid.ground_m_per_mm
    info.update(
        {
            "elevation_m": [round(elev_min), round(elev_max)],
            "relief_mm": round(float(z.max() - spec.base_mm), 1),
            "mode": mode,
        }
    )

    # --- features ---------------------------------------------------------------------
    masks: list[tuple[str, np.ndarray]] = []
    layer_stats = {}
    for layer in area.enabled_layers:
        ways = osm_mod.fetch_ways(area.bbox, layer.select, cache_dir)
        width_px = mm_to_px(layer.width_mm, grid)
        mask = rasterize_ways(ways, grid, width_px, fill_closed=layer.fill_closed)
        masks.append((layer.name, mask))
        layer_stats[layer.name] = {"ways": len(ways), "nodes": int(mask.sum())}
        log.info("layer %-18s %4d ways, %7d grid nodes", layer.name, len(ways), int(mask.sum()))
    info["layers"] = layer_stats

    # --- preview ----------------------------------------------------------------------
    layer_by_name = {layer.name: layer for layer in area.layers}
    preview = render_preview(
        z, grid.mm_per_cell, [(m, layer_by_name[n].color) for n, m in masks], area.terrain_color
    )
    preview_path = out_dir / f"{area.slug}-preview.png"
    preview.save(preview_path)
    result.files["preview"] = preview_path
    if preview_only:
        result.stats = info
        _write_stats(out_dir, area, info)
        return result

    # --- meshes -----------------------------------------------------------------------
    parts: dict[str, trimesh.Trimesh] = {}
    terrain_top = z.copy()
    if mode in ("emboss", "engrave"):
        sign = 1.0 if mode == "emboss" else -1.0
        for name, mask in masks:
            terrain_top[mask] = z[mask] + sign * layer_by_name[name].relief_mm
        terrain_top = np.maximum(terrain_top, 0.5)
    terrain = heightfield_solid(terrain_top, 0.0, None, grid.mm_per_cell)
    parts["terrain"] = terrain

    if mode == "parts":
        for name, mask in masks:
            layer = layer_by_name[name]
            top = z + layer.raise_mm
            bottom = np.maximum(z - layer.embed_mm, 0.2)
            solid = heightfield_solid(top, bottom, mask, grid.mm_per_cell)
            if not solid.is_empty:
                parts[name] = solid

    label = label_solid(area.label, (grid.width_mm, grid.depth_mm), spec.base_mm)
    if not label.is_empty:
        parts["label"] = label

    for name, mesh in parts.items():
        path = out_dir / f"{area.slug}-{name}.stl"
        export_stl(mesh, path)
        result.files[name] = path
        info.setdefault("meshes", {})[name] = {
            "faces": int(len(mesh.faces)),
            "watertight": bool(mesh.is_watertight),
        }

    # One multi-part 3MF for slicers that keep parts (Bambu Studio, OrcaSlicer, PrusaSlicer).
    try:
        scene = trimesh.Scene()
        for name, mesh in parts.items():
            scene.add_geometry(mesh, node_name=name, geom_name=name)
        path = out_dir / f"{area.slug}.3mf"
        scene.export(str(path))
        result.files["3mf"] = path
    except Exception as exc:  # pragma: no cover - optional convenience output
        log.warning("3MF export skipped: %s", exc)

    result.stats = info
    _write_stats(out_dir, area, info)
    return result


def _write_stats(out_dir: Path, area: AreaConfig, info: dict) -> None:
    (out_dir / f"{area.slug}-stats.json").write_text(
        json.dumps({"name": area.name, "slug": area.slug, **info}, indent=2), encoding="utf-8"
    )
