"""Build a small committed REAL slice of Toronto automated traffic enforcement (demo_data/).

Produces ``demo_data/enforcement__downtown.csv`` — the geocoded "where the city actively manages
dangerous traffic" field the Urban-OS Enforcement display lens lifts onto the substrate (ADR-0039).
Merges two real City feeds of automated enforcement device locations:
  - **Red Light Cameras** (`red-light-cameras`) — at major signalised intersections.
  - **Automated Speed Enforcement** (`automated-speed-enforcement-locations`) — on roads near
    schools / community-safety zones.
Each device is a real point (the CSVs carry a GeoJSON ``geometry`` MultiPoint, parsed here to
lat/lng). Counting weighted enforcement devices near each substrate node gives a real **enforcement
density** — distinct from collision history (KSI / RoadRisk) and active closures (RoadDisruption);
together the three form the road-safety triad.

What it does (real values, only reshaped):
- Streams each feed's CSV, parses the ``geometry`` coordinates ([lng, lat] GeoJSON), keeps the
  downtown bbox (matches fetch_ksi.py / the offline PMTiles basemap), and weights red-light cameras
  (continuous, major intersections) 2 vs speed cameras 1 — the relative *shape* is the claim.
- Writes a tidy slice (one row per device).

Offline-safe: any network/parse failure prints a note and exits 0 (the adapter's synthetic fallback
covers dev/CI). The raw CSVs are never committed — only the small normalized slice.

    python scripts/fetch_enforcement.py
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import sys
from pathlib import Path

import httpx

from urbanos.risk.ingest.ckan import CKANClient

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_data"

# (slug, name_contains hint, device type, severity weight)
_FEEDS = [
    ("red-light-cameras", "", "red_light", 2),
    ("automated-speed-enforcement-locations", "", "speed", 1),
]
# Downtown bbox — matches fetch_ksi.py / fetch_road_restrictions.py / the offline PMTiles basemap.
BBOX = dict(min_lat=43.62, max_lat=43.69, min_lon=-79.43, max_lon=-79.34)


def _coords_from_geometry(geom: str):
    """Parse a GeoJSON ``geometry`` cell (Point / MultiPoint) → (lat, lng) or None. GeoJSON is
    [lng, lat]; a MultiPoint nests one more level. One bad cell is skipped, never fatal."""
    try:
        g = json.loads(geom)
        c = g.get("coordinates")
        # Point: [lng, lat]; MultiPoint/Line: [[lng, lat], ...]
        if c and isinstance(c[0], (list, tuple)):
            c = c[0]
        lng, lat = float(c[0]), float(c[1])
        return lat, lng
    except (TypeError, ValueError, KeyError, json.JSONDecodeError, IndexError):
        return None


def _collect(text: str, dtype: str, severity: int) -> list[dict]:
    rows: list[dict] = []
    reader = csv.DictReader(text.splitlines())
    # geometry column may be 'geometry' (case varies)
    for r in reader:
        geom = r.get("geometry") or r.get("Geometry") or r.get("GEOMETRY") or ""
        c = _coords_from_geometry(geom)
        if c is None:
            continue
        lat, lng = c
        if not (BBOX["min_lat"] <= lat <= BBOX["max_lat"]
                and BBOX["min_lon"] <= lng <= BBOX["max_lon"]):
            continue
        rows.append({"lat": round(lat, 6), "lng": round(lng, 6),
                     "severity": severity, "type": dtype})
    return rows


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    rows: list[dict] = []
    try:
        c = CKANClient()
        for slug, name, dtype, severity in _FEEDS:
            res = c.find_resource(slug, formats=["CSV"], name_contains=name)
            text = httpx.get(res["url"], timeout=120, follow_redirects=True).content.decode(
                "utf-8-sig", errors="replace"
            )
            got = _collect(text, dtype, severity)
            rows.extend(got)
            print(f"  {slug}: {len(got)} downtown devices")
    except Exception as exc:  # noqa: BLE001 — offline-safe
        print(f"fetch_enforcement: skipped (no network / API error: {exc}). "
              "The synthetic enforcement fallback covers dev/CI.")
        return 0
    if not rows:
        print("fetch_enforcement: no downtown rows; leaving any existing slice in place.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "enforcement__downtown.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lat", "lng", "severity", "type"])
        w.writeheader()
        w.writerows(rows)
    rl = sum(1 for r in rows if r["type"] == "red_light")
    print(f"enforcement: {len(rows)} downtown devices ({rl} red-light, {len(rows)-rl} speed) "
          f"-> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
