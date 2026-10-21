from pathlib import Path

import numpy as np
import pytest

from trailprint.config import AreaConfig, BBox, LabelSpec, LayerSpec, ModelSpec
from trailprint.dem import DEM
from trailprint.geo import lonlat_to_merc
from trailprint.osm import Way

AREAS = Path(__file__).resolve().parents[1] / "areas"


@pytest.fixture
def bbox() -> BBox:
    return BBox(south=46.90, west=-121.52, north=46.93, east=-121.47)


@pytest.fixture
def synthetic_dem(bbox: BBox) -> DEM:
    """A smooth hill covering the bbox with margin, 30 m pixels."""
    x0, y0 = lonlat_to_merc(bbox.west - 0.02, bbox.north + 0.02)
    x1, y1 = lonlat_to_merc(bbox.east + 0.02, bbox.south - 0.02)
    mpp = 30.0
    cols, rows = int((x1 - x0) / mpp) + 1, int((y0 - y1) / mpp) + 1
    cc, rr = np.meshgrid(np.arange(cols), np.arange(rows))
    z = 1200 + 800 * np.exp(
        -(((cc - cols / 2) / (cols / 4)) ** 2 + ((rr - rows / 2) / (rows / 4)) ** 2)
    )
    return DEM(data=z.astype(np.float32), x0=x0, y0=y0, m_per_px=mpp, zoom=13)


@pytest.fixture
def area(bbox: BBox) -> AreaConfig:
    return AreaConfig(
        name="Test Hill",
        slug="test-hill",
        bbox=bbox,
        model=ModelSpec(width_mm=40, resolution_mm=0.5, base_mm=4, z_scale=1.0, mode="parts"),
        label=LabelSpec(text="Test Hill", height_mm=2.5),
        layers=[
            LayerSpec(name="runs", select=['["piste:type"="downhill"]'], width_mm=1.2),
            LayerSpec(name="lifts", select=['["aerialway"]'], width_mm=0.8, raise_mm=0.8),
        ],
    )


@pytest.fixture
def fake_ways(bbox: BBox):
    """Return a fetch_ways stand-in that draws one diagonal way per selector."""

    def fetch(bbox_, selectors, cache_dir, **kw):
        s, w, n, e = bbox_.south, bbox_.west, bbox_.north, bbox_.east
        ways = []
        for k, sel in enumerate(selectors):
            frac = 0.3 + 0.2 * k
            ways.append(
                Way(
                    id=k,
                    coords=[
                        (w + (e - w) * frac, s + (n - s) * 0.1),
                        (w + (e - w) * (1 - frac), n - (n - s) * 0.1),
                    ],
                    tags={"sel": sel},
                )
            )
        return ways

    return fetch
