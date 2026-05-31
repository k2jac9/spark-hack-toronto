# 0015 — Shelter as a real lever, smoothed staffing, and J cost-transparency

Status: Accepted
Date: 2026-05-30

## Context

An audit of the Urban-OS egress dashboard surfaced a cluster of related defects that
all undermined the demo's headline claim — "the optimizer recommends a genuine,
auditable intervention." They had to be fixed together because they share one data
path (the cost model → optimizer → `/simulate` contract → UI → narrator):

1. **Shelter was all-cost, never chosen.** The objective was
   `J = delay + hold + exposure + staffing`. No lens priced the crowd-safety **risk**
   field into `J`, yet dividing that risk field is the *entire* benefit of deploying
   shelter. So shelter only ever added staffing cost and the optimizer correctly but
   uselessly always chose `shelter = 0`. The shelter lever was dead weight.

2. **Staffing was non-monotonic in release.** `WeatherLens` staffing was
   `crowd_size · shelter · rain_minutes · _SHELTER_COST` — keyed to the *static* crowd
   size, independent of how many people were actually held in the rain. Longer
   staggered releases (which empty the platforms *before* the rain peak) made shelter
   look up to ~3× **more** expensive, the opposite of physical reality, producing an
   incoherent cost curve.

3. **The objective was invisible.** `/simulate` and `/optimize` surfaced only the
   peak and the net saving. The 2100/min hold cost and the shelter/safety terms were
   nowhere on screen, so "longer release is always better by the heatmap" could not be
   reconciled with "the optimizer picks 16, not 20."

4. **Map ≠ engine (a real graph bug).** `EventSurge.configure` seeded the egress wave
   by raw lat/lng proximity across **all** nodes, sinks included. `sink_west` —
   orphaned on the published graph (0 edges) — received ~243 people injected directly
   and never drained. The drawn graph did not equal the simulated routing.

5. **UI/narrator honesty.** The banner claimed "100% on-device" (compute is
   server-side); the narrator labelled the net-`J` saving as "commuter-delay cost"
   (it nets the hold penalty and weather/safety terms); rounding was inconsistent
   (0.9 vs 0.94 for the same peak); congestion was colour-only; the map was not a
   labelled landmark; the "✓ grounded" tag over-claimed.

## Decision

### 1. Price crowd-safety risk into `J` (`lenses/economic.py`)

`EconomicLens.observe` now emits a per-step `safety_cost = (Σ_nodes risk)·dt ·
VALUE_OF_SAFETY`, and `EconomicLens.cost` sums it alongside `delay_cost`. Because
`observe` runs as the loop's last phase — *after* `WeatherLens.couple` has multiplied
`risk` by `(1 + 0.6·wet)` — the integrated risk already reflects weather amplification.
Shelter cuts `wet`, so it directly lowers this term: the shelter lever finally has a
benefit the optimizer can see.

`VALUE_OF_SAFETY = 350.0` $/(risk·person·minute). Synthetic, plausibility-flagged.

### 2. Re-base staffing on the in-system rained-on load (`lenses/weather.py`)

`WeatherLens.observe` records `shelter_load_min = in_system · rain_at(t)` per step.
`WeatherLens.cost` integrates it: `staffing = shelter · _SHELTER_COST ·
Σ(in_system·rain·dt)`. Staffing now scales with the people *actually present in the
rain*, so a longer hold (which drains the platforms before the rain peak) makes shelter
**cheaper** — the curve is monotonically decreasing in release, as physics demands.

`_SHELTER_COST` raised `0.04 → 0.14`; `_EXPOSURE_COST` lowered `0.10 → 0.05`.

### 3. Calibration result

With `(VALUE_OF_SAFETY, _SHELTER_COST, _EXPOSURE_COST) = (350.0, 0.14, 0.05)` on the
default downtown scenario (`crowd 45k`, rain `width 20`):

- **Default optimum (rain intensity 0.7): release = 16 min, shelter = 1.0**,
  J ≈ \$45.6k vs do-nothing J ≈ \$139k → **net benefit ≈ \$94k**.
- **Shelter starts being chosen at rain intensity ≈ 0.10** (it is 0 at ≤ 0.05) and is
  **monotone non-decreasing** in intensity thereafter (0.25 → 1.0). At a fixed release,
  staffing is monotone *decreasing* in release. Shelter is never strictly dominated:
  at heavy rain the best (release, shelter > 0) beats the best (release, shelter = 0).

