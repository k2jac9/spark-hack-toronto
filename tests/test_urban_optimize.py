"""The optimizer finds the honest interior optimum and reports a real saving."""
from __future__ import annotations

import numpy as np
import pytest

from urban_os.adapters import downtown_scenario
from urban_os.kernel import Simulation
from urban_os.lenses import EconomicLens, EventSurge, WeatherLens
from urban_os.optimize import cost_breakdown, objective, optimize


def _lenses(sc):
    return [
        EventSurge(sc.venue_id, sc.crowd_size, event_end=sc.event_end),
        EconomicLens(),
    ]


def _three_lens(sc, *, intensity: float = 0.7):
    """The full demo stack with a tunable rain intensity, so shelter calibration
    can be exercised across mild → heavy rain."""
    return [
        EventSurge(sc.venue_id, sc.crowd_size, event_end=sc.event_end),
        EconomicLens(),
        WeatherLens(
            peak_time=sc.event_end,
            intensity=intensity,
            width=20.0,
            crowd_size=sc.crowd_size,
        ),
    ]


def test_optimizer_picks_interior_release_and_saves_money() -> None:
    sc = downtown_scenario()
    opt = optimize(sc.substrate, _lenses(sc), sc.horizon, dt=sc.dt)
    best = opt.best_params["release_minutes"]
    # Not the corner solutions: doing nothing (0) loses to a real release, and
    # holding forever (max, 20) is over-corrected by the hold-cost term.
    assert 0 < best < 20
    assert opt.savings > 0
    assert opt.best_J < opt.baseline_J


def test_baseline_is_do_nothing() -> None:
    sc = downtown_scenario()
    opt = optimize(sc.substrate, _lenses(sc), sc.horizon, dt=sc.dt)
    assert opt.baseline_params["release_minutes"] == 0.0
    # The chosen intervention lowers the peak crush vs. doing nothing.
    base_peak = opt.baseline_result.peak_congestion()["congestion"]
    best_peak = opt.best_result.peak_congestion()["congestion"]
    assert best_peak < base_peak


def test_trials_cover_the_whole_lever_grid() -> None:
    sc = downtown_scenario()
    lenses = _lenses(sc)
    opt = optimize(sc.substrate, lenses, sc.horizon, dt=sc.dt)
    grid = lenses[0].levers()[0].values
    assert len(opt.trials) == len(grid)


# --------------------------------------------------------------------------- #
# Shelter is a genuine interior optimum (GOAL 1 / ADR-0015)
# --------------------------------------------------------------------------- #
def test_default_optimum_chooses_shelter_and_release() -> None:
    """On the calibrated default scenario (rain intensity 0.7) the optimizer now
    prices crowd-safety risk into J, so shelter is a real benefit and is chosen
    alongside an interior staggered release."""
    sc = downtown_scenario()
    opt = optimize(sc.substrate, _three_lens(sc), sc.horizon, dt=sc.dt)
    release = float(opt.best_params["release_minutes"])
    shelter = float(opt.best_params["shelter_fraction"])
    assert 0 < release < 20          # interior staggered release
    assert shelter > 0.0             # shelter is part of the recommendation
    assert opt.savings > 0
    assert opt.best_J < opt.baseline_J


def test_shelter_is_chosen_at_high_rain_not_at_low_rain() -> None:
    """The shelter lever is a genuine interior trade-off: skipped when rain is
    mild (staffing not worth it) and engaged once rain is heavy enough that the
    safety + exposure benefit beats the staffing cost."""
    sc = downtown_scenario()

    def chosen_shelter(intensity: float) -> float:
        opt = optimize(
            sc.substrate, _three_lens(sc, intensity=intensity), sc.horizon, dt=sc.dt
        )
        return float(opt.best_params["shelter_fraction"])

    # Mild drizzle (intensity 0.05): not worth staffing shelter.
    assert chosen_shelter(0.05) == 0.0
    # Heavy rain (and the calibrated default 0.7): shelter pays for itself, and
    # shelter coverage is non-decreasing as the rain gets worse (coherent).
    assert chosen_shelter(0.3) > 0.0
    assert chosen_shelter(0.7) > 0.0
    assert chosen_shelter(1.0) > 0.0
    assert chosen_shelter(0.3) <= chosen_shelter(0.7) <= chosen_shelter(1.0)


def test_shelter_not_strictly_dominated_by_release() -> None:
    """At heavy rain, the all-release/no-shelter corner is beaten by a run that
    also deploys shelter — i.e. shelter is never strictly dominated."""
    sc = downtown_scenario()
    lenses = _three_lens(sc, intensity=1.0)
    horizon = sc.horizon

    def J(release: float, shelter: float) -> float:
        sim = Simulation(
            sc.substrate,
            lenses,
            params={"release_minutes": release, "shelter_fraction": shelter},
            dt=sc.dt,
        )
        return objective(sim.run(horizon), lenses)

    # The best release with NO shelter vs. the same release WITH full shelter.
    no_shelter = min(J(r, 0.0) for r in (12.0, 14.0, 16.0, 18.0, 20.0))
    with_shelter = min(J(r, 1.0) for r in (12.0, 14.0, 16.0, 18.0, 20.0))
    assert with_shelter < no_shelter


def test_staffing_cost_is_monotonic_decreasing_in_release() -> None:
    """Re-basing staffing on the in-system rained-on load (not a static crowd)
    makes longer holds CHEAPER, not more expensive: the platforms drain before
    the rain peak, so fewer people are sheltered (audit finding)."""
    sc = downtown_scenario()
    lenses = _three_lens(sc, intensity=0.7)
    weather = lenses[-1]

    def staffing(release: float) -> float:
        sim = Simulation(
            sc.substrate,
            lenses,
            params={"release_minutes": release, "shelter_fraction": 1.0},
            dt=sc.dt,
        )
        res = sim.run(sc.horizon)
        # Weather cost = exposure + staffing; full shelter ⇒ exposure 0, so the
        # whole weather cost is staffing.
        return weather.cost(res)

    grid = list(np.arange(0.0, 20.0001, 2.0))
    costs = [staffing(r) for r in grid]
    for prev, cur in zip(costs, costs[1:]):
        assert cur <= prev + 1e-6      # non-increasing in release


def test_cost_breakdown_sums_to_total_and_equals_J() -> None:
    """The J decomposition names every term and sums to the total objective."""
    sc = downtown_scenario()
    lenses = _three_lens(sc)
    opt = optimize(sc.substrate, lenses, sc.horizon, dt=sc.dt)
    for bd, res in (
        (opt.best_breakdown, opt.best_result),
        (opt.baseline_breakdown, opt.baseline_result),
    ):
        assert set(bd) == {
            "delay", "hold", "exposure", "staffing", "safety", "total"
        }
        parts = sum(bd[k] for k in ("delay", "hold", "exposure", "staffing", "safety"))
        assert bd["total"] == pytest.approx(parts, abs=1e-6)
        assert bd["total"] == pytest.approx(objective(res, lenses), abs=1e-6)
        assert all(bd[k] >= -1e-9 for k in bd)  # no negative dollar terms


def test_cost_breakdown_helper_matches_objective() -> None:
    sc = downtown_scenario()
    lenses = _three_lens(sc)
    sim = Simulation(
        sc.substrate,
        lenses,
        params={"release_minutes": 16.0, "shelter_fraction": 1.0},
        dt=sc.dt,
    )
    res = sim.run(sc.horizon)
    bd = cost_breakdown(res, lenses)
    assert bd["total"] == pytest.approx(objective(res, lenses), abs=1e-6)
