"""Fit C — BikeTheft lens (reported bicycle-theft density, advisory display overlay).

The lens lifts a severity-weighted reported bicycle-theft density onto the substrate as its OWN
static ``bike_theft`` overlay. It is DISPLAY-ONLY and ADDITIVE: read-only on the crowd fields
(``load``/``congestion``/``risk``), declares NO levers, carries NO cost, and is excluded from the
optimizer's ``J`` — so it can never move a headline number. These tests pin the honesty
invariants (ADR-0040):

1. bare construction is inert (offline-safe no-op);
2. the static theft field is baked at NON-SINK nodes only and normalised 0..1; degenerate/empty
   inputs don't raise and never emit NaN/inf;
3. no levers, zero cost, advisory provenance; the exposure metric is a bounded cosine;
4. read-only on the crowd fields — the additivity contract (it perturbs nothing else);
5. determinism.

All offline: a tiny in-test substrate + a hand-built ``{node_id: value}`` theft map, no network,
no real data, no adapter (the ``bike_theft_by_node`` adapter wiring is the lead's to land — these
tests construct the lens DIRECTLY).
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pytest

from urbanos.kernel.adapters import downtown_scenario
from urbanos.kernel.kernel import Simulation
from urbanos.kernel.kernel.state import State, Substrate
from urbanos.kernel.lenses import EconomicLens, EventSurge
from urbanos.kernel.lenses.bike_theft import PROVENANCE, BikeTheftLens


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


def _theft_by_ids(sub: Substrate) -> dict[str, float]:
    """A deterministic hand-built ``{node_id: value}`` theft map over a substrate's NON-SINK
    nodes — ``i+1`` per non-sink id (no adapter, no real data)."""
    return {
        nid: float(i + 1)
        for i, nid in enumerate(nid for j, nid in enumerate(sub.ids) if not sub.is_sink[j])
    }


# --- 1. bare lens is inert ---------------------------------------------------
def test_bare_lens_is_inert():
    sub = _toy_substrate()
    lens = BikeTheftLens()
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)
    assert "bike_theft" not in st.fields           # wrote no overlay
    assert lens.observe(st, 0.0) == {}             # no metric when inert


def test_bare_lens_inert_in_a_full_run():
    sc = downtown_scenario()
    stack = [EventSurge(events=sc.events), EconomicLens(), BikeTheftLens()]
    res = Simulation(sc.substrate, stack, params={"release_minutes": 0.0}, dt=sc.dt).run(
        sc.horizon
    )
    assert res.series("bike_theft_peak") == []     # inert -> no metric


# --- 2. static field baked at non-sink nodes only; normalised ----------------
def test_couple_writes_normalised_overlay_at_non_sinks_only():
    """The theft overlay carries the configured value at the non-sink node (normalised to the
    peak), the sink's value is IGNORED, and the field is the SAME every step (static)."""
    sub = _toy_substrate()
    theft = {"a": 150.0, "s": 999.0}               # sink value must be ignored
    lens = BikeTheftLens(theft)
    lens.configure(sub)
    ai, si = sub.idx("a"), sub.idx("s")
    st = _state(sub)
    lens.couple(st, 0.0)
    overlay = st.fields["bike_theft"]
    assert overlay[ai] == pytest.approx(1.0)       # the only node -> peak -> normalised 1.0
    assert overlay[si] == 0.0                       # sink never seeded
    assert lens.observe(st, 0.0)["bike_theft_peak"] == pytest.approx(1.0)
    # static: a later step writes the identical field
    st2 = _state(sub)
    lens.couple(st2, 99.0)
    assert np.array_equal(st.fields["bike_theft"], st2.fields["bike_theft"])


def test_relative_shape_is_normalised():
    """Two non-sink nodes keep their RELATIVE theft after normalisation (the shape is the
    claim): the hotter node is 1.0, the cooler is its ratio."""
    g = nx.DiGraph()
    g.add_node("a", lat=43.60, lng=-79.40, capacity=100.0)
    g.add_node("b", lat=43.61, lng=-79.41, capacity=100.0)
    g.add_node("s", lat=43.50, lng=-79.50, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    g.add_edge("b", "s", capacity=1000.0, length=1.0)
    sub = Substrate.from_graph(g, sinks=["s"])
    lens = BikeTheftLens({"a": 200.0, "b": 50.0})
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)
    ov = st.fields["bike_theft"]
    assert ov[sub.idx("a")] == pytest.approx(1.0)
    assert ov[sub.idx("b")] == pytest.approx(0.25)


def test_no_nan_or_inf_from_degenerate_inputs():
    sub = _toy_substrate()
    lens = BikeTheftLens({"a": float("nan")})      # all degenerate
    lens.configure(sub)
    st = _state(sub)
    lens.couple(st, 0.0)                            # must not raise
    assert np.all(np.isfinite(st.fields["bike_theft"]))
    assert st.fields["bike_theft"][sub.idx("a")] == 0.0   # nan dropped -> nothing seeded


