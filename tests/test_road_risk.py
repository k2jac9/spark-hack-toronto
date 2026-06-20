"""Fit C — RoadRisk lens (Vision Zero / KSI collision history, advisory display overlay).

The lens lifts a severity-weighted KSI collision density onto the substrate as its OWN static
``road_risk`` overlay. It is DISPLAY-ONLY and ADDITIVE: read-only on the crowd fields
(``load``/``congestion``/``risk``), declares NO levers, carries NO cost, and lives in
``extra_display_lenses`` (excluded from the optimizer's ``J``) — so it can never move a headline
number. These tests pin the honesty invariants (ADR-0036):

1. bare construction is inert (offline-safe no-op);
2. the static danger field is baked at NON-SINK nodes only and normalised 0..1; degenerate/empty
   inputs don't raise and never emit NaN/inf;
3. no levers, zero cost, advisory provenance; the exposure metric is a bounded cosine;
4. read-only on the crowd fields — the additivity contract (it perturbs nothing else);
5. determinism;
6. the adapter ``road_risk_by_node`` returns the right shape, concentrates density near real
   points, and falls back synthetically when no slice is present.

All offline: a tiny in-test substrate + in-test KSI points, no network, no real data.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pytest

from urbanos.kernel.adapters import downtown_scenario, road_risk_by_node
from urbanos.kernel.kernel import Simulation
from urbanos.kernel.kernel.state import State, Substrate
from urbanos.kernel.lenses import EconomicLens, EventSurge, RoadRiskLens
from urbanos.kernel.lenses.road_risk import PROVENANCE


# --- a tiny deterministic substrate -----------------------------------------
def _toy_substrate() -> Substrate:
    """One transit node 'a' draining to a sink 's' — small enough to assert exact shape."""
    g = nx.DiGraph()
    g.add_node("a", lat=43.60, lng=-79.40, capacity=100.0)
    g.add_node("s", lat=43.50, lng=-79.50, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    return Substrate.from_graph(g, sinks=["s"])


def _state(sub: Substrate, dt: float = 1.0) -> State:
    st = State(sub, {"release_minutes": 0.0})
    st.params["dt"] = dt
    return st


# --- 1. bare lens is inert ---------------------------------------------------
def test_bare_lens_is_inert():
    sub = _toy_substrate()
    lens = RoadRiskLens()
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)
    assert "road_risk" not in st.fields            # wrote no overlay
    assert lens.observe(st, 0.0) == {}             # no metric when inert


def test_bare_lens_inert_in_a_full_run():
    sc = downtown_scenario()
    stack = [EventSurge(events=sc.events), EconomicLens(), RoadRiskLens()]
    res = Simulation(sc.substrate, stack, params={"release_minutes": 0.0}, dt=sc.dt).run(
        sc.horizon
    )
    assert res.series("road_risk_peak") == []      # inert -> no metric


# --- 2. static field baked at non-sink nodes only; normalised ----------------
def test_couple_writes_normalised_overlay_at_non_sinks_only():
    """The danger overlay carries the configured value at the non-sink node (normalised to the
    peak), the sink's value is IGNORED, and the field is the SAME every step (static)."""
    sub = _toy_substrate()
    risk = {"a": 150.0, "s": 999.0}                # sink value must be ignored
    lens = RoadRiskLens(risk)
    lens.configure(sub)
    ai, si = sub.idx("a"), sub.idx("s")
    st = _state(sub)
    lens.couple(st, 0.0)
    overlay = st.fields["road_risk"]
    assert overlay[ai] == pytest.approx(1.0)       # the only node -> peak -> normalised 1.0
    assert overlay[si] == 0.0                       # sink never seeded
    assert lens.observe(st, 0.0)["road_risk_peak"] == pytest.approx(1.0)
    # static: a later step writes the identical field
    st2 = _state(sub)
    lens.couple(st2, 99.0)
    assert np.array_equal(st.fields["road_risk"], st2.fields["road_risk"])


def test_relative_shape_is_normalised():
    """Two non-sink nodes keep their RELATIVE danger after normalisation (the shape is the
    claim): the hotter node is 1.0, the cooler is its ratio."""
    g = nx.DiGraph()
    g.add_node("a", lat=43.60, lng=-79.40, capacity=100.0)
    g.add_node("b", lat=43.61, lng=-79.41, capacity=100.0)
    g.add_node("s", lat=43.50, lng=-79.50, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    g.add_edge("b", "s", capacity=1000.0, length=1.0)
    sub = Substrate.from_graph(g, sinks=["s"])
    lens = RoadRiskLens({"a": 200.0, "b": 50.0})
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)
    ov = st.fields["road_risk"]
    assert ov[sub.idx("a")] == pytest.approx(1.0)
    assert ov[sub.idx("b")] == pytest.approx(0.25)


def test_no_nan_or_inf_from_degenerate_inputs():
    sub = _toy_substrate()
    lens = RoadRiskLens({"a": float("nan")})       # all degenerate
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)                            # must not raise
    assert np.all(np.isfinite(st.fields["road_risk"]))
    assert st.fields["road_risk"][sub.idx("a")] == 0.0   # nan dropped -> nothing seeded


def test_empty_series_does_not_raise():
    sub = _toy_substrate()
    for series in ({}, None):
        lens = RoadRiskLens(series)
        lens.configure(sub)
        st = _state(sub)
        lens.couple(st, 0.0)                        # inert, no raise
        assert "road_risk" not in st.fields


# --- 3. no levers, zero cost, provenance; bounded exposure -------------------
def test_no_levers_no_cost_and_provenance():
    sub = _toy_substrate()
    lens = RoadRiskLens({"a": 10.0})
    lens.configure(sub)
    assert lens.levers() == []
    assert lens.cost(None) == 0.0                   # display-only, never a J term
    assert PROVENANCE == "synthetic/advisory"


