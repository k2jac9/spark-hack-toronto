"""Fit C — Emergency lens (TFS fire-incident response density, advisory display overlay).

The lens lifts a severity-weighted fire-service incident-RESPONSE density onto the substrate as
its OWN static ``emergency`` overlay. It is DISPLAY-ONLY and ADDITIVE: read-only on the crowd
fields (``load``/``congestion``/``risk``), declares NO levers, carries NO cost, and lives in
``extra_display_lenses`` (excluded from the optimizer's ``J``) — so it can never move a headline
number. These tests pin the honesty invariants (ADR-0041):

1. bare construction is inert (offline-safe no-op);
2. the static response-load field is baked at NON-SINK nodes only and normalised 0..1;
   degenerate/empty inputs don't raise and never emit NaN/inf;
3. no levers, zero cost, advisory provenance; the exposure metric is a bounded cosine;
4. read-only on the crowd fields — the additivity contract (it perturbs nothing else);
5. determinism.

The lens is constructed DIRECTLY from a hand-built ``{node_id: value}`` map (the ``emergency_by_node``
adapter is wired separately by the lead — these tests never import it), so everything stays offline:
a tiny in-test substrate + in-test density values, no network, no real data.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pytest

from urbanos.kernel.kernel import Simulation
from urbanos.kernel.kernel.state import State, Substrate
from urbanos.kernel.lenses.economic import EconomicLens
from urbanos.kernel.lenses.event_surge import EventSurge
from urbanos.kernel.lenses.emergency import EmergencyLens, PROVENANCE
from urbanos.kernel.adapters import downtown_scenario


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


def _emergency_by_node(sub: Substrate) -> dict[str, float]:
    """A deterministic per-node density built DIRECTLY (no adapter import): each non-sink node
    gets ``i+1``, sinks get 0. Mirrors the shape the real adapter returns, fully offline."""
    return {nid: (0.0 if sub.is_sink[i] else float(i + 1)) for i, nid in enumerate(sub.ids)}


# --- 1. bare lens is inert ---------------------------------------------------
def test_bare_lens_is_inert():
    sub = _toy_substrate()
    lens = EmergencyLens()
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)
    assert "emergency" not in st.fields           # wrote no overlay
    assert lens.observe(st, 0.0) == {}            # no metric when inert


def test_bare_lens_inert_in_a_full_run():
    sc = downtown_scenario()
    stack = [EventSurge(events=sc.events), EconomicLens(), EmergencyLens()]
    res = Simulation(sc.substrate, stack, params={"release_minutes": 0.0}, dt=sc.dt).run(
        sc.horizon
    )
    assert res.series("emergency_peak") == []     # inert -> no metric


# --- 2. static field baked at non-sink nodes only; normalised ----------------
def test_couple_writes_normalised_overlay_at_non_sinks_only():
    """The response overlay carries the configured value at the non-sink node (normalised to the
    peak), the sink's value is IGNORED, and the field is the SAME every step (static)."""
    sub = _toy_substrate()
    emergency = {"a": 150.0, "s": 999.0}          # sink value must be ignored
    lens = EmergencyLens(emergency)
    lens.configure(sub)
    ai, si = sub.idx("a"), sub.idx("s")
    st = _state(sub)
    lens.couple(st, 0.0)
    overlay = st.fields["emergency"]
    assert overlay[ai] == pytest.approx(1.0)      # the only node -> peak -> normalised 1.0
    assert overlay[si] == 0.0                      # sink never seeded
    assert lens.observe(st, 0.0)["emergency_peak"] == pytest.approx(1.0)
    # static: a later step writes the identical field
    st2 = _state(sub)
    lens.couple(st2, 99.0)
    assert np.array_equal(st.fields["emergency"], st2.fields["emergency"])


def test_relative_shape_is_normalised():
    """Two non-sink nodes keep their RELATIVE response load after normalisation (the shape is the
    claim): the busier node is 1.0, the quieter is its ratio."""
    g = nx.DiGraph()
    g.add_node("a", lat=43.60, lng=-79.40, capacity=100.0)
    g.add_node("b", lat=43.61, lng=-79.41, capacity=100.0)
    g.add_node("s", lat=43.50, lng=-79.50, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    g.add_edge("b", "s", capacity=1000.0, length=1.0)
    sub = Substrate.from_graph(g, sinks=["s"])
    lens = EmergencyLens({"a": 200.0, "b": 50.0})
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)
    ov = st.fields["emergency"]
    assert ov[sub.idx("a")] == pytest.approx(1.0)
    assert ov[sub.idx("b")] == pytest.approx(0.25)


def test_no_nan_or_inf_from_degenerate_inputs():
    sub = _toy_substrate()
    lens = EmergencyLens({"a": float("nan")})     # all degenerate
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)                           # must not raise
    assert np.all(np.isfinite(st.fields["emergency"]))
    assert st.fields["emergency"][sub.idx("a")] == 0.0   # nan dropped -> nothing seeded