def test_empty_series_does_not_raise():
    sub = _toy_substrate()
    for series in ({}, None):
        lens = BikeTheftLens(series)
        lens.configure(sub)
        st = _state(sub)
        lens.couple(st, 0.0)                        # inert, no raise
        assert "bike_theft" not in st.fields


# --- 3. no levers, zero cost, provenance; bounded exposure -------------------
def test_no_levers_no_cost_and_provenance():
    sub = _toy_substrate()
    lens = BikeTheftLens({"a": 10.0})
    lens.configure(sub)
    assert lens.levers() == []
    assert lens.cost(None) == 0.0                   # display-only, never a J term
    assert PROVENANCE == "real/measured"


def test_crush_bike_theft_exposure_is_bounded():
    """The advisory exposure overlap is a scale-free cosine in [0, 1] (display-only)."""
    sub = _toy_substrate()
    lens = BikeTheftLens({"a": 10.0})
    lens.configure(sub)
    st = _state(sub)
    st.fields["load"][sub.idx("a")] = 5.0          # crowd coincides with theft at 'a'
    lens.couple(st, 0.0)
    m = lens.observe(st, 0.0)
    assert 0.0 <= m["crush_bike_theft_exposure"] <= 1.0
    assert m["crush_bike_theft_exposure"] == pytest.approx(1.0)   # perfectly aligned profiles


# --- 4. read-only on the crowd fields (the additivity contract) --------------
def test_lens_does_not_perturb_crowd_fields_or_economic_terms():
    """The additivity contract: building the lens DIRECTLY from a hand-built theft map, the
    crowd fields and the economic terms are byte-identical with vs without the lens."""
    sc = downtown_scenario()
    theft = _theft_by_ids(sc.substrate)

    def run(with_lens: bool):
        stack = [EventSurge(events=sc.events), EconomicLens()]
        if with_lens:
            stack.append(BikeTheftLens(theft))
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
    theft = _theft_by_ids(sc.substrate)

    def run():
        stack = [EventSurge(events=sc.events), EconomicLens(), BikeTheftLens(theft)]
        return Simulation(
            sc.substrate, stack, params={"release_minutes": 6.0}, dt=sc.dt
        ).run(sc.horizon)

    a, b = run(), run()
    assert a.series("crush_bike_theft_exposure") == b.series("crush_bike_theft_exposure")
    assert np.allclose(a.frames[-1]["load"], b.frames[-1]["load"])


# --- adapter: proximity fusion + synthetic fallback (wired post-integration) --
def test_bike_theft_by_node_concentrates_density_near_points():
    from urbanos.kernel.adapters import bike_theft_by_node

    g = nx.DiGraph()
    g.add_node("a", lat=43.600, lng=-79.400, capacity=100.0)
    g.add_node("b", lat=43.660, lng=-79.340, capacity=100.0)
    g.add_node("s", lat=43.500, lng=-79.500, capacity=1.0e9)
    g.add_edge("a", "s", capacity=1000.0, length=1.0)
    g.add_edge("b", "s", capacity=1000.0, length=1.0)
    sub = Substrate.from_graph(g, sinks=["s"])
    pts = [{"lat": 43.6005, "lng": -79.4002, "value": 2.0},
           {"lat": 43.6003, "lng": -79.3998, "value": 1.0}]
    rr = bike_theft_by_node(sub, provider=lambda: pts)
    assert rr["a"] > rr["b"]
    assert rr["s"] == 0.0
    assert all(np.isfinite(v) for v in rr.values())


def test_bike_theft_by_node_synthetic_fallback():
    from urbanos.kernel.adapters import bike_theft_by_node

    sc = downtown_scenario()
    rr = bike_theft_by_node(sc.substrate, provider=lambda: [])   # empty -> synthetic
    sub = sc.substrate
    assert set(rr) == set(sub.ids)
    for i, nid in enumerate(sub.ids):
        assert np.isfinite(rr[nid])
        if sub.is_sink[i]:
            assert rr[nid] == 0.0
    assert sum(rr[nid] for i, nid in enumerate(sub.ids) if not sub.is_sink[i]) > 0.0


def test_bike_theft_by_node_default_provider_is_offline_safe():
    from urbanos.kernel.adapters import bike_theft_by_node, reset_bike_theft_cache

    reset_bike_theft_cache()
    sc = downtown_scenario()
    rr = bike_theft_by_node(sc.substrate)            # default provider
    assert set(rr) == set(sc.substrate.ids)
    assert all(np.isfinite(v) for v in rr.values())
