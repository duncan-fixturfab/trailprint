import json

import trimesh

from tests.conftest import AREAS
from trailprint import build as build_mod
from trailprint.build import build, plan
from trailprint.config import load_area


def test_area_yamls_load_and_plan():
    for path in sorted(AREAS.glob("*.yaml")):
        area = load_area(path)
        info = plan(area)
        assert info["dem_zoom"] >= 12
        assert info["footprint_mm"][0] == area.model.width_mm


def test_build_parts_end_to_end(tmp_path, monkeypatch, area, synthetic_dem, fake_ways):
    monkeypatch.setattr(build_mod.dem_mod, "fetch_dem", lambda bbox, zoom, cache: synthetic_dem)
    monkeypatch.setattr(build_mod.osm_mod, "fetch_ways", fake_ways)
    result = build(area, tmp_path, cache_dir=tmp_path / "cache")
    for name in ("terrain", "runs", "lifts", "label", "preview", "3mf"):
        assert name in result.files, name
        assert result.files[name].exists()
    terrain = trimesh.load(result.files["terrain"])
    assert terrain.is_watertight
    assert terrain.bounds[0][2] == 0.0
    assert terrain.bounds[1][2] > area.model.base_mm
    runs = trimesh.load(result.files["runs"])
    assert runs.is_watertight and runs.volume > 0
    stats = json.loads((result.out_dir / "test-hill-stats.json").read_text())
    assert stats["meshes"]["terrain"]["watertight"]


def test_build_emboss_single_mesh(tmp_path, monkeypatch, area, synthetic_dem, fake_ways):
    monkeypatch.setattr(build_mod.dem_mod, "fetch_dem", lambda bbox, zoom, cache: synthetic_dem)
    monkeypatch.setattr(build_mod.osm_mod, "fetch_ways", fake_ways)
    result = build(area, tmp_path, cache_dir=tmp_path / "cache", mode="emboss")
    assert "runs" not in result.files
    assert trimesh.load(result.files["terrain"]).is_watertight
