"""Watertight solids from heightfields.

`heightfield_solid` turns a top surface, a bottom surface and a node mask into a closed
triangle mesh: top faces, bottom faces, and vertical walls wherever an active cell borders an
inactive cell or the grid edge. Arbitrary masks (holes, islands) are fine, which is what lets
us build the terrain, every feature overlay and the embossed label with one routine.
"""

from __future__ import annotations

import numpy as np
import trimesh


def _cell_active(mask: np.ndarray) -> np.ndarray:
    """A cell is active when all four corner nodes are in the mask."""
    return _resolve_checkerboards(mask[:-1, :-1] & mask[1:, :-1] & mask[:-1, 1:] & mask[1:, 1:])


def _resolve_checkerboards(active: np.ndarray, max_iter: int = 20) -> np.ndarray:
    """Fill 2x2 checkerboard patterns so no two cells touch only at a corner.

    Two active (or two inactive) cells meeting at a single node would give the vertical edge
    at that node four wall faces, which is non-manifold. Filling the 2x2 block is the smallest
    change that keeps the solid watertight.
    """
    active = active.copy()
    for _ in range(max_iter):
        a, b, c, d = active[:-1, :-1], active[:-1, 1:], active[1:, :-1], active[1:, 1:]
        checker = (a == d) & (b == c) & (a != b)
        if not checker.any():
            break
        ci, cj = np.nonzero(checker)
        for di, dj in ((0, 0), (0, 1), (1, 0), (1, 1)):
            active[ci + di, cj + dj] = True
    return active


def heightfield_solid(
    top: np.ndarray,
    bottom: np.ndarray | float,
    mask: np.ndarray | None,
    cell_mm: float,
    origin_mm: tuple[float, float] = (0.0, 0.0),
) -> trimesh.Trimesh:
    """Closed solid between `bottom` and `top` over the active region of `mask`.

    Arrays are (ny, nx), indexed [i, j] with x = origin_x + j*cell_mm, y = origin_y + i*cell_mm.
    """
    top = np.asarray(top, dtype=np.float64)
    ny, nx = top.shape
    bottom = np.broadcast_to(np.asarray(bottom, dtype=np.float64), top.shape)
    mask = np.ones(top.shape, dtype=bool) if mask is None else np.asarray(mask, dtype=bool)
    if bottom.shape != top.shape or mask.shape != top.shape:
        raise ValueError("top, bottom and mask must share a shape")

    active = _cell_active(mask)
    if not active.any():
        return trimesh.Trimesh()

    xs = origin_mm[0] + np.arange(nx) * cell_mm
    ys = origin_mm[1] + np.arange(ny) * cell_mm
    gx, gy = np.meshgrid(xs, ys)
    n_nodes = nx * ny
    verts = np.concatenate(
        [
            np.column_stack([gx.ravel(), gy.ravel(), top.ravel()]),
            np.column_stack([gx.ravel(), gy.ravel(), bottom.ravel()]),
        ]
    )

    def node(i: np.ndarray, j: np.ndarray) -> np.ndarray:
        return i * nx + j

    ci, cj = np.nonzero(active)
    v00, v01, v10, v11 = node(ci, cj), node(ci, cj + 1), node(ci + 1, cj), node(ci + 1, cj + 1)
    # Top: counter-clockwise seen from +z. Bottom: reversed.
    top_faces = np.concatenate([np.column_stack([v00, v01, v11]), np.column_stack([v00, v11, v10])])
    bottom_faces = np.concatenate(
        [
            np.column_stack([v00 + n_nodes, v11 + n_nodes, v01 + n_nodes]),
            np.column_stack([v00 + n_nodes, v10 + n_nodes, v11 + n_nodes]),
        ]
    )

    # Walls: walk each active cell's edges counter-clockwise (interior on the left) and emit a
    # wall wherever the neighbour across that edge is inactive. For an edge A->B with the
    # interior on the left, faces (bA, bB, tB), (bA, tB, tA) have an outward normal.
    padded = np.pad(active, 1, constant_values=False)
    south_open = active & ~padded[:-2, 1:-1]
    east_open = active & ~padded[1:-1, 2:]
    north_open = active & ~padded[2:, 1:-1]
    west_open = active & ~padded[1:-1, :-2]

    edges = []
    for open_mask, (ai, aj, bi, bj) in (
        (south_open, (0, 0, 0, 1)),
        (east_open, (0, 1, 1, 1)),
        (north_open, (1, 1, 1, 0)),
        (west_open, (1, 0, 0, 0)),
    ):
        ei, ej = np.nonzero(open_mask)
        if ei.size:
            edges.append((node(ei + ai, ej + aj), node(ei + bi, ej + bj)))
    wall_faces = []
    for a, b in edges:
        ta, tb, ba, bb = a, b, a + n_nodes, b + n_nodes
        wall_faces.append(np.column_stack([ba, bb, tb]))
        wall_faces.append(np.column_stack([ba, tb, ta]))

    faces = np.concatenate([top_faces, bottom_faces, *wall_faces])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=False)
    mesh.remove_unreferenced_vertices()
    return mesh


def export_stl(mesh: trimesh.Trimesh, path) -> None:
    mesh.export(str(path), file_type="stl")
