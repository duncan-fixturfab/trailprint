"""Embossed text label on one side face of the base."""

from __future__ import annotations

import numpy as np
import trimesh
from PIL import Image, ImageDraw, ImageFont

from .config import LabelSpec
from .mesh import heightfield_solid

TEXT_CELL_MM = 0.1


def _load_font(px: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.load_default(size=px)  # Pillow >= 10.1 bundles a scalable font
    except TypeError:  # pragma: no cover - very old Pillow
        return ImageFont.load_default()


def text_mask(text: str, cap_height_mm: float, cell_mm: float = TEXT_CELL_MM) -> np.ndarray:
    """Boolean mask of the rendered text, rows = +z (bottom row is the baseline side)."""
    px = max(8, int(round(cap_height_mm / cell_mm * 1.35)))  # font size ~1.35x cap height
    font = _load_font(px)
    left, top, right, bottom = font.getbbox(text)
    w, h = right - left + 4, bottom - top + 4
    img = Image.new("L", (w, h), 0)
    ImageDraw.Draw(img).text((2 - left, 2 - top), text, fill=255, font=font)
    mask = np.asarray(img) > 128
    return mask[::-1]  # image row 0 is the top; we want row 0 at the bottom (z = 0)


def label_solid(
    spec: LabelSpec,
    footprint_mm: tuple[float, float],
    base_mm: float,
    embed_mm: float = 0.4,
) -> trimesh.Trimesh:
    """Text standing proud of the chosen side face, vertically centred on the base slab."""
    if not spec.text:
        return trimesh.Trimesh()
    width_mm, depth_mm = footprint_mm
    face_len = width_mm if spec.side in ("south", "north") else depth_mm
    mask = text_mask(spec.text, spec.height_mm)
    cell = TEXT_CELL_MM
    text_w = mask.shape[1] * cell
    text_h = mask.shape[0] * cell
    avail = face_len - 2 * spec.margin_mm
    if text_w > avail:  # shrink to fit
        scale = avail / text_w
        mask = text_mask(spec.text, spec.height_mm * scale)
        text_w = mask.shape[1] * cell
        text_h = mask.shape[0] * cell
    # Letters occupy z in [z0, z0 + text_h], centred on the base slab.
    z0 = max(0.3, (base_mm - text_h) / 2)
    top = np.full(mask.shape, spec.depth_mm)
    local = heightfield_solid(top, -embed_mm, mask, cell)
    if local.is_empty:
        return local
    # Local frame: x along the face, y up (z), z out of the face. Map to the model frame.
    x_off = spec.margin_mm
    if spec.side == "south":  # face at y = 0, outward = -y
        m = np.array([[1, 0, 0, x_off], [0, 0, -1, 0], [0, 1, 0, z0], [0, 0, 0, 1]], float)
    elif spec.side == "north":  # face at y = depth, outward = +y, text reads left->right from +y
        m = np.array(
            [[-1, 0, 0, width_mm - x_off], [0, 0, 1, depth_mm], [0, 1, 0, z0], [0, 0, 0, 1]], float
        )
    elif spec.side == "east":  # face at x = width, outward = +x
        m = np.array([[0, 0, 1, width_mm], [1, 0, 0, x_off], [0, 1, 0, z0], [0, 0, 0, 1]], float)
    elif spec.side == "west":  # face at x = 0, outward = -x
        m = np.array(
            [[0, 0, -1, 0], [-1, 0, 0, depth_mm - x_off], [0, 1, 0, z0], [0, 0, 0, 1]], float
        )
    else:
        raise ValueError(f"label.side must be south|north|east|west, got {spec.side!r}")
    local.apply_transform(m)
    if np.linalg.det(m[:3, :3]) < 0:
        local.invert()
    return local
