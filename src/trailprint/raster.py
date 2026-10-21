"""Rasterise way geometries onto the model grid as boolean node masks."""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw

from .geo import ModelGrid
from .osm import Way


def rasterize_ways(
    ways: list[Way], grid: ModelGrid, width_px: float, fill_closed: bool = False
) -> np.ndarray:
    """Boolean mask of shape (ny, nx), south-up like the grid."""
    img = Image.new("L", (grid.nx, grid.ny), 0)
    draw = ImageDraw.Draw(img)
    width = max(1, int(round(width_px)))
    for way in ways:
        pts = [grid.lonlat_to_pixel(lon, lat) for lon, lat in way.coords]
        if fill_closed and way.closed:
            draw.polygon(pts, fill=255, outline=255)
            if width > 1:
                draw.line(pts, fill=255, width=width, joint="curve")
        else:
            draw.line(pts, fill=255, width=width, joint="curve")
            if width > 2:
                r = width / 2
                for x, y in (pts[0], pts[-1]):
                    draw.ellipse([x - r, y - r, x + r, y + r], fill=255)
    return np.asarray(img, dtype=np.uint8) > 0


def mm_to_px(mm: float, grid: ModelGrid) -> float:
    return mm / grid.mm_per_cell
