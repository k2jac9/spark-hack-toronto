"""Build a small committed REAL slice of Toronto road-safety (Vision Zero) collisions (demo_data/).

Produces ``demo_data/ksi__downtown.csv`` — the geocoded "where the road is historically
dangerous" field the Urban-OS RoadRisk display lens lifts onto the substrate (ADR-0036).
Each row of the City "Motor Vehicle Collisions involving Killed or Seriously Injured Persons"
(KSI / Vision Zero) dataset is a person-involvement record at a real intersection with a
``latitude``/``longitude`` (the ``- 4326`` resource is WGS84). Counting severity-weighted KSI
records near each substrate node gives a real, static **road-danger density** — distinct from
the civic Safety index (food inspections) and the crowd crush.

What it does (real values, only reshaped):
- Streams the KSI ``- 4326`` CSV (WGS84 lat/lng).
- Keeps recent years (``--since``, default 2014) so the danger signal reflects the current
  network, and the downtown bbox (matches ``fetch_tmc.py`` / ``fetch_bikeshare.py`` / the
  offline PMTiles basemap).
- Weights each record by injury severity (Fatal 3 / Major 2 / else 1) so a fatal corner reads
  hotter than a minor one — the relative *shape* is the claim, not any single count.
- Writes a tidy slice (one row per kept KSI record), most-severe first so an MAX_OUT cap keeps
  the strongest signal.

Offline-safe: any network/parse failure prints a note and exits 0 (the adapter's synthetic
fallback covers dev/CI), so ``make demo-data`` never breaks off-box. The raw CSV is never
committed — only the small normalized slice under demo_data/ (repo hygiene).

    python scripts/fetch_ksi.py                 # recent years, downtown
    python scripts/fetch_ksi.py --since 2018
"""
from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "demo_data"

# CKAN KSI dataset; the "- 4326" CSV resource is WGS84 lat/lng (id verified via resource_show).
_KSI_DATASET = "motor-vehicle-collisions-involving-killed-or-seriously-injured-persons"
_KSI_RESOURCE_4326 = "b95f5270-4eb0-40c2-917d-37fb494328a1"
_RESOURCE_SHOW = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/api/3/action/resource_show"
)
# Downtown bbox — matches fetch_tmc.py / fetch_bikeshare.py / the offline PMTiles basemap.
BBOX = dict(min_lat=43.62, max_lat=43.69, min_lon=-79.43, max_lon=-79.34)
MAX_OUT = 2500          # cap on normalized rows written (keeps the committed slice small)


def _severity(row: dict) -> int:
    """Injury severity weight (Fatal 3 / Major 2 / else 1) from the per-record fields. A KSI
    row is already a serious record; the weight just lets a fatal corner read hotter."""
    inj = (row.get("injury") or "").strip().lower()
    acc = (row.get("acclass") or "").strip().lower()
    # NB: acclass is "Fatal Injury" / "Non-Fatal Injury" — use startswith so "Non-Fatal"
    # (which contains the substring "fatal") is NOT counted as fatal.
    if "fatal" in inj or acc.startswith("fatal"):
        return 3
    if "major" in inj:
        return 2
    return 1


def _resource_url(rid: str) -> str:
    resp = httpx.get(_RESOURCE_SHOW, params={"id": rid}, timeout=60, follow_redirects=True)
    resp.raise_for_status()
    return resp.json()["result"]["url"]


def _collect(csv_bytes, since: int) -> list[dict]:
    """Stream the KSI CSV; keep downtown rows since ``since`` with a parseable lat/lng. One bad
    row is skipped, never fatal (mirrors the loader's tolerance)."""
    rows: list[dict] = []
    reader = csv.DictReader(io.TextIOWrapper(csv_bytes, encoding="utf-8-sig", errors="replace"))
    for r in reader:
        try:
            lat = float(r.get("latitude") or "")
            lng = float(r.get("longitude") or "")
        except (TypeError, ValueError):
            continue
        if not (BBOX["min_lat"] <= lat <= BBOX["max_lat"]
                and BBOX["min_lon"] <= lng <= BBOX["max_lon"]):
            continue
        date = (r.get("accdate") or "").strip()
        try:
            year = int(date[:4])
        except (ValueError, IndexError):
            continue
        if year < since:
            continue
        rows.append({
            "lat": round(lat, 6),
            "lng": round(lng, 6),
            "severity": _severity(r),
            "acclass": (r.get("acclass") or "").strip() or "Unknown",
            "year": year,
        })
    return rows


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--since", type=int, default=2014,
                   help="Earliest collision year to keep (default 2014).")
    args = p.parse_args(argv)
    try:
        url = _resource_url(_KSI_RESOURCE_4326)
        cbytes = httpx.get(url, timeout=300, follow_redirects=True).content
        rows = _collect(io.BytesIO(cbytes), args.since)
    except Exception as exc:  # noqa: BLE001 — offline-safe: never fail the chained target
        print(f"fetch_ksi: skipped (no network / API error: {exc}). "
              "The synthetic road-risk fallback covers dev/CI.")
        return 0
    if not rows:
        print("fetch_ksi: no downtown rows returned; leaving any existing slice in place.")
        return 0
    rows.sort(key=lambda r: (-r["severity"], -r["year"]))   # strongest signal survives the cap
    rows = rows[:MAX_OUT]
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "ksi__downtown.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["lat", "lng", "severity", "acclass", "year"])
        w.writeheader()
        w.writerows(rows)
    fatals = sum(1 for r in rows if r["severity"] == 3)
    yrs = sorted({r["year"] for r in rows})
    print(f"ksi: {len(rows)} downtown KSI records ({fatals} fatal-weighted), "
          f"years {yrs[0]}-{yrs[-1]} -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
