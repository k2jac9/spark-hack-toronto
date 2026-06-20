"""Build a small committed REAL slice of Toronto Bike Share trip-origin demand (demo_data/).

Produces ``demo_data/bikeshare__downtown.csv`` — the "demand to leave" temporal field the
Urban-OS MobilityDemand display lens lifts onto the substrate (ADR-0030). A Bike Share trip
*origin* is a local decision to leave; counting trip starts per station per 15-min bin gives
a real micromobility demand series in the same ``location, lat, lng, time_start, mode, volume``
shape the TMC slice uses.

What it does (real values, only reshaped):
- Pulls one City "Bike Share Ridership" yearly ZIP (default 2026 — the small current-year
  file) and streams its trip CSV. The trip rows carry a start station + start time but **no
  coordinates**, so we join each station to the live GBFS ``station_information`` feed for its
  real lat/lng (the same public Bike Share Toronto source).
- Keeps the **evening egress window (17:00–19:00)** and aggregates trip origins per station per
  15-min-of-day bin across every day in the file (a robust "typical evening" profile rather
  than one arbitrary day). The window is chosen to line up with the post-event evening egress
  the demo simulates; the adapter rebases the first bin to t=0, so 17:00 maps onto sim-minute 0.
- Filters to the downtown bbox (matches ``fetch_tmc.py`` / the offline PMTiles basemap) and
  writes a tidy slice (one row per station per 15-min bin).

Offline-safe: any network failure prints a note and exits 0 (the adapter's synthetic fallback
covers dev/CI), so ``make demo-data`` never breaks off-box. The raw ZIP is never committed —
only the small normalized slice under demo_data/ (repo hygiene).

    python scripts/fetch_bikeshare.py            # default year 2026
    python scripts/fetch_bikeshare.py --year 2025
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_data"

# CKAN "Bike Share Toronto Ridership Data" yearly ZIP resources (id verified via package_show).
_ZIP_RESOURCE = {
    "2026": "6124836d-a7ce-4f95-82ea-105fecaecd1a",  # current partial year (smallest)
    "2025": "dedb033b-b6e9-45d1-baa4-836d1e0c7f1b",
    "2024": "551c0cbf-6e78-4390-86e4-5a6665369bd1",
    "2023": "129aea67-9974-4814-a614-8965a38818c6",
}
_RESOURCE_SHOW = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/resource_show"
)
# Live Bike Share Toronto station coordinates (GBFS) — the trip CSV has no lat/lng.
_GBFS_STATION_INFO = (
    "https://tor.publicbikesystem.net/ube/gbfs/v1/en/station_information"
)
# Downtown bbox — matches fetch_tmc.py / build_demo_slice.py / the offline PMTiles basemap.
BBOX = dict(min_lat=43.62, max_lat=43.69, min_lon=-79.43, max_lon=-79.34)
# Evening egress window [start, end) in minutes-from-midnight (17:00–19:00).
WIN_START, WIN_END = 17 * 60, 19 * 60
BIN = 15                # 15-min bins, matching the TMC / observed-count grid
MAX_OUT = 5000          # cap on normalized rows written (matches loader _ROW_LIMIT)


def _station_coords() -> dict[str, tuple[float, float]]:
    """{station_id: (lat, lng)} from the GBFS station_information feed."""
    resp = httpx.get(_GBFS_STATION_INFO, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    out: dict[str, tuple[float, float]] = {}
    for s in resp.json()["data"]["stations"]:
        try:
            out[str(s["station_id"])] = (float(s["lat"]), float(s["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _zip_url(year: str) -> str:
    rid = _ZIP_RESOURCE[year]
    resp = httpx.get(_RESOURCE_SHOW, params={"id": rid}, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()["result"]["url"]


def _aggregate_origins(csv_bytes: io.BufferedReader) -> dict[str, dict[int, float]]:
    """Stream the trip CSV; sum evening trip origins per ``{station_id: {bin: count}}``.

    Only rows whose start time falls in the evening window are kept; the 15-min bin is the
    minute-of-day floored to ``BIN``. Aggregating across every day in the file yields a typical
    evening profile (one bad row is skipped, never fatal — mirrors the loader's tolerance)."""
    by_station: dict[str, dict[int, float]] = {}
    reader = csv.DictReader(io.TextIOWrapper(csv_bytes, encoding="utf-8-sig", errors="replace"))
    for row in reader:
        t = (row.get("Start_Time") or "").strip()
        sid = str(row.get("Start_Station_Id") or "").split(".")[0].strip()
        if len(t) < 16 or not sid:
            continue
        try:                                   # "YYYY-MM-DD HH:MM:SS"
            minute = int(t[11:13]) * 60 + int(t[14:16])
        except (ValueError, IndexError):
            continue
        if not (WIN_START <= minute < WIN_END):
            continue
        b = (minute // BIN) * BIN
        by_station.setdefault(sid, {})
        by_station[sid][b] = by_station[sid].get(b, 0.0) + 1.0
    return by_station


def _normalize(
    by_station: dict[str, dict[int, float]], coords: dict[str, tuple[float, float]]
) -> list[dict]:
    """Join station→coords, keep downtown stations, emit one tidy row per station per bin
    (busiest stations first so an MAX_OUT cap keeps the strongest signal)."""
    rows: list[dict] = []
    ordered = sorted(by_station.items(), key=lambda kv: -sum(kv[1].values()))
    for sid, bins in ordered:
        if sid not in coords:
            continue
        lat, lng = coords[sid]
        if not (BBOX["min_lat"] <= lat <= BBOX["max_lat"]
                and BBOX["min_lon"] <= lng <= BBOX["max_lon"]):
            continue
        for b in sorted(bins):
            rows.append({
                "location": f"bikeshare_{sid}",
                "lat": lat,
                "lng": lng,
                "time_start": f"{b // 60:02d}:{b % 60:02d}",
                "mode": "bike",
                "volume": int(bins[b]),
            })
            if len(rows) >= MAX_OUT:
                return rows
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--year", default="2026", choices=sorted(_ZIP_RESOURCE),
                   help="Bike Share ridership year to slice (default 2026, the smallest).")
    args = p.parse_args(argv)
    try:
        coords = _station_coords()
        url = _zip_url(args.year)
        zbytes = httpx.get(url, timeout=300, follow_redirects=True).content
        zf = zipfile.ZipFile(io.BytesIO(zbytes))
        member = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
        with zf.open(member) as fh:
            by_station = _aggregate_origins(fh)
    except Exception as exc:  # noqa: BLE001 — offline-safe: never fail the chained target
        print(f"fetch_bikeshare: skipped (no network / API error: {exc}). "
              "The synthetic-demand fallback covers dev/CI.")
        return 0
    rows = _normalize(by_station, coords)
    if not rows:
        print("fetch_bikeshare: no downtown rows returned; leaving any existing slice in place.")
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "bikeshare__downtown.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh, fieldnames=["location", "lat", "lng", "time_start", "mode", "volume"]
        )
        w.writeheader()
        w.writerows(rows)
    locs = len({r["location"] for r in rows})
    print(f"bikeshare: {len(rows)} rows across {locs} downtown stations "
          f"(evening 17:00-19:00, {args.year}) -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
