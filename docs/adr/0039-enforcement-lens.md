# ADR-0039 — Enforcement lens (automated traffic-enforcement device density)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** the data-driven roadmap
(`docs/research/tpf-and-data-driven-lenses.md` §6, the "real source/demand lenses" Fit C track),
ADR-0036 (RoadRisk display lens — the template + the road-safety triad's first axis), ADR-0038
(RoadDisruption display lens — the triad's second axis), ADR-0030 (MobilityDemand display lens),
ADR-0014 (two-index civic risk — the *different* "Safety" axis this is distinct from)

## Context

The shell's intelligence lenses cover the crowd crush, transit, civic activity, EMS access,
emissions, micromobility demand, transit supply, historical road danger (RoadRisk / KSI), and
active road disruption (closures / restrictions) — but nothing captures **where the city actively
enforces against dangerous traffic**. The City publishes the locations of its *Automated
Enforcement* devices: real, geocoded **red-light cameras** and **speed (Automated Speed
Enforcement) cameras**. Overlaying that on the egress substrate answers a genuinely new question —
*does the staggered-release lever funnel the crowd through actively enforced corridors?* — and
completes the **road-safety triad**:

- **RoadRisk** (ADR-0036) — *where the road is historically dangerous* (KSI collision history);
- **RoadDisruption** (ADR-0038) — *where the road is constrained right now* (active closures);
- **Enforcement** (this ADR) — *where the city actively enforces* (automated camera coverage).

This is a third, distinct axis from the civic Safety index (food inspections + permits, ADR-0014).

## Decision

Add **`EnforcementLens`** — a Fit C, display-only advisory lens, an **exact static-density clone of
`RoadRiskLens`** (ADR-0036), carrying a **static** per-node field rather than a time series.

- **Data.** `scripts/fetch_enforcement.py` streams the Automated Enforcement device locations
  (WGS84), keeps the downtown bbox, weights each device by type (red-light camera 2 / speed camera
  1), and writes a small committed slice `demo_data/enforcement__downtown.csv` (51 real downtown
  devices; columns `lat,lng,severity,type` where `type` is `red_light`|`speed`). Offline-safe
  (network failure → exit 0); the raw source is never committed.
- **Adapter.** `adapters.enforcement_by_node(substrate)` loads that slice via
  `timeseries.load_station_values(key="enforcement", value_col="severity")` and fuses the points
  onto the substrate by a Gaussian proximity-weighted **sum** (coverage is cumulative — more
  devices nearby ⇒ more enforced), returning raw `{node_id: density}`. Synthetic deterministic
  fallback when no slice is present, so CI/dev never need real data.
- **Lens.** `EnforcementLens` bakes a **normalised 0..1** coverage field at non-sink nodes only,
  writes it as its own `enforcement` overlay in `couple()` (read-only on the crowd fields), and
  reports in `observe()`: `enforcement_peak` and **`crush_enforcement_exposure`** — a scale-free
  cosine in `[0, 1]` of how much the crush (`load`) overlaps the fixed enforcement field. **No
  levers, zero cost.** Lives in `scenarios.extra_display_lenses` (excluded from the optimizer's
  `J`). Like the rest of the triad, the baked normalised field is stored on `self._risk` so the
  overlay helper `services.enforcement_overlay` reads it identically (`getattr(lens, "_risk", None)`).
- **Surfaces.** `/overlays` gains a normalised `enforcement` per-node field; `/lenses` gains an
  `enforcement` advisory report (peak/mean exposure). The shell adds an **"Enforcement"** map-heat
  button (Context group, after Road disruption) and an "Enforcement coverage" advisory card on the
  optimizer result, styled like the other advisory cards (labelled *cameras · advisory*).

## Honesty / invariants (unchanged)

Display-only and additive: read-only on the crowd fields, no lever, no `J` term, excluded from the
objective — proven by `tests/test_enforcement.py` (additivity contract: `load`/`delay_cost`/
`safety_cost` byte-identical with vs without the lens). The golden numbers (do-nothing
**J $323,222** → best **$105,050**), the 100%-offline map, and the hallucination guard are
unchanged. The device **locations are real** (red-light + speed cameras, `PROVENANCE =
"real/measured"`) under the demo (`DATA_DIR=demo_data`); a deterministic synthetic field stands in
in CI/dev so the lens always runs offline.