def test_empty_series_does_not_raise():
    sub = _toy_substrate()
    for series in ({}, None):
        lens = EmergencyLens(series)
        lens.configure(sub)
        st = _state(sub)
        lens.couple(st, 0.0)                       # inert, no raise
        assert "emergency" not in st.fields


# --- 3. no levers, zero cost, provenance; bounded exposure -------------------
def test_no_levers_no_cost_and_provenance():
    sub = _toy_substrate()
    lens = EmergencyLens({"a": 10.0})
    lens.configure(sub)
    assert lens.levers() == []
    assert lens.cost(None) == 0.0                  # display-only, never a J term
    assert PROVENANCE == "real/measured"


def test_crush_emergency_exposure_is_bounded():
    """The advisory exposure overlap is a scale-free cosine in [0, 1] (display-only)."""
    sub = _toy_substrate()
    lens = EmergencyLens({"a": 10.0})
    lens.configure(sub)
    st = _state(sub)
    st.fields["load"][sub.idx("a")] = 5.0         # crowd coincides with response load at 'a'
    lens.couple(st, 0.0)
    m = lens.observe(st, 0.0)
    assert 0.0 <= m["crush_emergency_exposure"] <= 1.0
    assert m["crush_emergency_exposure"] == pytest.approx(1.0)   # perfectly aligned profiles


# --- 4. read-only on the crowd fields (the additivity contract) --------------
def test_lens_does_not_perturb_crowd_fields_or_economic_terms():
    sc = downtown_scenario()
    emergency = _emergency_by_node(sc.substrate)

    def run(with_lens: bool):
        stack = [EventSurge(events=sc.events), EconomicLens()]
        if with_lens:
            stack.append(EmergencyLens(emergency))
        return Simulation(
            sc.substrate, stack, params={"release_minutes": 0.0}, dt=sc.dt
        ).run(sc.horizon)

    base, withl = run(False), run(True)
    assert np.allclose(base.frames[-1]["load"], withl.frames[-1]["load"])
    assert np.isclose(sum(base.series("delay_cost")), sum(withl.series("delay_cost")))
    assert np.isclose(sum(base.series("safety_cost")), sum(withl.series("safety_cost")))


# --- 5. determinism ----------------------------------------------------------
def test_deterministic():
    sc = downtown_scenario()
    emergency = _emergency_by_node(sc.substrate)

    def run():
        stack = [EventSurge(events=sc.events), EconomicLens(), EmergencyLens(emergency)]
        return Simulation(
            sc.substrate, stack, params={"release_minutes": 6.0}, dt=sc.dt
        ).run(sc.horizon)

    a, b = run(), run()
    assert a.series("crush_emergency_exposure") == b.series("crush_emergency_exposure")
    assert np.allclose(a.frames[-1]["load"], b.frames[-1]["load"])


# --- adapter: proximity fusion + synthetic fallback (wired post-integration) --
def test_emergency_by_node_concentrates_density_near_points():
    from urbanos.kernel.adapters import emergency_by_node

    g = nx.DiGraph()
    g.add_node("a", lat=43.600, lng=-79.400, capacity=100.0)
    g.add_node("b", lat=43.660, lng=-79.340, capacity=100.0)
    g.add_node("s", lat=43.500, lng=-79.500, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    g.add_edge("b", "s", capacity=1000.0, length=1.0)
    sub = Substrate.from_graph(g, sinks=["s"])
    pts = [{"lat": 43.6005, "lng": -79.4002, "value": 2.0},
           {"lat": 43.6003, "lng": -79.3998, "value": 1.0}]
    rr = emergency_by_node(sub, provider=lambda: pts)
    assert rr["a"] > rr["b"]
    assert rr["s"] == 0.0
    assert all(np.isfinite(v) for v in rr.values())


def test_emergency_by_node_synthetic_fallback():
    from urbanos.kernel.adapters import emergency_by_node

    sc = downtown_scenario()
    rr = emergency_by_node(sc.substrate, provider=lambda: [])   # empty -> synthetic
    sub = sc.substrate
    assert set(rr) == set(sub.ids)
    for i, nid in enumerate(sub.ids):
        assert np.isfinite(rr[nid])
        if sub.is_sink[i]:
            assert rr[nid] == 0.0
    assert sum(rr[nid] for i, nid in enumerate(sub.ids) if not sub.is_sink[i]) > 0.0


def test_emergency_by_node_default_provider_is_offline_safe():
    from urbanos.kernel.adapters import emergency_by_node, reset_emergency_cache

    reset_emergency_cache()
    sc = downtown_scenario()
    rr = emergency_by_node(sc.substrate)            # default provider
    assert set(rr) == set(sc.substrate.ids)
    assert all(np.isfinite(v) for v in rr.values())
