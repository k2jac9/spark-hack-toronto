# ADR-0029 — TransitLoad lens: a real/measured background-ridership source (Fit C)

**Status:** Accepted · **Date:** 2026-06-19 · **Relates:** ADR-0028 (learned-dynamics floor — the opt-in/advisory honesty template), ADR-0022 (one shared lens stack), ADR-0014 (two-index civic risk), ADR-0002 (capacitated substrate) · **Research:** `docs/research/tpf-and-data-driven-lenses.md` §6 "Fit C", §7 "Honesty constraints"

## Context

The data-driven roadmap (§6) lists **Fit C** — "real source/demand lenses" — as the *low-risk, high-credibility, no-TPF* track that makes the demo more real today. Phase 1 shipped `CongestionNowcastLens`, which *reads* the observed Toronto TMC 15-min counts (`adapters.observed_counts_by_node`) to score the kernel against ground truth. The natural companion (§6: "**TransitLoad lens** — `source()` injects measured TTC boardings at relay nodes") *writes* the same series: it adds the measured boardings as honest background ridership — the people entering the transit system on top of the event-egress wave EventSurge already injects.

Unlike ADR-0028's learned floor, there is no model and no fit here: this is **real, metered data injected as a source term**, exactly the way `EventSurge` meters a venue crowd. The only design questions are how to convert a 15-min count into a per-step inflow honestly, where (not) to inject it, and how to keep it from touching any headline number.

## Decision

**`urban_os/lenses/transit_load.py` — `TransitLoadLens(Lens)`, a `source`-only lens.**

1. **Real/measured source.** Construct with the `{node_id: {minute: count}}` series (the same shape CongestionNowcast consumes). `configure` bakes per-bin per-node count arrays; `source` injects, for the observed bin nearest sim-time `t`, the per-step inflow **`count / 15 * dt * scale`** (people-per-minute × minutes-per-step × a documented `scale`, default `1.0`) into `state.fields["load"]`. The conversion reads the live `dt`, so per-step mass is correct at any step size.
2. **Never seed a sink.** Like `EventSurge`, only NON-SINK nodes are seeded — a slug placed directly on a sink would be absorbed without routing through the real graph (the drawn graph would not equal the simulated routing). Sinks are reached only via real edges.
3. **No lever, no J term.** `levers()` is empty and `cost()` is `0.0`. It is a **realism source, not a priced or controllable lever**, so it can never change the optimizer's chosen intervention or any headline dollar figure. `observe` reports `transit_boardings` (people injected this step) for transparency only.
4. **Opt-in, off by default.** `transit_load_enabled()` reads `URBANOS_TRANSIT_LOAD` (mirrors `learned_dynamics_enabled`). `default_lens_stack(sc, transit_load=False)` is the default; the CLI exposes `--transit-load` (default from the env flag). The API is untouched — it keeps calling `default_lens_stack` with the default `transit_load=False`.

## Honesty notes (roadmap §7 — none regressed)

- **Default surfaces byte-identical.** With the flag off the lens is **not even constructed**, so the default stack is the pre-existing one. The golden CLI numbers are unchanged: do-nothing **J $323,222**, best release **14 min → J $105,050** (verified before and after, pinned by `test_default_stack_golden_numbers_unchanged`).
- **Exact kernel decides (§7.1).** Even when ON this only adds a *real* source term; the kernel still moves and prices every person exactly. No learned/approximate substitution, **no new J/cost term**, no lever — the chosen intervention and every priced figure are unmoved (pinned by `test_transit_load_adds_no_cost_and_no_lever_when_opted_in`).
- **Opt-in + CPU fallback (§7.2).** Off by default; gated behind `URBANOS_TRANSIT_LOAD`. Bare construction (no series) is a clean inert no-op; offline the adapter supplies a deterministic synthetic series, so CI/dev never need real data or CUDA.
- **Provenance honesty (§7.3).** Stamped `provenance="real/measured"` — *distinct* from learned_dynamics' `learned/approximate` — so this metered data is never mistaken for a fit.
- **Boundary validation.** A non-finite/negative `scale` raises at construction; negative/NaN/inf cell counts are dropped at `configure`; the injected load is guaranteed finite (no NaN/inf ever reaches the kernel).
- **No private deps.** Pure numpy metering of public adapter data; vendors nothing.

## Verification

`tests/test_transit_load.py`: bare lens inert (standalone + in a full run); `source` injects the documented `count/15*dt*scale` mass at non-sink nodes only (sink counts ignored); dt/scale scaling; nearest-bin selection; degenerate counts (negative/NaN/inf) and empty series don't raise and never emit NaN/inf; invalid scale rejected; no levers / zero cost / provenance label; **off-by-default wiring** (`default_lens_stack(sc)` has no `transit_load`, `transit_load=True` appends exactly one); env-flag parsing; **golden-number invariance** of the default stack (J $323,222 → $105,050); no-cost/no-lever even when opted in; determinism. Full suite green.

## What's next (when justified)

A real TTC GTFS/boardings slice on the box would replace the synthetic fallback with measured ridership (the adapter swap is the whole point of Fit C — lens and kernel unchanged). Companion Fit C lenses the roadmap lists (MobilityDemand from Bike Share OD) follow the same `source`/display-overlay pattern; each stays opt-in and unpriced unless a separate ADR promotes it to a decision objective.