def test_crush_road_exposure_is_bounded():
    """The advisory exposure overlap is a scale-free cosine in [0, 1] (display-only)."""
    sub = _toy_substrate()
    lens = RoadRiskLens({"a": 10.0})
    lens.configure(sub)
    st = _state(sub)
    st.fields["load"][sub.idx("a")] = 5.0          # crowd coincides with danger at 'a'
    lens.couple(st, 0.0)
    m = lens.observe(st, 0.0)
    assert 0.0 <= m["crush_road_exposure"] <= 1.0
    assert m["crush_road_exposure"] == pytest.approx(1.0)   # perfectly aligned profiles


# --- 4. read-only on the crowd fields (the additivity contract) --------------
def test_lens_does_not_perturb_crowd_fields_or_economic_terms():
    sc = downtown_scenario()

    def run(with_lens: bool):
        stack = [EventSurge(events=sc.events), EconomicLens()]
        if with_lens:
            stack.append(RoadRiskLens(road_risk_by_node(sc.substrate)))
        return Simulation(
            sc.substrate, stack, params={"release_minutes": 0.0}, dt=sc.dt
        ).run(sc.horizon)

    base, withl = run(False), run(True)
    assert np.allclose(base.frames[-1]["load"], withl.frames[-1]["load"])
    assert np.isclose(sum(base.series("delay_cost")), sum(withl.series("delay_cost")))
    assert np.isclose(sum(base.series("safety_cost")), sum(withl.series("safety_cost")))


def test_extra_display_lenses_includes_road_risk_and_stays_additive():
    from urbanos.kernel.scenarios import extra_display_lenses

    sc = downtown_scenario()
    grounded = next(l for l in extra_display_lenses(sc) if l.name == "road_risk")
    bare = next(l for l in extra_display_lenses() if l.name == "road_risk")
    assert grounded.node_risk is not None
    assert set(grounded.node_risk) == set(sc.substrate.ids)
    assert bare.node_risk is None

    base = Simulation(
        sc.substrate, [EventSurge(events=sc.events), EconomicLens()],
        params={"release_minutes": 0.0}, dt=sc.dt,
    ).run(sc.horizon)
    stack = [EventSurge(events=sc.events), EconomicLens(), *extra_display_lenses(sc)]
    withl = Simulation(
        sc.substrate, stack, params={"release_minutes": 0.0}, dt=sc.dt
    ).run(sc.horizon)
    assert np.isclose(sum(base.series("delay_cost")), sum(withl.series("delay_cost")))
    assert np.isclose(sum(base.series("safety_cost")), sum(withl.series("safety_cost")))
    assert np.allclose(base.frames[-1]["load"], withl.frames[-1]["load"])


# --- 5. determinism ----------------------------------------------------------
def test_deterministic():
    sc = downtown_scenario()
    risk = road_risk_by_node(sc.substrate, provider=lambda: [])  # synthetic

    def run():
        stack = [EventSurge(events=sc.events), EconomicLens(), RoadRiskLens(risk)]
        return Simulation(
            sc.substrate, stack, params={"release_minutes": 6.0}, dt=sc.dt
        ).run(sc.horizon)

    a, b = run(), run()
    assert a.series("crush_road_exposure") == b.series("crush_road_exposure")
    assert np.allclose(a.frames[-1]["load"], b.frames[-1]["load"])


# --- 6. adapter: shape, proximity fusion, synthetic fallback -----------------
def test_road_risk_by_node_concentrates_density_near_points():
    """A KSI point next to node 'a' lifts 'a' well above the far node 'b'; the sink is 0."""
    g = nx.DiGraph()
    g.add_node("a", lat=43.600, lng=-79.400, capacity=100.0)
    g.add_node("b", lat=43.660, lng=-79.340, capacity=100.0)
    g.add_node("s", lat=43.500, lng=-79.500, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    g.add_edge("b", "s", capacity=1000.0, length=1.0)
    sub = Substrate.from_graph(g, sinks=["s"])
    pts = [{"lat": 43.6005, "lng": -79.4002, "value": 3.0},
           {"lat": 43.6003, "lng": -79.3998, "value": 2.0}]
    rr = road_risk_by_node(sub, provider=lambda: pts)
    assert rr["a"] > rr["b"]
    assert rr["s"] == 0.0
    assert all(np.isfinite(v) for v in rr.values())


def test_road_risk_by_node_synthetic_fallback():
    """With no KSI slice the adapter returns a deterministic synthetic field: one value per
    node, finite, non-sink nodes carry danger, sinks none."""
    sc = downtown_scenario()
    rr = road_risk_by_node(sc.substrate, provider=lambda: [])   # empty -> synthetic
    sub = sc.substrate
    assert set(rr) == set(sub.ids)
    for i, nid in enumerate(sub.ids):
        assert np.isfinite(rr[nid])
        if sub.is_sink[i]:
            assert rr[nid] == 0.0
    assert sum(v for i, nid in enumerate(sub.ids) if not sub.is_sink[i] for v in [rr[nid]]) > 0.0


def test_road_risk_by_node_default_provider_is_offline_safe():
    """The DEFAULT provider path yields a well-formed field via the loader (real slice under the
    demo, synthetic fallback in CI/dev) — proving the real-data wiring degrades cleanly."""
    from urbanos.kernel.adapters.toronto import reset_road_risk_cache

    reset_road_risk_cache()
    sc = downtown_scenario()
    rr = road_risk_by_node(sc.substrate)            # default provider
    assert set(rr) == set(sc.substrate.ids)
    assert all(np.isfinite(v) for v in rr.values())
