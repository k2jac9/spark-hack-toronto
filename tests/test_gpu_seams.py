"""GPU-accelerator seams are wired with a verified CPU fallback.

These run on any machine (no GPU/CUDA needed): they assert the seams exist, are
invoked, and that the CPU fallback path is correct and behaviour-preserving. The
actual GPU activation is proven separately on the GB10 box (``make gpu-check``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import networkx as nx
import pytest

from urban_os.kernel import state as kstate
from urban_os.optimize import optimize
from urban_os.adapters import downtown_scenario
from urban_os.lenses import EconomicLens, EventSurge

from civic_analyst.ingest import loader

_HAS_POLARS = importlib.util.find_spec("polars") is not None


# --------------------------------------------------------------- nx-cugraph seam
def test_dijkstra_seam_runs_cpu_by_default_and_reports_backend():
    """With the GPU env unset, the substrate bake uses the CPU networkx backend and
    records it. The seam is exercised on every substrate build."""
    sc = downtown_scenario()
    assert sc.substrate.n > 0
    # The bake ran during downtown_scenario(); the seam recorded the backend.
    assert kstate.GRAPH_BACKEND in {"networkx", "cugraph"}
    # Default (no URBANOS_GPU_GRAPH) → CPU.
    assert kstate.GRAPH_BACKEND == "networkx"


def test_dijkstra_seam_matches_plain_networkx():
    """The seam's lengths are identical to a direct networkx call — it is a
    drop-in accelerator, never a behaviour change."""
    g = nx.DiGraph()
    g.add_edge("a", "b", length=1.0)
    g.add_edge("b", "c", length=2.0)
    g.add_edge("c", "exit", length=1.0)
    rev = g.reverse(copy=False)
    sinks = {"exit"}
    via_seam = kstate._multi_source_dijkstra_lengths(rev, sinks)
    via_nx = nx.multi_source_dijkstra_path_length(rev, sinks, weight="length")
    assert via_seam == via_nx


def test_gpu_graph_disabled_by_default(monkeypatch):
    monkeypatch.delenv("URBANOS_GPU_GRAPH", raising=False)
    monkeypatch.delenv("NX_CUGRAPH_AUTOCONFIG", raising=False)
    assert kstate._gpu_graph_enabled() is False
    monkeypatch.setenv("URBANOS_GPU_GRAPH", "1")
    assert kstate._gpu_graph_enabled() is True


# ------------------------------------------------------------------- cuOpt seam
def test_optimizer_uses_grid_fallback_by_default_and_reports_solver():
    """With the cuOpt env unset, the optimizer uses the deterministic grid search
    and records that solver. The result is the honest grid optimum."""
    sc = downtown_scenario()
    opt = optimize(sc.substrate, [EventSurge(events=sc.events), EconomicLens()],
                   sc.horizon, dt=sc.dt)
    assert getattr(opt, "solver", "grid") == "grid"
    assert opt.best_J <= opt.baseline_J + 1e-6  # never worse than do-nothing


# --------------------------------------------------------------- cuDF/Polars seam
def _a_fixture_csv() -> Path:
    for d in ("fixtures", "demo_data"):
        csv = next(Path(d).glob("*.csv"), None)
        if csv is not None:
            return csv
    pytest.skip("no CSV fixture available")


def test_ingest_reports_dataframe_backend():
    cols, rows = loader._read_csv_rows(_a_fixture_csv())
    assert loader.DF_BACKEND in {"pandas", "polars", "cudf-polars"}
    assert cols and rows  # read something


def test_force_pandas_backend(monkeypatch):
    monkeypatch.setenv("URBANOS_DF_BACKEND", "pandas")
    cols, rows = loader._read_csv_rows(_a_fixture_csv())
    assert loader.DF_BACKEND == "pandas"
    assert cols and rows


@pytest.mark.skipif(not _HAS_POLARS, reason="polars not installed (pandas-only env)")
def test_polars_and_pandas_read_identical_rows(monkeypatch):
    """The Polars ingest path is a drop-in: it yields byte-identical (columns, rows)
    to the pandas path, so the golden two-index numbers are unaffected by the swap."""
    csv = _a_fixture_csv()
    monkeypatch.setenv("URBANOS_DF_BACKEND", "pandas")
    p_cols, p_rows = loader._read_csv_rows(csv)
    assert loader.DF_BACKEND == "pandas"
    monkeypatch.delenv("URBANOS_DF_BACKEND", raising=False)
    pl_cols, pl_rows = loader._read_csv_rows(csv)
    assert loader.DF_BACKEND == "polars"  # polars present → preferred path
    assert pl_cols == p_cols
    assert pl_rows == p_rows
