# ADR-0040 — BikeTheft lens (reported bicycle-theft density)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** the data-driven roadmap
(`docs/research/tpf-and-data-driven-lenses.md` §6, the "real source/demand lenses" Fit C track),
ADR-0036 (RoadRisk lens — the static-density template this clones exactly), ADR-0038
(RoadDisruption lens — the other static-field clone), ADR-0030 (MobilityDemand display lens — the
bike-demand pair), ADR-0037 (Footfall display lens — the foot-traffic pair)

## Context

The shell's intelligence lenses cover the crowd crush, transit, civic activity, EMS access,
emissions, micromobility demand, transit supply, ambient pedestrian footfall, and where the road
is historically dangerous (Vision Zero / KSI) or currently constrained (road restrictions). But
nothing captures a **property-crime / cycling-safety** axis: *where bikes actually get stolen*.
Toronto Police publish the *Bicycle Thefts* dataset: real, geocoded reported bicycle-theft
records. Overlaying that on the egress substrate answers a genuinely new question — *does the
staggered-release lever funnel the crowd through bike-theft hotspots?* — distinct from the civic
Safety index (food inspections + permits) and from the road-danger axes (RoadRisk / RoadDisruption).
It pairs naturally with the **bike-demand** (MobilityDemand, ADR-0030) and **footfall** (ADR-0037)
lenses: *where people ride and leave bikes* vs. *where those bikes get stolen*.

## Decision

Add **`BikeTheftLens`** — a Fit C, display-only advisory lens, built on the EXACT RoadRisk
pattern (ADR-0036): a **static** per-node field rather than a time series.

- **Data.** `scripts/fetch_bike_theft.py` streams the Toronto Police *Bicycle Thefts* feed, keeps
  recent years and the downtown bbox, and writes a small committed slice
  `demo_data/bike_theft__downtown.csv` (2500 real reported downtown thefts 2024-26; columns
  `lat,lng,severity,year`, `severity` uniformly 1 — a count density). Offline-safe (network
  failure → exit 0); the raw feed is never committed.
- **Adapter.** `adapters.bike_theft_by_node(substrate)` loads that slice via
  `timeseries.load_station_values(key="bike_theft", value_col="severity")` — the same mechanism
  `road_risk_by_node` uses — and fuses the points onto the substrate by a Gaussian
  proximity-weighted **sum** (theft density is cumulative — more thefts nearby ⇒ a worse hotspot),
  returning raw `{node_id: density}`. Synthetic deterministic fallback when no slice is present, so
  CI/dev never need real data.
- **Lens.** `BikeTheftLens` bakes a **normalised 0..1** theft field at non-sink nodes only,
  writes it as its own `bike_theft` overlay in `couple()` (read-only on the crowd fields), and
  reports in `observe()`: `bike_theft_peak` and **`crush_bike_theft_exposure`** — a scale-free
  cosine in `[0, 1]` of how much the crush (`load`) overlaps the fixed theft field (lower is
  safer). The baked field is stored on `self._risk` (the same attribute name RoadRisk uses) so the
  overlay helper reads it identically. **No levers, zero cost.** Lives in
  `scenarios.extra_display_lenses` (excluded from the optimizer's `J`).
- **Surfaces.** `/overlays` gains a normalised `bike_theft` per-node field; `/lenses` gains a
  `bike_theft` advisory report (peak/mean exposure). The shell adds a **"Bike theft"** map-heat
  button (Context group) and a "Bike-theft exposure" advisory card on the optimizer result, styled
  like the other learned/advisory cards (labelled *theft · advisory*).

On the demo substrate the theft density concentrates on the busy downtown corridors where bikes
are parked, so the do-nothing crush reads a non-trivial peak exposure — i.e. the egress does
funnel the crowd through bike-theft hotspots.

## Honesty / invariants (unchanged)

Display-only and additive: read-only on the crowd fields, no lever, no `J` term, excluded from
the objective — proven by `tests/test_bike_theft.py` (additivity contract: `load`/`delay_cost`/
`safety_cost` byte-identical with vs without the lens). The golden numbers (do-nothing
**J $323,222** → best **$105,050**), the 100%-offline map, and the hallucination guard are
unchanged. Real reported thefts under the demo (`DATA_DIR=demo_data`), deterministic synthetic
field in CI/dev.
