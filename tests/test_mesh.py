import numpy as np
import pytest

from trailprint.mesh import heightfield_solid


def _check_closed(mesh):
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0


def test_flat_slab_volume():
    top = np.full((6, 9), 3.0)
    mesh = heightfield_solid(top, 0.0, None, 0.5)
    _check_closed(mesh)
    assert mesh.volume == pytest.approx(5 * 8 * 0.25 * 3.0)
    assert mesh.bounds[1][0] == pytest.approx(8 * 0.5)


def test_random_terrain_is_closed():
    rng = np.random.default_rng(0)
    top = 5 + rng.random((40, 60)) * 3
    mesh = heightfield_solid(top, 0.0, None, 0.4)
    _check_closed(mesh)


def test_mask_with_hole_and_islands():
    top = np.full((30, 30), 2.0)
    mask = np.zeros_like(top, dtype=bool)
    mask[2:20, 2:20] = True
    mask[8:12, 8:12] = False  # hole
    mask[23:28, 23:28] = True  # island
    mesh = heightfield_solid(top, 1.0, mask, 1.0)
    _check_closed(mesh)
    n_cells = (17 * 17) - (5 * 5) + (4 * 4)
    assert mesh.volume == pytest.approx(n_cells * 1.0)


def test_varying_bottom_and_top():
    rng = np.random.default_rng(1)
    base = rng.random((20, 25)) * 2 + 5
    mask = rng.random((20, 25)) > 0.4
    mesh = heightfield_solid(base + 0.3, base - 0.5, mask, 0.4)
    if mesh.is_empty:
        pytest.skip("random mask produced no active cell")
    _check_closed(mesh)


def test_empty_mask_gives_empty_mesh():
    mesh = heightfield_solid(np.ones((5, 5)), 0.0, np.zeros((5, 5), bool), 1.0)
    assert mesh.is_empty
