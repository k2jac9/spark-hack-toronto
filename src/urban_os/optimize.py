"""Intervention optimizer — search lens-declared levers to minimize ``J``.

``J = Σ wₚ·Jₚ`` over the lenses' ``cost`` terms. P0 does an exhaustive grid
search over the (small, discrete) lever space; that is correct and trivially
deterministic, and it is the seam where **cuOpt** drops in on the GX10 for the
larger joint-lever problem (the search is isolated behind ``optimize`` so the
solver can be swapped without touching lenses or the kernel).

"Do nothing" is the first value of every lever (convention: index 0), so the
baseline is always part of the search and the reported saving is honest.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field

from .kernel.loop import SimResult
from .kernel.operators import Lens, Lever
from .kernel.state import Substrate


def objective(result: SimResult, lenses: list[Lens]) -> float:
    """The weighted cost ``J`` of a finished run."""
    return float(sum(lens.weight * lens.cost(result) for lens in lenses))


# The cost terms the UI/narrator surface so the optimizer's pick is reproducible
# from on-screen numbers (audit finding: the hold and shelter/safety costs were
# invisible, so "longer is always better by the heatmap" could not be reconciled
# with the optimizer's choice). Each maps to a per-step metric series the lenses
# already emit; ``total`` is just their sum and equals ``J`` (weights are 1.0 in
# the demo stack, asserted by the cost-decomposition test).
_COST_TERMS = ("delay", "hold", "exposure", "staffing", "safety")


def cost_breakdown(result: SimResult, lenses: list[Lens]) -> dict[str, float]:
    """Decompose ``J`` into its named dollar terms for transparency.

    Returns ``{delay, hold, exposure, staffing, safety, total}``. ``total`` is the
    sum of the five terms and equals ``objective(result, lenses)`` for the demo
    three-lens stack (all weights 1.0). Terms are derived from the per-step metric
    series the lenses emit, so this never re-runs the simulation.

    - **delay**: commuter-delay dollars (over-capacity queueing) — EconomicLens.
    - **safety**: integrated crowd-safety risk priced into ``J`` — EconomicLens.
    - **exposure**: rain-exposure discomfort for the unsheltered — WeatherLens.
    - **staffing**: cost of running shelter over the in-system rained-on load.
    - **hold**: staggered-release hold cost (orderly waiting) — EventSurge.
    """
    delay = float(sum(result.series("delay_cost")))
    safety = float(sum(result.series("safety_cost")))
    exposure = float(sum(result.series("exposure_cost")))
    total = objective(result, lenses)
    # Staffing is the part of the weather-lens cost beyond exposure; hold is the
    # remainder of J once the economic + weather terms are accounted for. Deriving
    # them by subtraction keeps the lenses the single source of truth for their
    # own ``cost`` (no formula is duplicated here) while still naming every term.
    staffing = max(0.0, total - delay - safety - exposure - _hold_cost(result, lenses))
    hold = _hold_cost(result, lenses)
    breakdown = {
        "delay": delay,
        "hold": hold,
        "exposure": exposure,
        "staffing": staffing,
        "safety": safety,
    }
    breakdown["total"] = total
    return breakdown


def _hold_cost(result: SimResult, lenses: list[Lens]) -> float:
    """The staggered-release hold dollars: the EventSurge lens's whole cost term
    (it contributes only the hold penalty to ``J``)."""
    for lens in lenses:
        if getattr(lens, "name", "") == "event_surge":
            return float(lens.weight * lens.cost(result))
    return 0.0


@dataclass
class OptResult:
    levers: list[Lever]
    baseline_params: dict
    baseline_result: SimResult
    baseline_J: float
    best_params: dict
    best_result: SimResult
    best_J: float
    trials: list[dict] = field(default_factory=list)  # [{params, J}]
    # Per-run J decomposition (delay/hold/exposure/staffing/safety/total) for the
    # do-nothing baseline and the chosen intervention — surfaced so the UI/narrator
    # can show WHY the optimizer picks its answer (audit finding). None for
    # directly-constructed OptResults; ``optimize()`` always fills them.
    baseline_breakdown: dict | None = None
    best_breakdown: dict | None = None

    @property
    def savings(self) -> float:
        """Dollars (or J units) the chosen intervention saves vs. doing nothing."""
        return self.baseline_J - self.best_J

    def to_dict(self) -> dict:
        return {
            "baseline": {
                "params": self.baseline_params,
                "J": self.baseline_J,
                "breakdown": self.baseline_breakdown,
            },
            "best": {
                "params": self.best_params,
                "J": self.best_J,
                "breakdown": self.best_breakdown,
            },
            "savings": self.savings,
            "levers": [{"name": lv.name, "label": lv.label} for lv in self.levers],
            "trials": self.trials,
        }


def optimize(
    substrate: Substrate,
    lenses: list[Lens],
    horizon: int,
    *,
    dt: float = 1.0,
    beta: float = 1.8,
    base_params: dict | None = None,
) -> OptResult:
    """Grid-search every lever combination; return the J-minimizing intervention
    alongside the do-nothing baseline. Lenses are reused across trials (their
    ``configure`` is idempotent); each trial builds a fresh ``Simulation`` so no
    state leaks between runs."""
    # Imported here to avoid a kernel→optimizer import cycle at module load.
    from .kernel.loop import Simulation

    levers = [lv for lens in lenses for lv in lens.levers()]
    base = dict(base_params or {})

    def run(params: dict) -> SimResult:
        sim = Simulation(substrate, lenses, params=params, dt=dt, beta=beta)
        return sim.run(horizon)

    # Baseline: every lever at its do-nothing (first) value.
    baseline_params = dict(base)
    for lv in levers:
        baseline_params.setdefault(lv.name, lv.values[0])
    baseline_result = run(baseline_params)
    baseline_J = objective(baseline_result, lenses)

    best_params, best_result, best_J = baseline_params, baseline_result, baseline_J
    trials: list[dict] = []

    grids = [lv.values for lv in levers]
    for combo in itertools.product(*grids) if levers else [()]:
        params = dict(base)
        for lv, val in zip(levers, combo):
            params[lv.name] = val
        result = run(params)
        J = objective(result, lenses)
        trials.append({"params": {lv.name: params[lv.name] for lv in levers}, "J": J})
        if J < best_J:
            best_params, best_result, best_J = params, result, J

    return OptResult(
        levers=levers,
        baseline_params=baseline_params,
        baseline_result=baseline_result,
        baseline_J=baseline_J,
        best_params=best_params,
        best_result=best_result,
        best_J=best_J,
        trials=trials,
        baseline_breakdown=cost_breakdown(baseline_result, lenses),
        best_breakdown=cost_breakdown(best_result, lenses),
    )
