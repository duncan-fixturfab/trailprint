# trailprint

Python CLI that turns an area YAML into printable STL/3MF terrain models. Package in
`src/trailprint/`, demo configs in `areas/`, offline tests in `tests/`.

- `uv sync --all-extras`, then `uv run pytest` and `uv run ruff check .` before committing.
- Tests must stay offline: monkeypatch `build.dem_mod.fetch_dem` and `build.osm_mod.fetch_ways`
  (see `tests/conftest.py`). Network fetches are cached under `~/.cache/trailprint/`.
- Grid arrays are `[i, j]` with row 0 at the SOUTH edge (south-up). Flip for images.
- All solids come from `mesh.heightfield_solid`; keep it watertight (the tests check
  `is_watertight`, `is_winding_consistent`, positive volume).
- Overpass needs a User-Agent header or it returns 406. Keep per-layer queries so a selector
  change only re-fetches that layer.
