# ADR-0024 — RAPIDS GPU accelerator seams (nx-cugraph, cuDF-via-Polars) + honest cuOpt scoping

**Status:** Accepted · **Date:** 2026-05-31 · **Relates:** ADR-0004/0009 (Rust accelerator opt-in pattern), ADR-0001 (kernel)

## Context

The README claimed RAPIDS (cuDF/cuML), `nx-cugraph`, and cuOpt as part of the stack,
but **none were wired** — no code, no deps (the team's own SCORECARD flagged this as
"DOCS-ONLY" and an honesty risk). The box is a GB10 (aarch64, driver 580, CUDA 13);
RAPIDS ships **cu12** aarch64 wheels which the driver runs forward-compatibly
(confirmed: `libcugraph-cu12` aarch64 wheels install on the box).

## Decision

Wire the accelerators that **genuinely fit**, each as an **opt-in seam with a verified
CPU fallback** (the Rust-accelerator pattern, ADR-0004/0009) so the demo/CI never
depend on a GPU, and be **honest** about the one that doesn't fit.

1. **nx-cugraph** — the substrate shortest-paths bake (`kernel/state.py`
   `multi_source_dijkstra_path_length`) calls the `cugraph` networkx backend when
   `URBANOS_GPU_GRAPH=1` and `nx-cugraph` is installed; else networkx CPU. The backend
   that ran is recorded in `state.GRAPH_BACKEND`.
2. **cuDF via Polars** — the civic ingest (`ingest/loader.py`) reads CSVs with **Polars**
   (now a core dep, CPU everywhere), using Polars' `collect(engine="gpu")` — which runs
   on **RAPIDS cuDF** — when `URBANOS_GPU_DF=1` and `cudf-polars` is installed; else
   Polars-CPU, then **pandas** (retained as the ultimate fallback so the live demo venv
   keeps working until Polars is installed). Recorded in `loader.DF_BACKEND`. The three
   paths return byte-identical rows (parity-tested) — the golden two-index numbers are
   unchanged.
3. **cuOpt — explicitly NOT wired (honest).** cuOpt solves structured LP/MILP/routing,
   not a black-box *simulation-in-the-loop* search (our `J` is produced by running the
   kernel per lever combo). Pretending it drops into `optimize()` would be the exact
   overstatement the audits flagged. `OptResult.solver` records `"grid"`; the module
   docstring documents the LP/MILP (or substrate min-cost-flow) reformulation as the
   real next step. cuML is likewise dropped from the claims (no clustering ships).

Optional GPU wheels live in **`requirements-gpu.txt`** (separate from the core lock, so
CI/dev install nothing CUDA). `make gpu-install` installs them on the box; **`make
gpu-check`** runs `scripts/gpu_check.py` and prints the backend each seam used — the
proof that the GPU path is *invoked*, not just claimed.

## Consequences

- The README moves from "DOCS-ONLY claims" to **wired, fallback-safe, opt-in, and
  box-provable** — and states plainly that the GPU win is at city scale, not on the
  17/459-node demo graphs (honest, mirroring ADR-0009's Rust note).
- CI stays green with zero GPU deps: matrix jobs install `polars` (exercising the Polars
  ingest path), the `test-locked` job and `URBANOS_DF_BACKEND=pandas` cover the pandas
  fallback, and the GPU env is off by default (`networkx`/`polars` CPU).
- Behaviour-preserving: golden civic numbers (0.593/0.113) and `make urbanos-cli`
  (3.73×/14-min/~$218k) unchanged.

## Verification

`tests/test_gpu_seams.py`: backends reported, CPU fallback identical to networkx,
Polars↔pandas row parity, env gating. Box: `make gpu-install && make gpu-check` →
expect `GRAPH_BACKEND=cugraph` and `DF_BACKEND=cudf-polars`.
