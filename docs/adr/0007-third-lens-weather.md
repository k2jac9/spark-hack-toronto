# 0007 — A third domain lens: WeatherLens (rain → slower drainage + higher crush risk)

Status: Accepted
Date: 2026-05-30

## Context

urban_os ships a four-operator **Lens** contract (`urban_os.kernel.operators.Lens`:
`configure` / `source` / `couple` / `observe`, plus optional `levers` + `cost`).
P0 shipped two lenses — `EventSurge` (the egress demand pulse, a `source` with a
staggered-release lever) and `EconomicLens` (congestion → `risk = ρ^2.5` and the
dollar cost of delay, a `couple`+`observe`+`J` term). The kernel itself owns only
`transport` (capacitated drainage downhill to sinks).

For the demo we want a **third, visibly different domain** that stresses a
different part of the contract and composes cleanly with the existing two. The
brief suggested a TransitDisruptionLens or a WeatherLens. I chose **weather
(rain)** for three reasons:

1. **It exercises a part of the contract the other two don't.** EventSurge only
   `source`s; EconomicLens only `couple`s on fields it owns. A rain lens needs to
   touch the *substrate's* link throughput (slow drainage) **and** post-process
   another lens's `risk` field — proving the contract supports a lens that reads
   and reversibly tweaks shared kernel state, not just its own fields.
2. **Demo legibility.** "It started raining, Union drains slower and the platform
   is more dangerous — here's the dollar value of opening covered queueing" is a
   one-sentence story a judge gets instantly, and it stacks on the existing
   stadium-egress scenario (rain *during* egress is the worst case).
3. **It gives the optimizer a second, independent lever** (shelter deployment)
   with its own interior optimum, mirroring EventSurge's staggered-release knob —
   useful for the multi-lever optimization story without new kernel code.

A TransitDisruptionLens (a line down, rerouting crowd onto alternates) is a
strong alternative, but it overlaps EventSurge's "where does the crowd go"
mechanics and would mostly re-route `source` injection; the weather lens covers
more *new* contract surface (capacity tax + cross-lens risk multiply).

## Decision

Add `src/urban_os/lenses/weather.py::WeatherLens` and register it in
`lenses/__init__.py` (additively; existing exports untouched).

### Operator math

Rain is a **Gaussian-in-time intensity pulse** (a passing cell):
`rain(t) = intensity · exp(−½((t − peak_time)/width)²)`, clamped to `[0, intensity] ⊆ [0,1]`.
The shelter lever removes a fraction of the rain, giving net **wetness**:
`wetness(t) = rain(t) · (1 − shelter_fraction)`.

Two physical effects, each landing in the correct operator phase:

- **`source` — slower drainage (a transient capacity tax).** The kernel's
  `transport` reads `substrate.edge_cap` *each step*, and the loop order is
  `source → transport → congestion → couple → observe`. So `source` snapshots
  the current `edge_cap`, then writes a penalised copy
  `edge_cap = dry · (1 − _MAX_CAP_PENALTY · wetness)` (≤25% slower at full rain).
  `couple` restores the snapshot. Net: rain throttles link throughput **only for
  that step's transport**, never permanently mutating the substrate other lenses
  share. We keep a pristine `dry` copy at `configure` time so the penalty is
  always derived from the dry baseline — repeated steps/runs can never compound.

- **`couple` — higher crush risk at the same density.** After `EconomicLens` sets
  the base `risk = ρ^2.5`, WeatherLens multiplies it:
  `risk ← risk · (1 + _MAX_RISK_BONUS · wetness)` (up to +60% at full rain). This
  requires WeatherLens to run **after** EconomicLens in the stack; documented in
  the module + `__init__` docstring. If no upstream lens populated `risk`,
  `State` still guarantees a zeroed `risk` field, so the multiply is a safe
  numeric no-op (tested).

**Cost (`J` term).** Two parts that trade off:
- *Exposure*: unsheltered people still in the system pay `_EXPOSURE_COST` per
  person·minute of wet exposure — the part the optimizer **shrinks** with shelter.
- *Staffing*: shelter costs `_SHELTER_COST` per person·minute of crowd covered,
  integrated over the rainy window — non-zero **only** when the lever engages.
Doing nothing pays full exposure but zero staffing; full shelter pays zero
exposure but full staffing — an interior optimum, exactly like EventSurge's
hold-discount design (ADR-0003's "honest optimum" philosophy).

All four constants (`_MAX_CAP_PENALTY`, `_MAX_RISK_BONUS`, `_EXPOSURE_COST`,
`_SHELTER_COST`) are plausibility-checked, **not** ground-truth — flagged the
same way EconomicLens flags its value-of-time.

### Wiring is an intentional fast-follow

`api.py::_lenses()` is **not** edited here (Workstream B keeps `api.py` disjoint
to avoid merge conflicts). Wiring WeatherLens into the default demo stack is a
deliberate 2-line change in `_lenses()` — append
`WeatherLens(peak_time=sc.event_end, intensity=1.0, width=20.0, crowd_size=sc.crowd_size)`
**after** `EconomicLens()` (order matters: see above). Left out by design so this
lens lands without touching the API contract; a follow-up PR flips it on.

## Roadblocks researched

- **Where to apply the drainage tax.** First instinct was to add a new "speed"
  field, but transport reads `edge_cap` directly from the substrate, not from a
  field. Reading the loop + accel signature confirmed `edge_cap` is consumed
  inside `transport`, between `source` and `couple`. Decision: scale
  `edge_cap` in `source`, restore in `couple` — the only reversible seam in the
  step that the contract exposes. Tested that the substrate is pristine after
  every run and that repeated runs don't drift.
- **Risk-multiplier test isolation.** Comparing a wet run's risk to a dry run's
  risk *also* changed the underlying load (rain slowed drainage → more load →
  higher base `ρ^2.5`), so the observed ratio (~1.75) exceeded the pure
  multiplier (1.6). Resolved by unit-testing `couple` directly against a known
  risk field, isolating the multiplier from the drainage tax — the behavioral
  "wet > dry peak risk" assertion is kept separately.

## Consequences

- **+** A third lens covering new contract surface (substrate capacity tax +
  cross-lens risk multiply), composing with the existing two with no kernel
  change. People-conservation, determinism, and substrate purity are preserved
  and regression-tested.
- **+** A second optimizer lever (shelter) with a real interior optimum.
- **−** Order dependence: WeatherLens must follow EconomicLens. Mitigated by
  docstrings, a graceful zeroed-`risk` fallback, and tests; the fast-follow
  `_lenses()` edit places it correctly.
- **−** Four more synthetic calibration constants to flag in provenance.
- Tests: `tests/test_urban_weather_lens.py` (22 cases: validation, rain profile,
  drainage tax + restore + no-compounding + conservation, risk amplification +
  exact magnitude, shelter lever/cost, observe, contract conformance, and a
  three-lens end-to-end on the real downtown substrate). Full suite green.
