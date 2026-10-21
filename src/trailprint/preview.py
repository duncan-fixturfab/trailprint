"""Hillshade PNG preview of a build, with feature layers painted in their colours."""

from __future__ import annotations

import numpy as np
from PIL import Image


def _hex_to_rgb(color: str) -> np.ndarray:
    color = color.lstrip("#")
    return np.array([int(color[i : i + 2], 16) for i in (0, 2, 4)], dtype=np.float32)


def hillshade(z_mm: np.ndarray, cell_mm: float, azimuth_deg=315.0, altitude_deg=45.0) -> np.ndarray:
    dzdy, dzdx = np.gradient(z_mm, cell_mm)
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, dzdy)
    az = np.radians(360.0 - azimuth_deg + 90.0)
    alt = np.radians(altitude_deg)
    shade = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(shade, 0, 1)


def render_preview(
    z_mm: np.ndarray,
    cell_mm: float,
    layers: list[tuple[np.ndarray, str]],
    terrain_color: str = "#3f8f4f",
    max_width_px: int = 1400,
) -> Image.Image:
    shade = hillshade(z_mm, cell_mm)[..., None]
    rgb = np.broadcast_to(_hex_to_rgb(terrain_color), (*z_mm.shape, 3)).astype(np.float32)
    rgb = rgb * (0.35 + 0.65 * shade)
    for mask, color in layers:
        rgb[mask] = _hex_to_rgb(color) * (0.6 + 0.4 * shade[mask])
    img = Image.fromarray(np.clip(rgb, 0, 255).astype(np.uint8)[::-1])  # north up
    if img.width < max_width_px:
        scale = max_width_px / img.width
        img = img.resize((max_width_px, int(img.height * scale)), Image.NEAREST)
    return img
