# ADR-0036 — RoadRisk lens (Vision Zero / KSI collision history)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** the data-driven roadmap
(`docs/research/tpf-and-data-driven-lenses.md` §6, the "real source/demand lenses" Fit C track),
ADR-0030 (MobilityDemand display lens — the template), ADR-0032 (transit-supply overlay),
ADR-0014 (two-index civic risk — the *different* "Safety" axis this is distinct from)

## Context

The shell's intelligence lenses cover the crowd crush, transit, civic activity, EMS access,
emissions, micromobility demand, and transit supply — but nothing captures **where the road
itself is historically dangerous**. The City publishes the Vision Zero
*Motor Vehicle Collisions involving Killed or Seriously Injured Persons* (KSI) dataset: real,
geocoded, severity-bearing collision records. Overlaying that on the egress substrate answers a
genuinely new question — *does the staggered-release lever funnel the crowd through historically
dangerous intersections?* — distinct from the civic Safety index (food inspections + permits).

## Decision

Add **`RoadRiskLens`** — a Fit C, display-only advisory lens, built on the exact MobilityDemand
pattern (ADR-0030), but carrying a **static** per-node field rather than a time series.

- **Data.** `scripts/fetch_ksi.py` streams the KSI `- 4326` (WGS84) CSV, keeps recent years
  (≥2014) and the downtown bbox, weights each record by injury severity (Fatal 3 / Major 2 /
  else 1), and writes a small committed slice `demo_data/ksi__downtown.csv` (2036 records,
  ~92 KB). Offline-safe (network failure → exit 0); the raw CSV is never committed.
- **Adapter.** `adapters.road_risk_by_node(substrate)` loads that slice via
  `timeseries.load_station_values(key="ksi", value_col="severity")` and fuses the points onto the
  substrate by a Gaussian proximity-weighted **sum** (danger is cumulative — more severe nearby
  collisions ⇒ more dangerous), returning raw `{node_id: density}`. Synthetic deterministic
  fallback when no slice is present, so CI/dev never need real data.
- **Lens.** `RoadRiskLens` bakes a **normalised 0..1** danger field at non-sink nodes only,
  writes it as its own `road_risk` overlay in `couple()` (read-only on the crowd fields), and
  reports in `observe()`: `road_risk_peak` and **`crush_road_exposure`** — a scale-free cosine
  in `[0, 1]` of how much the crush (`load`) overlaps the fixed danger field (lower is safer).
  **No levers, zero cost.** Lives in `scenarios.extra_display_lenses` (excluded from the
  optimizer's `J`).
- **Surfaces.** `/overlays` gains a normalised `road_risk` per-node field; `/lenses` gains a
  `road_risk` advisory report (peak/mean exposure). The shell adds a **"Road risk"** map-heat
  button (Context group) and a "Road-risk exposure" advisory card on the optimizer result,
  styled like the other learned/advisory cards (labelled *Vision Zero · advisory*).

On the demo substrate the danger concentrates on real high-collision corridors — **King, Queen,
Union, St Andrew** — and the do-nothing crush reads ~0.71 peak exposure, i.e. the egress does
funnel the crowd through dangerous places.

## Honesty / invariants (unchanged)

Display-only and additive: read-only on the crowd fields, no lever, no `J` term, excluded from
the objective — proven by `tests/test_road_risk.py` (additivity contract: `load`/`delay_cost`/
`safety_cost` byte-identical with vs without the lens). The golden numbers (do-nothing
**J $323,222** → best **$105,050**), the 100%-offline map, and the hallucination guard are
unchanged. Real KSI under the demo (`DATA_DIR=demo_data`), deterministic synthetic field in
CI/dev. Suite: **+14 road-risk tests**, all green.
