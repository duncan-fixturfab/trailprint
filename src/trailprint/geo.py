"""Web Mercator helpers and the model grid.

Everything is done in EPSG:3857 (Web Mercator). Mercator is conformal, so shapes are
locally correct; only the overall scale differs from ground truth by cos(latitude), which we
account for when converting elevations to model millimetres.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .config import BBox

R = 6378137.0
MAX_MERC = math.pi * R


def lonlat_to_merc(lon: float, lat: float) -> tuple[float, float]:
    x = math.radians(lon) * R
    y = R * math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


def merc_to_tile(x: float, y: float, zoom: int) -> tuple[float, float]:
    """Fractional XYZ tile coordinates (col, row) of a mercator point at `zoom`."""
    n = 2**zoom
    return (x + MAX_MERC) / (2 * MAX_MERC) * n, (MAX_MERC - y) / (2 * MAX_MERC) * n


def tile_to_merc(tx: float, ty: float, zoom: int) -> tuple[float, float]:
    n = 2**zoom
    return tx / n * 2 * MAX_MERC - MAX_MERC, MAX_MERC - ty / n * 2 * MAX_MERC


def tile_resolution_m(zoom: int, lat: float) -> float:
    """Ground metres per pixel of a 256px tile at `zoom`, at latitude `lat`."""
    return 2 * MAX_MERC / 256 / 2**zoom * math.cos(math.radians(lat))


@dataclass
class ModelGrid:
    """A regular grid of nodes over the bbox.

    Node (i, j) sits at mercator (x_min + j*cell_m, y_min + i*cell_m); row 0 is the SOUTH
    edge, so arrays indexed [i, j] are 'south-up'. Flip vertically for a north-up image.
    """

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    nx: int
    ny: int
    cell_m: float  # mercator metres per cell
    mm_per_cell: float  # model millimetres per cell
    lat_center: float

    @classmethod
    def from_bbox(cls, bbox: BBox, width_mm: float, resolution_mm: float) -> ModelGrid:
        x_min, y_min = lonlat_to_merc(bbox.west, bbox.south)
        x_max, y_max = lonlat_to_merc(bbox.east, bbox.north)
        nx = max(2, int(round(width_mm / resolution_mm)) + 1)
        cell_m = (x_max - x_min) / (nx - 1)
        ny = max(2, int(round((y_max - y_min) / cell_m)) + 1)
        # Re-derive y_max so cells are exactly square.
        y_max = y_min + (ny - 1) * cell_m
        return cls(
            x_min=x_min,
            y_min=y_min,
            x_max=x_max,
            y_max=y_max,
            nx=nx,
            ny=ny,
            cell_m=cell_m,
            mm_per_cell=resolution_mm,
            lat_center=bbox.lat_center,
        )

    @property
    def width_mm(self) -> float:
        return (self.nx - 1) * self.mm_per_cell

    @property
    def depth_mm(self) -> float:
        return (self.ny - 1) * self.mm_per_cell

    @property
    def ground_m_per_mm(self) -> float:
        """True ground metres represented by one model millimetre."""
        return self.cell_m * math.cos(math.radians(self.lat_center)) / self.mm_per_cell

    def node_coords(self) -> tuple[np.ndarray, np.ndarray]:
        """Mercator (xs, ys) arrays of shape (ny, nx)."""
        xs = self.x_min + np.arange(self.nx) * self.cell_m
        ys = self.y_min + np.arange(self.ny) * self.cell_m
        return np.meshgrid(xs, ys)

    def lonlat_to_pixel(self, lon: float, lat: float) -> tuple[float, float]:
        """(col, row) in node units; row grows northward."""
        x, y = lonlat_to_merc(lon, lat)
        return (x - self.x_min) / self.cell_m, (y - self.y_min) / self.cell_m
