# ADR-0022 — API module split + a single shared lens stack

**Status:** Accepted · **Date:** 2026-05-31 · **Relates:** ADR-0019 (benefit semantics), ADR-0006 (api contract), ADR-0008 (UI)

## Context

Two structural findings from the audits:

1. **`urban_os/api.py` was 581→666 lines**, well over the project's 500-line rule. It
   crammed app wiring, the JSON-boundary serializers, eight route handlers, *and* the
   multi-simulation "service" logic (four-lens objective, cross-domain composition).
2. **The CLI and the API each built their own lens stack.** `cli._lenses` (no Weather)
   and `api._lenses` (with Weather) plus `api._four_lens_stack` were three separate
   copies. This is the structural root of the "numbers differ by surface" footgun —
   a reader of one `_lenses` had no way to know the other existed, and they could
   drift silently.

## Decision

Extract three leaf modules and route everything through one stack builder:

- **`urban_os/serialize.py`** — `r` / `native` / `peak_dict` (the numpy→native JSON
  boundary, ADR-0006). Pure, no urban_os imports.
- **`urban_os/scenarios.py`** — `default_lens_stack(sc, *, weather, safety, business)`:
  the **single source of truth** for which lenses run, in the fixed order
  EventSurge → Economic → [Weather] → [Safety] → [Business]. Both the CLI and the API
  call it; divergence is now an explicit, visible flag, not two drifting copies.
- **`urban_os/services.py`** — the cross-domain composition (`cross_domain_components`
  the ADR-0019 shared benefit helper, `cross_domain` panel, `four_lens_*`,
  `BENEFIT_DEFINITIONS`). Unit-testable without the web layer.

`api.py` keeps only app wiring + thin route handlers and imports the rest. `cli._lenses`
and `api._lenses` are now one-line delegators to `default_lens_stack`.

## Consequences

- `api.py` drops to **447 lines** (under the 500 rule); `services.py` 152, `scenarios.py`
  56, `serialize.py` 64 — all well under.
- The CLI and API **cannot** run different stacks by accident; the CLI's omission of
  WeatherLens (and hence its different headline number vs. the :8001 UI) is now a
  documented argument (`weather=False`) in one place.
- **Behaviour-preserving:** the contract tests (`test_urban_api_contract`,
  `test_urban_api_unified`) pass unchanged, and `make urbanos-cli` is byte-identical
  (3.73× / 14-min / −67% / ~$218k). No endpoint shape changed.

## Alternatives considered

- *Leave api.py large.* Rejected: it violates a stated repo rule and the inlined
  service logic was exactly what made the benefit-number duplication (ADR-0019) easy
  to introduce.
- *A package (`api/` dir with submodules).* Heavier churn for the same result; flat
  sibling modules keep imports obvious and diffs small for a hackathon codebase.
