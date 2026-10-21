"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__
from .build import DEFAULT_CACHE, build, plan
from .config import MODES, load_area


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="trailprint", description=__doc__)
    p.add_argument("--version", action="version", version=f"trailprint {__version__}")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("area", type=Path, help="area YAML (see areas/)")
        sp.add_argument("-o", "--out", type=Path, default=Path("out"), help="output root")
        sp.add_argument("--cache", type=Path, default=DEFAULT_CACHE, help="tile/OSM cache dir")
        sp.add_argument("--width", type=float, help="override model width (mm)")
        sp.add_argument("--resolution", type=float, help="override grid cell size (mm)")
        sp.add_argument("--z-scale", type=float, help="override vertical exaggeration")

    b = sub.add_parser("build", help="fetch data and write STL/3MF/preview")
    common(b)
    b.add_argument("--mode", choices=MODES, help="override output mode")

    pv = sub.add_parser("preview", help="fetch data and write only the preview PNG")
    common(pv)

    i = sub.add_parser("info", help="print the computed grid/scale plan without fetching")
    i.add_argument("area", type=Path)
    i.add_argument("--width", type=float)
    i.add_argument("--resolution", type=float)
    return p


def _apply_overrides(area, args) -> None:
    if getattr(args, "width", None):
        area.model.width_mm = args.width
    if getattr(args, "resolution", None):
        area.model.resolution_mm = args.resolution
    if getattr(args, "z_scale", None):
        area.model.z_scale = args.z_scale


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")
    area = load_area(args.area)
    _apply_overrides(area, args)

    if args.command == "info":
        print(json.dumps({"name": area.name, "slug": area.slug, **plan(area)}, indent=2))
        return 0

    result = build(
        area,
        args.out,
        cache_dir=args.cache,
        mode=getattr(args, "mode", None),
        preview_only=args.command == "preview",
    )
    for name, path in result.files.items():
        print(f"{name:12s} {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
