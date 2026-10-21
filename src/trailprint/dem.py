"""Elevation data from the AWS Open Data 'Terrarium' tiles (no API key required).

Tiles: https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png
Elevation (m) = (R * 256 + G + B / 256) - 32768
Source blend is documented at https://github.com/tilezen/joerd/blob/master/docs/data-sources.md
(3DEP 10 m over the continental US, SRTM / others elsewhere). Max useful zoom is 15.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import requests
from PIL import Image
from scipy.ndimage import gaussian_filter, map_coordinates

from .config import BBox
from .geo import lonlat_to_merc, merc_to_tile, tile_resolution_m, tile_to_merc

TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
MAX_ZOOM = 15
MIN_ZOOM = 6
USER_AGENT = "trailprint/0.1 (+https://github.com/duncan-fixturfab/trailprint)"


@dataclass
class DEM:
    """A mercator-aligned elevation mosaic. Row 0 is the NORTH edge (image convention)."""

    data: np.ndarray  # float32 metres, shape (rows, cols)
    x0: float  # mercator x of the left edge
    y0: float  # mercator y of the top edge
    m_per_px: float  # mercator metres per pixel
    zoom: int

    def sample(self, xs: np.ndarray, ys: np.ndarray) -> np.ndarray:
        """Bilinear sample at mercator coordinates (any shape)."""
        cols = (np.asarray(xs) - self.x0) / self.m_per_px - 0.5
        rows = (self.y0 - np.asarray(ys)) / self.m_per_px - 0.5
        return map_coordinates(self.data, [rows, cols], order=1, mode="nearest")


def decode_terrarium(png_bytes: bytes) -> np.ndarray:
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    rgb = np.asarray(img, dtype=np.float32)
    return rgb[..., 0] * 256 + rgb[..., 1] + rgb[..., 2] / 256 - 32768


def choose_zoom(lat: float, target_m_per_px: float) -> int:
    """Smallest zoom whose ground resolution is at least as fine as `target_m_per_px`."""
    for zoom in range(MIN_ZOOM, MAX_ZOOM + 1):
        if tile_resolution_m(zoom, lat) <= target_m_per_px:
            return zoom
    return MAX_ZOOM


def fetch_tile(zoom: int, x: int, y: int, cache_dir: Path, session: requests.Session) -> np.ndarray:
    path = cache_dir / "terrarium" / str(zoom) / str(x) / f"{y}.png"
    if path.exists():
        return decode_terrarium(path.read_bytes())
    url = TERRARIUM_URL.format(z=zoom, x=x, y=y)
    resp = session.get(url, timeout=60, headers={"User-Agent": USER_AGENT})
    resp.raise_for_status()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(resp.content)
    return decode_terrarium(resp.content)


def fetch_dem(
    bbox: BBox, zoom: int, cache_dir: Path, session: requests.Session | None = None
) -> DEM:
    """Mosaic every tile covering `bbox` at `zoom` (plus one tile of margin for resampling)."""
    session = session or requests.Session()
    x_min, y_min = lonlat_to_merc(bbox.west, bbox.south)
    x_max, y_max = lonlat_to_merc(bbox.east, bbox.north)
    tx0, ty0 = merc_to_tile(x_min, y_max, zoom)  # top-left
    tx1, ty1 = merc_to_tile(x_max, y_min, zoom)  # bottom-right
    n = 2**zoom
    tx_lo, tx_hi = max(0, math.floor(tx0) - 1), min(n - 1, math.floor(tx1) + 1)
    ty_lo, ty_hi = max(0, math.floor(ty0) - 1), min(n - 1, math.floor(ty1) + 1)
    cols = (tx_hi - tx_lo + 1) * 256
    rows = (ty_hi - ty_lo + 1) * 256
    data = np.empty((rows, cols), dtype=np.float32)
    for ty in range(ty_lo, ty_hi + 1):
        for tx in range(tx_lo, tx_hi + 1):
            tile = fetch_tile(zoom, tx, ty, cache_dir, session)
            r, c = (ty - ty_lo) * 256, (tx - tx_lo) * 256
            data[r : r + 256, c : c + 256] = tile
    left, top = tile_to_merc(tx_lo, ty_lo, zoom)
    m_per_px = 2 * math.pi * 6378137.0 / 256 / n
    return DEM(data=data, x0=left, y0=top, m_per_px=m_per_px, zoom=zoom)


def smooth(z: np.ndarray, sigma_px: float) -> np.ndarray:
    if sigma_px <= 0:
        return z
    return gaussian_filter(z, sigma=sigma_px, mode="nearest")