This is a genuine interior trade-off: mild drizzle → no shelter (staffing not worth it);
heavy rain → full shelter (the safety + exposure benefit beats staffing).

### 4. Surface the objective (`optimize.py`, `api.py`)

`optimize.cost_breakdown(result, lenses)` decomposes `J` into
`{delay, hold, exposure, staffing, safety, total}` from the per-step metric series the
lenses already emit (no re-run; lenses remain the single source of truth for their own
cost). `OptResult` carries `baseline_breakdown` / `best_breakdown`; `/optimize` returns
`cost_breakdown` + `baseline_cost_breakdown`; `/simulate` returns a breakdown for the
exact `(release, shelter)` requested. `total` equals `objective()` for the demo stack
(all weights 1.0), asserted by tests.

### 5. `/simulate` reproduces the optimizer (`api.py`)

`/simulate` gains `shelter_fraction: float = Query(0.0, ge=0.0, le=1.0)` (finite-checked
like `release_minutes`), passed into the params dict and echoed back. Any
`(release, shelter)` the optimizer evaluates is now reproducible on the map.

### 6. Fix the sink-injection bug (`lenses/event_surge.py`)

`EventSurge.configure` zeroes the `is_sink` entries of the spatial-decay weights
*before* normalizing (`w = np.where(substrate.is_sink, 0.0, w)`). The wave is seeded
only at non-sink nodes; crowd reaches sinks solely via real edges. `sink_west`'s
standing load is now 0.0 every step — **map routing == engine routing**.

### 7. UI + narrator honesty (`static/urban_os.html`, `narrate.py`)

- **Shelter slider** (0–1, 0.25 steps) wired to `/simulate`; the optimize panel shows
  the chosen shelter and reflects both levers on the sliders.
- **Cost-breakdown table** rendered from `/optimize` so the recommendation is
  reproducible from on-screen numbers.
- **One rounding convention per quantity** — peak/risk to 2 dp (`0.94×`) everywhere,
  money to whole `$k` matching the narrator's figures.
- **Banner** reworded "100% on-device · offline" → "Offline vector map · runs on the
  local box" (only the map is offline; compute is server-side).
- **Narrator** calls the saving the **net intervention benefit** (not "commuter-delay
  cost") and reflects both levers (release + shelter). The hallucination guard is
  unchanged — every figure still traces to `figures` (added `shelter_pct`).
- **"✓ grounded" tooltip** clarifies it means "numbers verified against the simulation
  run," not end-to-end optimizer soundness. The verifier is not loosened.
- **Accessibility** — the map is wrapped in `<main aria-label="Downtown egress map">`;
  a per-node text **readout table** gives a non-colour congestion encoding (peak first,
  over-capacity flagged); control-row labels demoted from `<h2>` to non-heading `.lbl`
  (with `role="group"` + `aria-labelledby`) so the heading outline lists only real
  sections.

## Audit findings → change

| Finding | Resolved by |
|---|---|
| Shelter all-cost, never chosen | §1 safety term in `J` |
| Staffing non-monotonic in release | §2 in-system staffing basis |
| Shelter not a genuine interior optimum | §3 calibration |
| `J` invisible; heatmap ⊥ optimizer pick | §4 cost-breakdown on `/simulate` + `/optimize` |
| Optimizer runs not reproducible on the map | §5 `shelter_fraction` on `/simulate` |
| Map ≠ engine; `sink_west` ~243 stranded | §6 zero sinks before seeding |
| Banner over-claims on-device compute | §7 banner reword |
| Saving mislabelled "commuter-delay cost" | §7 narrator wording |
| Inconsistent rounding | §7 one convention per quantity |
| Congestion colour-only; map not a landmark; heading outline noisy; tag over-claims | §7 readout table, `<main>`, `.lbl`, tooltip |

## Consequences

- The shelter lever is now load-bearing; the default demo recommendation includes
  shelter, which is the intended story (rain → cover the crowd).
- `cost_breakdown` is derived (delay/safety/exposure read directly; staffing and hold
  by attribution) so no cost formula is duplicated outside its lens.
- Calibration constants remain synthetic and plausibility-flagged — not ground-truth.
- The offline + hallucination-guard invariants are preserved; only the cost model,
  the `/simulate` contract (additive), the UI, and the narrator wording changed.
