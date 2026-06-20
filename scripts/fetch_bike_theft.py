"""Build a small committed REAL slice of Toronto bicycle thefts (demo_data/).

Produces ``demo_data/bike_theft__downtown.csv`` — the geocoded "where bikes get stolen" field the
Urban-OS BikeTheft display lens lifts onto the substrate (ADR-0040). Each row of the Toronto Police
``bicycle-thefts`` dataset is a real reported theft with a WGS84 lat/lng. Counting thefts near each
substrate node gives a real property-crime / cycling-safety density — a different axis from the
crowd crush, and a natural pair to the bike-demand (MobilityDemand) + footfall lenses (where people
ride/leave bikes vs. where they get stolen).

What it does (real values, only reshaped):
- Streams the CSV, keeps recent years (``--since``, default 2018) and the downtown bbox (matches
  fetch_ksi.py / the offline PMTiles basemap). Each theft is weight 1 (a count density).
- Writes a tidy slice (one row per theft), capped at MAX_OUT.

Offline-safe: any network/parse failure prints a note and exits 0 (the adapter's synthetic fallback
covers dev/CI). The raw CSV is never committed — only the small normalized slice.

    python scripts/fetch_bike_theft.py --since 2018
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import httpx

from urbanos.risk.ingest.ckan import CKANClient

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_data"

_DATASET = "bicycle-thefts"
BBOX = dict(min_lat=43.62, max_lat=43.69, min_lon=-79.43, max_lon=-79.34)
MAX_OUT = 2500


def _find(cols, *keys):
    """First column whose lowercased name contains any key."""
    low = {c.lower(): c for c in cols}
    for c_low, c in low.items():
        if any(k in c_low for k in keys):
            return c
    return None


def _collect(text: str, since: int) -> list[dict]:
    reader = csv.DictReader(text.splitlines())
    cols = reader.fieldnames or []
    lat_c = _find(cols, "lat_wgs84", "latitude", "lat")
    lng_c = _find(cols, "long_wgs84", "longitude", "long", "lng")
    yr_c = _find(cols, "occ_year", "report_year", "year")
    if not (lat_c and lng_c):
        return []
    rows: list[dict] = []
    for r in reader:
        try:
            lat, lng = float(r.get(lat_c) or ""), float(r.get(lng_c) or "")
        except (TypeError, ValueError):
            continue
        if not (BBOX["min_lat"] <= lat <= BBOX["max_lat"]
                and BBOX["min_lon"] <= lng <= BBOX["max_lon"]):
            continue
        try:
            year = int(float(r.get(yr_c) or 0)) if yr_c else since
        except (TypeError, ValueError):
            year = since
        if year < since:
            continue
        rows.append({"lat": round(lat, 6), "lng": round(lng, 6), "severity": 1, "year": year})
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", type=int, default=2018, help="Earliest occurrence year (default 2018).")
    args = p.parse_args(argv)
    try:
        res = CKANClient().find_resource(_DATASET, formats=["CSV"], name_contains="")
        text = httpx.get(res["url"], timeout=180, follow_redirects=True).content.decode(
            "utf-8-sig", errors="replace"
        )
        rows = _collect(text, args.since)
    except Exception as exc:  # noqa: BLE001 — offline-safe
        print(f"fetch_bike_theft: skipped (no network / API error: {exc}). "
              "The synthetic bike-theft fallback covers dev/CI.")
        return 0
    if not rows:
        print("fetch_bike_theft: no downtown rows; leaving any existing slice in place.")
        return 0
    rows.sort(key=lambda r: -r["year"])
    rows = rows[:MAX_OUT]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "bike_theft__downtown.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lat", "lng", "severity", "year"])
        w.writeheader()
        w.writerows(rows)
    yrs = sorted({r["year"] for r in rows})
    print(f"bike_theft: {len(rows)} downtown thefts, years {yrs[0]}-{yrs[-1]} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
