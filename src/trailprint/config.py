"""Area configuration (YAML) -> dataclasses."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

MODES = ("parts", "emboss", "engrave", "plain")


@dataclass
class BBox:
    south: float
    west: float
    north: float
    east: float

    def __post_init__(self) -> None:
        if not (self.south < self.north and self.west < self.east):
            raise ValueError("bbox must satisfy south < north and west < east")

    @property
    def lat_center(self) -> float:
        return (self.south + self.north) / 2

    def overpass(self) -> str:
        return f"{self.south},{self.west},{self.north},{self.east}"


@dataclass
class ModelSpec:
    width_mm: float = 120.0  # east-west footprint
    resolution_mm: float = 0.4  # grid cell size on the printed model
    base_mm: float = 6.0  # thickness below the lowest terrain point
    z_scale: float = 1.0  # vertical exaggeration (1.0 = true scale)
    smooth_mm: float = 0.0  # gaussian smoothing radius applied to the heightmap, in model mm
    mode: str = "parts"  # parts | emboss | engrave | plain

    def __post_init__(self) -> None:
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, got {self.mode!r}")
        if self.width_mm <= 0 or self.resolution_mm <= 0 or self.base_mm <= 0:
            raise ValueError("width_mm, resolution_mm and base_mm must be positive")


@dataclass
class LabelSpec:
    text: str = ""  # empty string disables the label
    height_mm: float = 3.5  # cap height of the lettering
    depth_mm: float = 0.6  # how far the letters stand proud of the front face
    margin_mm: float = 2.0  # inset from the left edge of the front face
    side: str = "south"  # which face carries the label: south | north | east | west


@dataclass
class LayerSpec:
    """One printable feature class (runs, lifts, trails, water, buildings...)."""

    name: str
    select: list[str] = field(default_factory=list)  # Overpass tag selectors for `way`
    width_mm: float = 1.2  # drawn line width on the model
    raise_mm: float = 0.2  # how far the feature's top sits above the terrain (parts mode)
    embed_mm: float = 0.6  # how far the feature extends below the terrain surface (parts mode)
    relief_mm: float = 0.4  # emboss/engrave depth in single-colour modes
    fill_closed: bool = False  # fill closed ways (areas) instead of outlining them
    color: str = "#ffffff"  # preview colour
    enabled: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", self.name):
            raise ValueError(f"layer name must be kebab-case, got {self.name!r}")
        if not self.select:
            raise ValueError(f"layer {self.name!r} needs at least one `select` entry")


@dataclass
class AreaConfig:
    name: str
    slug: str
    bbox: BBox
    model: ModelSpec = field(default_factory=ModelSpec)
    label: LabelSpec = field(default_factory=LabelSpec)
    layers: list[LayerSpec] = field(default_factory=list)
    terrain_color: str = "#3f8f4f"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", self.slug):
            raise ValueError(f"slug must be kebab-case, got {self.slug!r}")
        names = [layer.name for layer in self.layers]
        if len(names) != len(set(names)):
            raise ValueError("layer names must be unique")

    @property
    def enabled_layers(self) -> list[LayerSpec]:
        return [layer for layer in self.layers if layer.enabled]


def _bbox_from(raw) -> BBox:
    if isinstance(raw, dict):
        return BBox(**raw)
    if isinstance(raw, (list, tuple)) and len(raw) == 4:
        south, west, north, east = raw
        return BBox(south, west, north, east)
    raise ValueError("bbox must be {south, west, north, east} or [south, west, north, east]")


def area_from_dict(raw: dict) -> AreaConfig:
    raw = dict(raw)
    label_raw = raw.pop("label", {}) or {}
    if isinstance(label_raw, str):
        label_raw = {"text": label_raw}
    label = LabelSpec(**label_raw)
    if "text" not in label_raw:
        label.text = raw["name"]
    return AreaConfig(
        name=raw["name"],
        slug=raw["slug"],
        bbox=_bbox_from(raw["bbox"]),
        model=ModelSpec(**(raw.pop("model", {}) or {})),
        label=label,
        layers=[LayerSpec(**layer) for layer in (raw.pop("layers", []) or [])],
        terrain_color=raw.get("terrain_color", "#3f8f4f"),
    )


def load_area(path: str | Path) -> AreaConfig:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at top level")
    return area_from_dict(raw)
