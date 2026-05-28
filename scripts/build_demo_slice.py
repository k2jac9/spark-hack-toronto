"""Build a small, committed REAL-data slice for the demo (demo_data/).

Filters the real DineSafe dataset to the downtown bbox that matches the offline
PMTiles basemap, keeps a mix of outcomes (so the map shows green + at-risk pins),
caps the size so it's repo-friendly, and preserves the real column schema so the
loader's heuristics exercise real data. Re-run to refresh.

    python scripts/download_data.py dinesafe   # or it auto-fetches below
    python scripts/build_demo_slice.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "dinesafe__real.csv"
OUT = ROOT / "demo_data" / "dinesafe__downtown.csv"
CSV_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    "b6b4f3fb-2e2c-47e7-931d-b87d22806948/resource/"
    "af0f5b8a-4b73-4a50-8781-65e949792b40/download/dinesafe.csv"
)
# Must match the PMTiles extent in scripts/build_tiles.sh.
BBOX = dict(min_lon=-79.43, min_lat=43.62, max_lon=-79.34, max_lat=43.69)
MAX_ROWS = 250


def main() -> None:
    if not RAW.exists():
        RAW.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading real DineSafe to {RAW} …")
        RAW.write_bytes(httpx.get(CSV_URL, timeout=120, follow_redirects=True).content)

    df = pd.read_csv(RAW, dtype=str).fillna("")
    df["lat"] = pd.to_numeric(df["latitude"], errors="coerce")
    df["lon"] = pd.to_numeric(df["longitude"], errors="coerce")
    downtown = df[
        df["lat"].between(BBOX["min_lat"], BBOX["max_lat"])
        & df["lon"].between(BBOX["min_lon"], BBOX["max_lon"])
        & (df["address"] != "")
    ]

    # Keep all at-risk rows (non-Pass) + a sample of Pass rows for a realistic mix.
    at_risk = downtown[downtown["inspectionStatus"] != "Pass"]
    passing = downtown[downtown["inspectionStatus"] == "Pass"]
    keep = pd.concat([at_risk.head(MAX_ROWS // 2), passing.head(MAX_ROWS // 2)])
    keep = keep.drop(columns=["lat", "lon"]).head(MAX_ROWS)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    keep.to_csv(OUT, index=False)
    print(
        f"wrote {len(keep)} rows -> {OUT.relative_to(ROOT)} "
        f"({keep['address'].nunique()} distinct addresses, "
        f"{(keep['inspectionStatus'] != 'Pass').sum()} at-risk rows)"
    )


if __name__ == "__main__":
    sys.exit(main())
