"""Build the small committed REAL gazetteers the offline geo-resolver reads (demo_data/).

The resolver (``urbanos.risk.ingest.georesolve``) turns an address / intersection / ward
string into ``(lat, lng)`` using only local data. This script builds the three committed
lookup tables it needs, each from a real City of Toronto WGS84 (4326) GeoJSON resource:

- ``demo_data/intersections__downtown.csv`` — ``intersection_id,desc,lat,lng`` from the
  **Centreline Intersection** file, filtered to the same downtown bbox as
  ``fetch_ksi.py`` / ``fetch_road_restrictions.py`` and capped at ``MAX_OUT`` (keeps the
  committed slice small).
- ``demo_data/ward_centroids.csv`` — ``code,name,centroid_lat,centroid_lng`` from
  **City Wards** (25 rows; centroid = pure-Python mean of the largest polygon's exterior
  ring vertices, dropping the closing vertex).
- ``demo_data/neighbourhood_centroids.csv`` — same shape from **Neighbourhoods** (158 rows).

Centroid crudeness: vertex-averaging is not area-weighted; that is acceptable because the
area centroid is the resolver's explicitly coarsest, down-weighted tier (``area-approx``).

Offline-safe: each of the three builds is independent and any network/parse failure prints a
note and is skipped, so a partial or no-network run leaves existing slices in place and
``make demo-data`` never breaks. The raw GeoJSON is never committed — only the small slices.

    python scripts/fetch_gazetteers.py
"""
from __future__ import annotations

import csv
import json
import sys
import tempfile
from pathlib import Path

# Allow running as a plain script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from urbanos.risk.ingest.ckan import CKANClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_data"

# Downtown bbox — matches fetch_ksi.py / fetch_road_restrictions.py / the offline PMTiles
# basemap. Only the intersection slice is filtered to it; the area centroids stay city-wide
# so a non-downtown ward still resolves to its own centroid.
BBOX = dict(min_lat=43.62, max_lat=43.69, min_lon=-79.43, max_lon=-79.34)
MAX_OUT = 4000          # cap on intersections written (keeps the committed slice ~250 KB)
_MAX_BYTES = 120_000_000  # raw GeoJSON size guard (intersection file is ~40 MB)


def _prop(props: dict, *needles: str) -> str:
    """First property whose key contains a needle (case-insensitive). '' when none match."""
    low = {str(k).lower(): v for k, v in props.items()}
    for needle in needles:
        for k, v in low.items():
            if needle in k and v not in (None, ""):
                return str(v)
    return ""


def _first_point(geom: dict) -> tuple[float, float] | None:
    """(lng, lat) of a Point / MultiPoint geometry, or None."""
    coords = geom.get("coordinates")
    gtype = geom.get("type")
    try:
        if gtype == "Point":
            return float(coords[0]), float(coords[1])
        if gtype == "MultiPoint":
            return float(coords[0][0]), float(coords[0][1])
    except (TypeError, ValueError, IndexError):
        return None
    return None


def _ring_centroid(geom: dict) -> tuple[float, float] | None:
    """Centroid (lng, lat) = mean of the largest polygon's exterior-ring vertices, dropping
    the closing vertex. Handles Polygon and MultiPolygon; None on anything unparseable."""
    gtype = geom.get("type")
    coords = geom.get("coordinates")
    try:
        if gtype == "Polygon":
            rings = [coords[0]]
        elif gtype == "MultiPolygon":
            rings = [poly[0] for poly in coords]
        else:
            return None
        ring = max(rings, key=len)              # largest polygon by exterior-ring vertices
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]                    # drop the closing vertex
        if not ring:
            return None
        lng = sum(float(pt[0]) for pt in ring) / len(ring)
        lat = sum(float(pt[1]) for pt in ring) / len(ring)
        return lng, lat
    except (TypeError, ValueError, IndexError):
        return None


def _download_geojson(ckan: CKANClient, slug: str, name_contains: str, dest: Path) -> list:
    res = ckan.find_resource(slug, formats=("geojson",), name_contains=name_contains)
    if res is None:
        raise RuntimeError(f"{slug}: no GeoJSON resource matching {name_contains!r}")
    path = ckan.download_resource(res, dest, max_bytes=_MAX_BYTES)
    return json.loads(path.read_text(encoding="utf-8")).get("features", [])


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def build_intersections(ckan: CKANClient, tmp: Path) -> int:
    feats = _download_geojson(
        ckan, "intersection-file-city-of-toronto", "4326.geojson", tmp / "intersections.geojson"
    )
    rows: list[dict] = []
    for f in feats:
        pt = _first_point(f.get("geometry") or {})
        if pt is None:
            continue
        lng, lat = pt
        if not (BBOX["min_lat"] <= lat <= BBOX["max_lat"]
                and BBOX["min_lon"] <= lng <= BBOX["max_lon"]):
            continue
        props = f.get("properties") or {}
        desc = _prop(props, "intersection_desc", "desc")
        rid = _prop(props, "intersection_id")
        if not (desc and rid):
            continue
        rows.append({
            "intersection_id": rid,
            "desc": desc,
            "lat": round(lat, 6),
            "lng": round(lng, 6),
        })
    rows = rows[:MAX_OUT]
    if not rows:
        print("fetch_gazetteers: no downtown intersections; leaving any existing slice in place.")
        return 0
    _write_csv(OUT / "intersections__downtown.csv", ["intersection_id", "desc", "lat", "lng"], rows)
    print(f"intersections: {len(rows)} downtown rows -> {OUT / 'intersections__downtown.csv'}")
    return len(rows)


def build_areas(ckan: CKANClient, slug: str, name_contains: str, out_name: str, tmp: Path) -> int:
    feats = _download_geojson(ckan, slug, name_contains, tmp / f"{out_name}.geojson")
    rows: list[dict] = []
    for f in feats:
        c = _ring_centroid(f.get("geometry") or {})
        if c is None:
            continue
        lng, lat = c
        props = f.get("properties") or {}
        rows.append({
            "code": _prop(props, "short_code", "long_code", "area_id", "code"),
            "name": _prop(props, "area_name", "name"),
            "centroid_lat": round(lat, 6),
            "centroid_lng": round(lng, 6),
        })
    if not rows:
        print(f"fetch_gazetteers: no {out_name} features; leaving any existing slice in place.")
        return 0
    _write_csv(OUT / f"{out_name}.csv", ["code", "name", "centroid_lat", "centroid_lng"], rows)
    print(f"{out_name}: {len(rows)} centroids -> {OUT / (out_name + '.csv')}")
    return len(rows)


def main() -> int:
    builds = (
        ("intersections", lambda c, t: build_intersections(c, t)),
        ("ward_centroids",
         lambda c, t: build_areas(c, "city-wards", "4326.geojson", "ward_centroids", t)),
        ("neighbourhood_centroids",
         lambda c, t: build_areas(c, "neighbourhoods", "4326.geojson", "neighbourhood_centroids", t)),
    )
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        for label, fn in builds:
            try:
                with CKANClient() as ckan:
                    fn(ckan, tmp)
            except Exception as exc:  # noqa: BLE001 — offline-safe: never fail the chained target
                print(f"fetch_gazetteers: {label} skipped (no network / API / parse error: {exc}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
