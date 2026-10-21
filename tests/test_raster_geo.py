import numpy as np

from trailprint.config import BBox
from trailprint.geo import ModelGrid, lonlat_to_merc, merc_to_tile, tile_to_merc
from trailprint.osm import Way, build_query
from trailprint.raster import rasterize_ways


def test_tile_roundtrip():
    x, y = lonlat_to_merc(-121.5, 46.9)
    tx, ty = merc_to_tile(x, y, 12)
    x2, y2 = tile_to_merc(tx, ty, 12)
    assert abs(x - x2) < 1e-3 and abs(y - y2) < 1e-3


def test_grid_is_square_and_scaled():
    grid = ModelGrid.from_bbox(BBox(46.90, -121.52, 46.93, -121.47), 100.0, 0.5)
    assert grid.nx == 201
    assert abs(grid.width_mm - 100.0) < 1e-9
    # ~3.8 km east-west at 46.9N over 100 mm => ~38 m per mm
    assert 35 < grid.ground_m_per_mm < 42
    col, row = grid.lonlat_to_pixel(-121.52, 46.90)
    assert abs(col) < 1e-6 and abs(row) < 1e-6


def test_rasterize_line_and_polygon():
    bbox = BBox(46.90, -121.52, 46.93, -121.47)
    grid = ModelGrid.from_bbox(bbox, 50.0, 0.5)
    line = Way(1, [(-121.52, 46.90), (-121.47, 46.93)])
    mask = rasterize_ways([line], grid, width_px=3)
    assert mask[0, 0] and mask[-1, -1]
    assert 0 < mask.mean() < 0.1
    square = Way(
        2,
        [
            (-121.51, 46.905),
            (-121.48, 46.905),
            (-121.48, 46.925),
            (-121.51, 46.925),
            (-121.51, 46.905),
        ],
        tags={"area": "yes"},
    )
    filled = rasterize_ways([square], grid, width_px=1, fill_closed=True)
    outline = rasterize_ways([square], grid, width_px=1, fill_closed=False)
    assert filled.sum() > 5 * outline.sum()
    assert np.array_equal(filled | outline, filled)


def test_build_query_contains_selectors():
    q = build_query(BBox(1, 2, 3, 4), ['["aerialway"]', '["piste:type"="downhill"]'])
    assert 'way["aerialway"](1,2,3,4);' in q
    assert "out geom;" in q
