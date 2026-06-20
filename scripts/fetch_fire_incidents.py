"""Build a small committed REAL slice of Toronto fire/emergency incidents (demo_data/).

Produces ``demo_data/fire_incidents__downtown.csv`` — the geocoded "where emergencies cluster"
field the Urban-OS Emergency display lens lifts onto the substrate (ADR-0041). Each row of the
Toronto Fire Services ``fire-incidents`` dataset is a real incident with a Latitude/Longitude.
Counting severity-weighted incidents near each substrate node gives a real emergency-response-load
density — a different axis from the crowd crush, and a natural pair to the EMS-access overlay (where
ambulances struggle to reach vs. where incidents actually happen).

What it does (real values, only reshaped):
- Streams the CSV, keeps recent years (``--since``, default 2018) and the downtown bbox (matches
  fetch_ksi.py / the offline PMTiles basemap). Weights actual fires/explosions 2 vs other incident
  types 1 — the relative *shape* is the claim, not any single count.
- Writes a tidy slice (one row per incident), most-severe first, capped at MAX_OUT.

Offline-safe: any network/parse failure prints a note and exits 0 (the adapter's synthetic fallback
covers dev/CI). The raw CSV is never committed — only the small normalized slice.

    python scripts/fetch_fire_incidents.py --since 2018
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

_DATASET = "fire-incidents"
BBOX = dict(min_lat=43.62, max_lat=43.69, min_lon=-79.43, max_lon=-79.34)
MAX_OUT = 2500


def _find(cols, *keys):
    low = {c.lower(): c for c in cols}
    for c_low, c in low.items():
        if any(k in c_low for k in keys):
            return c
    return None


def _severity(itype: str) -> int:
    """Weight an actual fire/explosion 2, any other incident type 1."""
    t = (itype or "").lower()
    if "fire" in t or "explos" in t:
        return 2
    return 1


def _collect(text: str, since: int) -> list[dict]:
    reader = csv.DictReader(text.splitlines())
    cols = reader.fieldnames or []
    lat_c = _find(cols, "latitude", "lat")
    lng_c = _find(cols, "longitude", "long", "lng")
    type_c = _find(cols, "final_incident_type", "incident_type", "event_type")
    time_c = _find(cols, "alarm_time", "tfs_alarm", "year")
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
        raw_t = (r.get(time_c) or "") if time_c else ""
        try:
            year = int(str(raw_t)[:4]) if len(str(raw_t)) >= 4 else since
        except (TypeError, ValueError):
            year = since
        if year < since:
            continue
        rows.append({"lat": round(lat, 6), "lng": round(lng, 6),
                     "severity": _severity(r.get(type_c, "")), "year": year})
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", type=int, default=2018, help="Earliest incident year (default 2018).")
    args = p.parse_args(argv)
    try:
        res = CKANClient().find_resource(_DATASET, formats=["CSV"], name_contains="")
        text = httpx.get(res["url"], timeout=180, follow_redirects=True).content.decode(
            "utf-8-sig", errors="replace"
        )
        rows = _collect(text, args.since)
    except Exception as exc:  # noqa: BLE001 — offline-safe
        print(f"fetch_fire_incidents: skipped (no network / API error: {exc}). "
              "The synthetic emergency fallback covers dev/CI.")
        return 0
    if not rows:
        print("fetch_fire_incidents: no downtown rows; leaving any existing slice in place.")
        return 0
    rows.sort(key=lambda r: (-r["severity"], -r["year"]))
    rows = rows[:MAX_OUT]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "emergency__downtown.csv"   # the "emergency" lens key (ADR-0041)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lat", "lng", "severity", "year"])
        w.writeheader()
        w.writerows(rows)
    fires = sum(1 for r in rows if r["severity"] == 2)
    yrs = sorted({r["year"] for r in rows})
    print(f"fire_incidents: {len(rows)} downtown incidents ({fires} fire/explosion), "
          f"years {yrs[0]}-{yrs[-1]} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
