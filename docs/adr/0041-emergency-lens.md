# ADR-0041 — Emergency lens (TFS fire-incident response density)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** the data-driven roadmap
(`docs/research/tpf-and-data-driven-lenses.md` §6, the "real source/demand lenses" Fit C track),
ADR-0036 (RoadRisk display lens — the static-density template this clones), ADR-0030
(MobilityDemand display lens — the original Fit C pattern), the EMS-access overlay (the access
twin this pairs with), ADR-0014 (two-index civic risk — the *different* "Safety" axis this is
distinct from)

## Context

The shell's intelligence lenses cover the crowd crush, transit, civic activity, EMS access,
emissions, micromobility demand, transit supply, historical road danger (KSI), and active road
disruption — but nothing captures **where the city's emergency-response load actually lands**.
The City publishes Toronto Fire Services *Fire Incidents* (`fire-incidents`): real, geocoded,
severity-bearing incident-response records. Overlaying that on the egress substrate answers a
genuinely new question — *does the staggered-release lever funnel the crowd through the areas the
city is called to most often?* — distinct from the civic Safety index (food inspections + permits)
and distinct from the EMS-access overlay (which shows where blocked roads make help slow to
*arrive*, not where it is *called*). The two pair naturally: response **load** plus response
**access**.

## Decision

Add **`EmergencyLens`** — a Fit C, display-only advisory lens, an **exact static-density clone of
`RoadRiskLens`** (ADR-0036): a normalised per-node field rather than a time series.

- **Data.** `scripts/fetch_fire_incidents.py` streams the TFS `fire-incidents` CSV, keeps recent
  years and the downtown bbox, and writes a small committed slice
  `demo_data/emergency__downtown.csv` (`lat,lng,severity,year`; ~2500 real incident responses,
  2018–21, severity uniformly 2). Offline-safe (network failure → exit 0); the raw CSV is never
  committed.
- **Adapter.** `adapters.emergency_by_node(substrate)` loads that slice via
  `timeseries.load_station_values(key="emergency", value_col="severity")` and fuses the points onto
  the substrate by a Gaussian proximity-weighted **sum** (response load is cumulative — more
  incidents nearby ⇒ more response load), returning raw `{node_id: density}`. Synthetic
  deterministic fallback when no slice is present, so CI/dev never need real data.
- **Lens.** `EmergencyLens` bakes a **normalised 0..1** response-load field at non-sink nodes only
  (the baked array lives on `self._risk`, the *same attribute name* `RoadRiskLens` uses, so the
  static-density overlay read path in `services` is shared verbatim), writes it as its own
  `emergency` overlay in `couple()` (read-only on the crowd fields), and reports in `observe()`:
  `emergency_peak` and **`crush_emergency_exposure`** — a scale-free cosine in `[0, 1]` of how much
  the crush (`load`) overlaps the fixed response-load field (lower is safer). **No levers, zero
  cost.** Lives in `scenarios.extra_display_lenses` (excluded from the optimizer's `J`).
- **Surfaces.** `/overlays` gains a normalised `emergency` per-node field; `/lenses` gains an
  `emergency` advisory report (peak/mean exposure). The shell adds an **"Emergency"** map-heat
  button (Context group) and an "Emergency load" advisory card on the optimizer result, styled like
  the other learned/advisory cards (labelled *fire/EMS · advisory*).

## Honesty / what this signal is

The backing dataset is TFS fire-incident **responses** — which **include alarm activations and
outdoor/grass fires, not only structure fires**. So this is honestly framed as a *"where
emergencies cluster / where response load concentrates"* signal, **not a "structure-fire count"**.
The relative shape is the claim, not the absolute magnitude.

## Honesty / invariants (unchanged)

Display-only and additive: read-only on the crowd fields, no lever, no `J` term, excluded from
the objective — proven by `tests/test_emergency.py` (additivity contract: `load`/`delay_cost`/
`safety_cost` byte-identical with vs without the lens). The golden numbers (do-nothing
**J $323,222** → best **$105,050**), the 100%-offline map, and the hallucination guard are
unchanged. Real TFS responses under the demo (`DATA_DIR=demo_data`), deterministic synthetic field
in CI/dev. Suite: **+9 emergency-lens tests**, all green.
