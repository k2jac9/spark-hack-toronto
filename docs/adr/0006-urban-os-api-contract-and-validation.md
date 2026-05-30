# ADR-0006 — Harden the Urban-OS API surface and pin it with a contract lane

- **Status:** accepted
- **Date:** 2026-05-30

## Context

`urban_os/api.py` is the thin FastAPI layer the offline map UI talks to and the
seam other workstreams (UI, narrator, optimizer) couple against. Four endpoints
(`/health`, `/scenario`, `/simulate`, `/optimize`) plus the map page and the
`/static` offline mount carry every value the demo renders. Two classes of risk
sit on this surface:

1. **Boundary correctness.** The kernel runs on numpy; numpy scalars are *not*
   valid JSON (and `NaN`/`Infinity` are not legal JSON tokens even when an
   encoder emits them). The project invariant is explicit: "every numeric payload
   is converted from numpy to native Python … converting at the boundary is the
   only safe place." An audit found a real leak: `optimize.OptResult.to_dict()`
   carries lever values straight off an `np.arange` grid, so `optimization.params`
   and every `trials[].params` held `numpy.float64`. It JSON-encodes *today* only
   because numpy floats subclass `float`; it still violates the invariant and
   would break a stricter encoder or any consumer that type-checks.

2. **Input robustness.** `/simulate` takes two client-controlled levers
   (`release_minutes`, `frame_every`). Out-of-range values, non-finite floats
   (`release_minutes=nan` satisfies neither `ge` nor `le` in some stacks), and a
   `frame_every` larger than the run length must all degrade gracefully — never a
   500 with a leaked stack trace, never an empty frame list.

There was no regression lane pinning the *shape* of these responses, so a future
edit to the kernel, optimizer, or narrator could silently change a key the UI
depends on and only surface as a broken demo.

## Decision

**Validation + graceful errors (api.py).**

- Keep `Query(ge=, le=)` as the declarative first gate (out-of-range → 422). Add
  an explicit `math.isfinite` guard on `release_minutes` (rejects `nan`/`inf`
  with a 422 and a clear detail), and clamp `frame_every` to the horizon so a
  max-bound value still yields at least the opening frame.
- Wrap the `/simulate` kernel run and the `/optimize` optimize+narrate pipeline
  in `try/except` that re-raises as `HTTPException(500, detail=...)` — a clean
  error to the client, no stack-trace leak. `index()` raises a 500 with a clear
  detail if the page asset is unreadable instead of returning a blank body.

**Native-Python boundary (api.py).**

- `_r()` now coerces through `float()` (collapsing numpy scalars) and clamps
  non-finite values to `0.0`, guaranteeing every rounded field is a finite native
  float.
- A new recursive `_native()` sanitizer coerces an arbitrary numpy-laced
  structure to native `int`/`float`/`bool`/`str`/`None`. It is applied to the two
  payloads sourced from code this workstream may **not** edit — `opt.to_dict()`
  and `insight.figures` — fixing the `numpy.float64` leak at the boundary rather
  than in `optimize.py`. Ordering matters: python `bool` and `np.bool_` are
  checked before the `numbers.Integral`/`Real` branches (numpy bool is neither).

**Contract / regression lane (tests/test_urban_api_contract.py).** A new
`TestClient` lane, companion to `test_urban_api.py` (left untouched), that pins:

- the exact key *sets* of every endpoint response and nested object;
- **no numpy leakage** — a structural walk rejecting any `np.generic` leaf and
  any non-finite float (stronger than `json.dumps`, which numpy floats survive);
- **people conservation** — `/simulate`'s `in_system` series rises from
  near-empty to a peak and drains back down, and peak in-system load never
  exceeds the scenario `crowd_size`;
- **peak structure** — the reported peak equals the max congestion actually in
  the frames and names a real node; the optimizer's best is never worse than the
  do-nothing baseline; reported `savings == baseline_J - best_J`;
- **grounded + cited insight** — `grounded` is a bool, every integer cited in the
  insight is a real figure value, and a stubbed LLM pins the `grounded is True`
  branch end-to-end (plus a liar-LLM test proving a fabricated number is rejected
  back to the deterministic fallback);
- **offline static** — the page references only vendored assets (no CDN) and
  `/static/vendor/maplibre-gl.{js,css}` serve from this origin.

## Consequences

- The `numpy.float64` leak in the `/optimize` payload is closed at the boundary;
  the contract lane's structural walk now fails loudly if any numpy scalar ever
  reappears in any endpoint, in this or a dependency module.
- Endpoint response keys and the `_lenses()` signature are unchanged (UI and other
  workstreams unaffected); the hardening is purely additive (validation,
  sanitization, tests). `test_urban_api.py` still passes verbatim.
- `/simulate` and `/optimize` can no longer 500 with a raw stack trace on an
  internal failure, and `/simulate` rejects non-finite input explicitly.
- We chose to sanitize at the API boundary rather than fix `optimize.py`/`narrate.py`
  because those modules are owned by other workstreams this iteration; `_native()`
  is the documented, single place where the numpy→native contract is enforced, so
  the fix is local and won't collide. If lever grids later become native floats
  upstream, `_native()` becomes a cheap no-op rather than a needed correction.
- The grounded-path test injects a deterministic stub LLM (no network), so the
  `grounded is True` branch is covered in CI even though the real model is only
  reachable on the GX10; the suite stays fully offline and fast.
