# ADR-0021 — Kernel correctness: conservation under noise + per-State capacity overlay

**Status:** Accepted · **Date:** 2026-05-31 · **Relates:** ADR-0002 (capacitated drainage / conservation), ADR-0007 (weather lens), ADR-0011 (honest peak)

## Context

The architecture audit found two real correctness hazards in the simulation kernel
— both off the path the existing tests exercised, so both were silently latent:

1. **Noise broke people-conservation (High).** The time loop's optional jitter did
   `load += rng.normal(0, noise)·√(load+1)` then clipped at 0. That adds/removes
   people who were never injected and never absorbed at a sink, so the ADR-0002
   invariant (`in_system + arrived = injected`) held only on the `noise == 0` path
   the tests use. The clip-at-zero also biased mass upward asymmetrically.
2. **Cross-run state-leak hazard (High).** `WeatherLens` applied its rain "capacity
   tax" by mutating the shared `substrate.edge_cap` in place each `source()` and
   restoring it in `couple()`. The optimizer reuses one lens *instance* across all
   trials and assumed `configure` was idempotent — but the only thing keeping the
   baked array pristine between trials was that `couple` always ran. An exception
   between `source` and `couple` (or any future lens leaving `edge_cap` mutated)
   would let the next `configure` snapshot a *penalised* array as the "dry" baseline
   and compound it silently. The root cause was the kernel mutating shared substrate
   state instead of using per-run state.

## Decision

1. **Conservative noise.** Make the jitter zero-sum (`eps -= eps.mean()`) so it
   *redistributes* load rather than creating/destroying it, and after the
   non-negativity clip, rescale `load` to restore the exact pre-noise total.
   People-conservation now holds **under noise**, not only at `noise == 0`.
2. **Per-`State` capacity multiplier.** Add `State.edge_cap_mult` (an `(E,)` array,
   reset to `1.0` each step by the loop). `transport` reads
   `substrate.edge_cap × edge_cap_mult`. Lenses that tax throughput **multiply into
   the multiplier** during `source()` instead of mutating the substrate. `WeatherLens`
   now does this and holds **no mutable cross-run state** (its `configure` snapshot is
   gone), so the substrate is immutable across steps, runs, and optimizer trials —
   the "configure is idempotent" assumption is now true *by construction*, not by luck.

## Consequences

- The kernel's central conservation claim is robust on every path; a new
  parametrised test asserts it across seeds and noise levels.
- The snapshot/restore dance and the compounding hazard are gone; lens reuse across
  optimizer trials is provably safe. Capacity taxes also now **compose** (multiple
  lenses multiply into one multiplier) instead of overwriting each other.
- **Behaviour-preserving:** with no rain the multiplier is all-ones (no-op), and the
  rainy path produces the identical effective `edge_cap` as the old in-place write —
  `make urbanos-cli` headline is unchanged (3.73× / 14-min / −67% / ~$218k).

## Tests

- `test_per_step_conservation_exact_with_noise` (new) — conservation under noise.
- `test_substrate_edge_cap_never_mutated` (replaces the old "restored after each
  step") — the substrate is byte-identical before/after a rainy run.
- `test_cap_penalty_magnitude_is_exact` / `test_configure_missing_is_handled_gracefully`
  updated to assert the tax lands on `edge_cap_mult`, never on `substrate.edge_cap`.
