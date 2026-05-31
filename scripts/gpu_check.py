"""Prove which compute backend each RAPIDS seam actually used (run on the box).

    URBANOS_GPU_GRAPH=1 URBANOS_GPU_DF=1 PYTHONPATH=src python scripts/gpu_check.py
    # or simply:  make gpu-check

Exercises the two genuinely-wired GPU seams and reports the backend that RAN — so a
judge / teammate can verify the GPU path is invoked, not just claimed. Exits 0
regardless (CPU fallback is a valid, honest outcome off the box); the VALUE is the
printed backend. On the GB10 with requirements-gpu.txt installed and the env vars
set, expect ``cugraph`` and ``cudf-polars``; anywhere else, ``networkx`` / ``polars``
/ ``pandas``.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _have(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def main() -> int:
    print("=== RAPIDS GPU seam check ===")
    print(f"env: URBANOS_GPU_GRAPH={os.environ.get('URBANOS_GPU_GRAPH', '')!r} "
          f"URBANOS_GPU_DF={os.environ.get('URBANOS_GPU_DF', '')!r}")
    print("installed: " + ", ".join(
        f"{m}={_have(m)}" for m in ("nx_cugraph", "cudf", "cudf_polars", "polars")
    ))

    # 1) nx-cugraph seam — building the scenario bakes the substrate shortest paths.
    from urban_os.adapters import downtown_scenario
    from urban_os.kernel import state as kstate

    sc = downtown_scenario()
    print(f"\n[graph]  substrate={sc.substrate.n} nodes  ->  GRAPH_BACKEND="
          f"{kstate.GRAPH_BACKEND}")

    # 2) cuDF/Polars seam — read a CSV through the ingest path.
    from civic_analyst.ingest import loader

    csv = next(Path("demo_data").glob("*.csv"), None) or next(Path("fixtures").glob("*.csv"), None)
    if csv is not None:
        cols, rows = loader._read_csv_rows(csv)
        print(f"[ingest] read {csv.name}: {len(rows)} rows, {len(cols)} cols  ->  "
              f"DF_BACKEND={loader.DF_BACKEND}")
    else:
        print("[ingest] no CSV found under demo_data/ or fixtures/ — skipped")

    gpu = kstate.GRAPH_BACKEND == "cugraph" or loader.DF_BACKEND == "cudf-polars"
    print("\nRESULT:", "GPU path active ✅" if gpu else
          "CPU fallback (honest) — install requirements-gpu.txt + set env on the box")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
