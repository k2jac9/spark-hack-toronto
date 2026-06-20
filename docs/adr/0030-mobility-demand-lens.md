# ADR-0030 — MobilityDemand lens: Bike Share trip-origin demand as an advisory display overlay (Fit C)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** ADR-0029 (TransitLoad — the sibling Fit C source lens), ADR-0028 (learned-dynamics floor — the opt-in/advisory honesty template), ADR-0022 (one shared lens stack), ADR-0014 (two-index civic risk) · **Research:** `docs/research/tpf-and-data-driven-lenses.md` §6 "Fit C", §7 "Honesty constraints"

## Context

The data-driven roadmap (§6) lists **Fit C** — "real source/demand lenses" — as the *low-risk, high-credibility, no-TPF* track that makes the demo more real today. Phase 1 shipped `CongestionNowcastLens` (reads observed TMC counts to score the kernel) and ADR-0029 shipped `TransitLoadLens` (writes measured boardings as a real `source`). The roadmap's third Fit C lens (§6: "**MobilityDemand lens** — Bike Share OD as a real demand field / display overlay") is the natural companion: a Bike Share trip **origin** is a local "demand to leave" event, so trip-starts per station per 15-min bin form a real micromobility **demand** field — *where people want to leave from*, alongside *where the crush actually piles up*.

Unlike `TransitLoadLens`, this is a **display overlay, not a source**: injecting bike-share demand as kernel `load` would conflate two different quantities (a *wish to leave* vs *people present in the egress system) and would move crowd fields — and we don't want a display lens touching a headline number. So MobilityDemand is **read-only on the crowd fields** and writes only its own advisory `bike_demand` overlay, exactly the discipline `CongestionNowcastLens` uses for its `observed_load` overlay. The only design questions are where (not) to lift demand, how to keep it strictly additive, and how to be honest that there is no committed slice yet.

## Decision

**`urban_os/lenses/mobility_demand.py` — `MobilityDemandLens(Lens)`, a `couple`/`observe` display lens.**

1. **Demand display overlay (no source, no `load` write).** Construct with the `{node_id: {minute: count}}` demand series (the same shape CongestionNowcast/TransitLoad consume — see `adapters.bikeshare_demand_by_node`). `configure` bakes per-bin per-node demand arrays; `couple` writes, for the demand bin nearest sim-time `t`, ONLY `state.fields["bike_demand"]`. It never reads or mutates `load`/`congestion`/`risk`, so it cannot perturb the kernel or any other lens.
2. **Never seed a sink.** Like `EventSurge`/`TransitLoad`, only NON-SINK nodes carry demand — an exit/home line is not an origin where someone decides to leave.
3. **No lever, no J term, excluded from `J`.** `levers()` is empty and `cost()` is `0.0`, and the lens lives in `scenarios.extra_display_lenses`, which is deliberately excluded from the optimizer's objective `J`. So it is **display-only**, cannot change the optimizer's chosen intervention or any headline dollar figure. `observe` reports advisory metrics only: `bike_demand_peak` (highest single-node trip-origin demand this step) and `micromobility_relief` (a scale-free cosine in `[0, 1]` measuring how much the egress crush coincides with high bike-share demand — a *relief opportunity* signal, purely informational).
4. **Grounded via `extra_display_lenses(sc)`.** When a scenario is given the lens is grounded in `bikeshare_demand_by_node(sc.substrate)` (real data, synthetic fallback offline), exactly like `CongestionNowcastLens`/`NoiseLivabilityLens`. Bare construction (no `sc`) stays synthetic/inert. The API/CLI default stacks (`default_lens_stack`) are untouched.

## Honesty notes (roadmap §7 — none regressed)

- **Default surfaces byte-identical.** The lens is additive and lives only in `extra_display_lenses` (excluded from `J`); it writes nothing to the crowd fields. The golden CLI numbers are unchanged: do-nothing **J $323,222**, best release **14 min → J $105,050** (verified byte-identical before and after).
- **Exact kernel decides (§7.1).** Read-only on `load`/`congestion`/`risk`; no learned/approximate substitution, no new J/cost term, no lever. The chosen intervention and every priced figure are unmoved (pinned by the additivity test, which proves load + the economic terms are byte-identical with the lens added).
- **Real demand, synthetic fallback until a slice (§7.2).** There is no committed Bike Share slice today, so (like the registered `ttc_ridership` dataset) the adapter supplies a deterministic synthetic series; the real-data path (`timeseries.load_counts(key="bikeshare")` → `bikeshare__*.csv`) is wired so a future committed slice lights it up with no lens or kernel change. Bare construction is a clean inert no-op; CI/dev never need real data or network.
- **Provenance honesty (§7.3).** `PROVENANCE = "synthetic/advisory"` — honest that the fallback is synthetic; a future real slice would warrant `"real/measured"` (matching the TransitLoad convention). Either way the lens is clearly advisory.
- **Boundary validation.** Negative / NaN / inf cell counts are dropped at `configure`; the baked overlay is guaranteed finite (no NaN/inf ever reaches a field). Empty/bare series are inert.
- **No private deps.** Pure numpy over public adapter data; vendors nothing.

## Verification

`tests/test_mobility_demand.py`: bare lens inert (standalone + in a full run); `couple` writes the demand overlay at non-sink nodes only (sink values ignored); nearest-bin selection; degenerate counts (negative/NaN/inf) and empty series don't raise and never emit NaN/inf; no levers / zero cost / advisory provenance; the `micromobility_relief` metric is bounded `[0, 1]`; **read-only on the crowd fields** (load + economic terms byte-identical with the lens added — the additivity contract); `extra_display_lenses(sc)` includes the grounded lens and stays additive over the full extra set; determinism; the adapter `bikeshare_demand_by_node` returns the right shape and falls back synthetically (explicit-empty + default-provider paths). The pre-existing strict `extra_lenses` set assertions stay green because this advisory lens (cost 0) is not surfaced as a priced `_EXTRA_LENS_METRIC` row. Full suite green.

## What's next (when justified)

A committed Bike Share Toronto ridership slice (`scripts/` could add a `fetch_bikeshare.py` that normalises trip-start OD into the `{location, 15-min bin, mode, volume}` shape `timeseries.load_counts` reads) would replace the synthetic fallback with measured origins — the adapter swap is the whole point of Fit C (lens and kernel unchanged). Surfacing `bike_demand` as a map heat layer (a `/overlays` field) and the `micromobility_relief` signal in the UI is a small, separate UI follow-up. Promoting demand to a *decision* objective (e.g. a bike-redeployment lever priced into `J`) would move headline numbers and so stays an explicit, separate ADR.
