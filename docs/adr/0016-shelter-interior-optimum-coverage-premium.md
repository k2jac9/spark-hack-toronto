# ADR-0016 — Shelter is a genuine *interior* optimum (convex coverage premium)

## Status
Accepted. Refines the calibration in [ADR-0015](0015-shelter-as-real-lever-and-cost-transparency.md).

## Context
ADR-0015 made shelter a real, priced lever (crush-safety in `J`, smoothed
staffing). But at the default rain (intensity 0.7) the optimizer landed on a
**corner** — shelter = 100%. Inspecting the objective showed why: shelter's
staffing cost is *concave* in coverage (more shelter → faster drainage → fewer
people to staff) and its safety/exposure benefit is *also* concave (diminishing
returns). A concave `J` has its minimum at a corner, so **no constant** could
produce a partial optimum — the lever was bistable (0 or 1). That undersells the
two-lever optimization: "max out shelter" isn't a compelling "it found the sweet
spot" result.

## Decision
Add a **convex coverage premium** to the staffing cost and a **finer lever grid**:

- `weather.py`: `staffing = shelter · _SHELTER_COST · basis · (1 + _COVERAGE_PREMIUM · shelter)`.
  The `(1 + p·shelter)` factor makes the *marginal* cost of coverage **rise** with
  coverage — realistic: scaling shelter toward 100% needs disproportionately more
  marshals and covered structures. Convex cost vs concave benefit ⇒ a genuine
  **interior** minimum.
- Shelter lever grid refined 0.25 → **0.1 steps** so the optimizer can land on a
  precise partial coverage.
- Recalibrated: `_SHELTER_COST 0.14 → 0.10`, `_COVERAGE_PREMIUM = 0.9`.

**Result (default scenario, rain 0.7):** optimum = **release 16 min + shelter 0.5**,
peak 2.48× → 0.93× (−62%), net benefit ≈ \$92k. The shelter `J`-curve now has a
clean interior minimum (…48 203 → 47 715 → **47 605 @ 0.5** → 47 661 → 47 857…).

## Consequences
- The demo headline is now "the optimizer balances two levers to **50% shelter
  coverage**", not "max it out" — a stronger, more honest optimization story.
- **The two levers substitute.** A longer staggered release drains the platforms
  before the rain peak, doing some of shelter's job, so the chosen *shelter alone*
  is **not** monotone in rain (e.g. 0.3 rain → 0.6 shelter, 0.5 rain → longer
  release + 0.4 shelter). This is coherent: the **net intervention benefit** *is*
  monotone in rain (60k→108k), which is the property the test pins. Documented so
  it isn't mistaken for the non-monotonic *penalty* bug ADR-0015 fixed.
- Rain intensity is not yet a UI control, so this substitution is only visible by
  varying the scenario in code; the live demo shows the clean interior default.
