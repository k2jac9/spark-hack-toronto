"""Holdout accuracy harness for the offline geo-resolver — measure it against ground truth.

Loads the committed intersection gazetteer, then for a deterministic sample re-resolves each
intersection **from its description string alone** (discarding the known coordinate) and
measures the metre error against the truth — including swapped-order and long-form variants
that exercise the canonical-key path. Emits a fallout report (the misses) for audit and
prints the headline numbers.

It is a reporting tool, **never fails the build**: offline / empty gazetteers → it prints a
note and exits 0 (the CI assertions live in ``tests/test_georesolve.py``). The raw datasets
are never touched — it reads only the committed ``demo_data/`` slice.

    python scripts/validate_gazetteers.py
"""
from __future__ import annotations

import csv
import math
import re
import sys
from pathlib import Path

# Allow running as a plain script without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from urbanos.risk.ingest import georesolve as gr  # noqa: E402
from urbanos.risk.graph.builder import _DIRECTIONS, _STREET_TYPES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo_data"
INTERSECTIONS = DEMO / "intersections__downtown.csv"
REPORT = DEMO / "gazetteer_validation_report.csv"

MAX_SAMPLES = 300        # deterministic stride keeps the report tiny + the run fast
TOL_M = 5.0              # a variant must resolve within this many metres of the truth
MAX_REPORT_ROWS = 60     # cap the committed CSV; over-tolerance misses are kept first

# Inverse of the canonical folds, to synthesise a long-form variant (ST -> STREET, W -> WEST).
_LONGFORM = {short: long for long, short in {**_STREET_TYPES, **_DIRECTIONS}.items()}


def _metres(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Equirectangular metre distance — exact enough at city scale."""
    r = 6371000.0
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    y = math.radians(lat2 - lat1)
    return r * math.hypot(x, y)


def _swapped(desc: str) -> str:
    parts = [p.strip() for p in desc.split("/") if p.strip()]
    return " / ".join(reversed(parts))


def _longform(desc: str) -> str:
    return re.sub(r"\b\w+\b", lambda m: _LONGFORM.get(m.group(0).upper(), m.group(0)), desc)


def main() -> int:
    if not INTERSECTIONS.exists():
        print(f"validate_gazetteers: skipped (no committed slice at {INTERSECTIONS}).")
        return 0
    resolver = gr.OfflineGeoResolver(gr.load_gazetteers(DEMO))
    rows = list(csv.DictReader(INTERSECTIONS.open(encoding="utf-8")))
    if not rows:
        print("validate_gazetteers: skipped (empty slice).")
        return 0
    stride = max(1, len(rows) // MAX_SAMPLES)
    sample = rows[::stride]

    errors: list[float] = []
    by_provenance: dict[str, int] = {}
    fallout: list[dict] = []
    total = 0
    for row in sample:
        try:
            tlat, tlng = float(row["lat"]), float(row["lng"])
        except (KeyError, ValueError):
            continue
        desc = row.get("desc", "")
        for label, variant in (("orig", desc), ("swap", _swapped(desc)), ("long", _longform(desc))):
            total += 1
            res = resolver.resolve({"intersection_desc": variant})
            by_provenance[res.provenance] = by_provenance.get(res.provenance, 0) + 1
            if res.lat is None:
                fallout.append({"desc": variant, "variant": label, "reason": "unresolved",
                                "provenance": res.provenance, "metres": "", "matched": ""})
                continue
            err = _metres(tlat, tlng, res.lat, res.lng)
            if err <= TOL_M:
                errors.append(err)
            else:
                fallout.append({"desc": variant, "variant": label, "reason": "over_tolerance",
                                "provenance": res.provenance, "metres": round(err, 1),
                                "matched": res.matched or ""})

    resolved = len(errors)
    fell_out = len(fallout)
    p50 = _pct(errors, 50)
    p95 = _pct(errors, 95)
    print(f"validate_gazetteers: {total} resolutions over {len(sample)} sampled intersections")
    print(f"  resolved within {TOL_M:.0f} m: {resolved} ({100*resolved/total:.1f}%)")
    print(f"  fallout (unresolved + over-tolerance): {fell_out} ({100*fell_out/total:.1f}%)")
    print(f"  metre error  p50={p50:.2f}  p95={p95:.2f}")
    print(f"  by provenance: {dict(sorted(by_provenance.items()))}")

    # Keep the actionable over-tolerance collisions first, then a sample of unresolved noise.
    fallout.sort(key=lambda r: r["reason"] == "unresolved")
    written = fallout[:MAX_REPORT_ROWS]
    with REPORT.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["desc", "variant", "reason", "provenance", "metres", "matched"])
        w.writeheader()
        w.writerows(written)
    print(f"  fallout report ({len(written)} of {fell_out} rows) -> {REPORT}")
    return 0


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = min(len(s) - 1, int(round((pct / 100.0) * (len(s) - 1))))
    return s[k]


if __name__ == "__main__":
    sys.exit(main())
