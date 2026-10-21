"""Fetch way geometries from OpenStreetMap through the Overpass API, with a disk cache."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import requests

from .config import BBox

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "trailprint/0.1 (+https://github.com/duncan-fixturfab/trailprint)"


@dataclass
class Way:
    id: int
    coords: list[tuple[float, float]]  # (lon, lat)
    tags: dict[str, str] = field(default_factory=dict)

    @property
    def closed(self) -> bool:
        return len(self.coords) > 3 and self.coords[0] == self.coords[-1]

    @property
    def is_area(self) -> bool:
        return self.closed and (
            self.tags.get("area") == "yes"
            or "building" in self.tags
            or self.tags.get("natural") == "water"
            or "landuse" in self.tags
        )


def build_query(bbox: BBox, selectors: list[str], timeout: int = 180) -> str:
    body = "".join(f"way{sel}({bbox.overpass()});" for sel in selectors)
    return f"[out:json][timeout:{timeout}];({body});out geom;"


def parse_ways(payload: dict) -> list[Way]:
    ways = []
    for el in payload.get("elements", []):
        if el.get("type") != "way" or "geometry" not in el:
            continue
        coords = [(p["lon"], p["lat"]) for p in el["geometry"]]
        if len(coords) < 2:
            continue
        ways.append(Way(id=el["id"], coords=coords, tags=el.get("tags", {})))
    return ways


def fetch_ways(
    bbox: BBox,
    selectors: list[str],
    cache_dir: Path,
    session: requests.Session | None = None,
    endpoint: str = OVERPASS_URL,
    retries: int = 4,
) -> list[Way]:
    query = build_query(bbox, selectors)
    key = hashlib.sha256(query.encode()).hexdigest()[:24]
    path = cache_dir / "overpass" / f"{key}.json"
    if path.exists():
        return parse_ways(json.loads(path.read_text(encoding="utf-8")))

    session = session or requests.Session()
    delay = 5.0
    last_exc: Exception | None = None
    for _attempt in range(retries):
        try:
            resp = session.post(
                endpoint,
                data={"data": query},
                timeout=240,
                headers={"User-Agent": USER_AGENT},
            )
            if resp.status_code in (429, 502, 503, 504):
                raise requests.HTTPError(f"Overpass busy: HTTP {resp.status_code}", response=resp)
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            last_exc = exc
            time.sleep(delay)
            delay *= 2
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload), encoding="utf-8")
        return parse_ways(payload)
    raise RuntimeError(f"Overpass request failed after {retries} attempts: {last_exc}")
