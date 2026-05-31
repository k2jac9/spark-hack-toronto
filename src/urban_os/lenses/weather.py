"""Weather lens — rain raises crowd-safety risk and slows network drainage.

A rainstorm during egress does two physical things to a transit network, and
this lens models both through the four-operator contract:

- **Slower drainage.** Wet platforms, umbrellas, and cautious boarding cut the
  effective per-minute throughput of every link. Because the kernel's
  ``transport`` reads ``substrate.edge_cap`` *each step* (between ``source`` and
  ``couple``), the lens scales that baked array down in ``source`` and restores
  it in ``couple`` — a transient, fully reversible "rain tax" on link capacity
  that never permanently corrupts the substrate other lenses share.
- **Higher crush risk at the same density.** Rain makes a given platform density
  more dangerous (slips, reduced visibility, people bunching under shelter), so
  the lens *multiplies* the standing ``risk`` field by a wetness factor after the
  economic lens has computed the base ``risk = ρ^2.5``. Ordering matters: the
  Weather lens must run **after** the Economic lens in the stack so its
  multiplier lands on a populated risk field (the default ``_lenses()`` stack
  already ends with EconomicLens; appending WeatherLens is the right order).

The rain itself is a Gaussian-in-time intensity pulse (a passing cell), peaking
at ``peak_time`` with width ``width`` minutes and a 0..1 ``intensity`` scale.

The control **lever** is *shelter deployment*: opening covered queueing /
adding marshals removes a fraction of the rain risk penalty (and recovers some
throughput), at a per-minute staffing cost. That gives the optimizer a real
interior trade-off — shelter buys safety but isn't free — exactly mirroring the
EventSurge staggered-release lever.

Calibration constants below are plausibility-checked, not ground-truth — flagged
the same way the economic lens flags its value-of-time.
"""
from __future__ import annotations

import math

import numpy as np

from ..kernel.loop import SimResult
from ..kernel.operators import Lens, Lever
from ..kernel.state import State, Substrate

# At full rain (intensity 1.0, no shelter), effective link throughput drops to
# this fraction of dry capacity (≈25% slower boarding/walking). Plausible upper
# bound for a heavy downtown cell; flagged as synthetic in provenance.
_MAX_CAP_PENALTY = 0.25
# At full rain (intensity 1.0, no shelter), the crowd-safety risk field is
# multiplied by up to (1 + this). 0.6 ⇒ a wet platform at the same density reads
# ~60% more dangerous than a dry one.
_MAX_RISK_BONUS = 0.6
# Per-(person·minute of exposure) dollar cost of standing in the rain queue when
# unsheltered — a small comfort/health penalty layered on the economic delay
# cost. Synthetic; calibrated with _SHELTER_COST / VALUE_OF_SAFETY in ADR-0015.
_EXPOSURE_COST = 0.05
# Per-(person·minute) cost of sheltering someone who is actually in the system
# while it is raining ($/person·min of covered, rained-on load). Staffing is now
# integrated against the **in-system load present during rain** (not a static
# crowd_size), so holding the crowd longer — which empties the platforms before
# the rain peak — makes shelter *cheaper*, not more expensive (audit finding:
# the old static-crowd staffing was non-monotonic in release). Calibrated in
# ADR-0015 so shelter is a genuine interior optimum.
_SHELTER_COST = 0.14


class WeatherLens(Lens):
    """Rain as a time-varying tax on throughput and a multiplier on risk."""

    name = "weather"

    def __init__(
        self,
        *,
        peak_time: float,
        intensity: float = 1.0,
        width: float = 20.0,
        crowd_size: float = 0.0,
        max_shelter: float = 1.0,
        weight: float = 1.0,
    ) -> None:
        # --- input validation at the boundary -------------------------------
        if width <= 0:
            raise ValueError("width must be > 0 minutes")
        if not 0.0 <= intensity <= 1.0:
            raise ValueError("intensity must be in [0, 1]")
        if not 0.0 <= max_shelter <= 1.0:
            raise ValueError("max_shelter must be in [0, 1]")
        if crowd_size < 0:
            raise ValueError("crowd_size must be >= 0")
        self.peak_time = float(peak_time)
        self.intensity = float(intensity)
        self.width = float(width)
        self.crowd_size = float(crowd_size)
        self.max_shelter = float(max_shelter)
        self.weight = float(weight)
        self._saved_edge_cap: np.ndarray | None = None
        self._dry_edge_cap: np.ndarray | None = None

    # ------------------------------------------------------------------ config
    def configure(self, substrate: Substrate) -> None:
        # Keep a pristine copy of the dry link capacities. We always derive the
        # rained-on capacity from *this* baseline so repeated runs / repeated
        # steps never compound the penalty.
        self._dry_edge_cap = np.array(substrate.edge_cap, dtype=float, copy=True)

    # ------------------------------------------------------------------ helpers
    def _rain_at(self, t: float) -> float:
        """Gaussian-in-time rain intensity in [0, intensity] at minute ``t``."""
        z = (t - self.peak_time) / self.width
        return self.intensity * math.exp(-0.5 * z * z)

    @staticmethod
    def _shelter(state: State) -> float:
        """Effective shelter fraction in [0, 1] (lever value, clamped)."""
        return float(np.clip(state.params.get("shelter_fraction", 0.0), 0.0, 1.0))

    def _wetness(self, t: float, shelter: float) -> float:
        """Net rain exposure after shelter: rain·(1 − shelter), in [0, 1]."""
        return self._rain_at(t) * (1.0 - shelter)

    # ------------------------------------------------------------------ source
    def source(self, state: State, t: float) -> None:
        """Scale link capacity DOWN before transport runs this step.

        ``transport`` reads ``substrate.edge_cap`` next, so this is how rain
        slows drainage. We snapshot whatever is currently in ``edge_cap`` and
        write a penalised copy; ``couple`` restores the snapshot afterwards so
        the substrate other lenses see is untouched between steps.
        """
        sub = state.substrate
        # Defensive: if configure() never ran, fall back to the live array.
        dry = self._dry_edge_cap
        if dry is None or dry.shape != sub.edge_cap.shape:
            dry = np.array(sub.edge_cap, dtype=float, copy=True)
            self._dry_edge_cap = dry
        self._saved_edge_cap = np.array(sub.edge_cap, dtype=float, copy=True)
        wet = self._wetness(t, self._shelter(state))
        factor = 1.0 - _MAX_CAP_PENALTY * wet      # in [1-_MAX_CAP_PENALTY, 1]
        sub.edge_cap[:] = dry * factor

    # ------------------------------------------------------------------ couple
    def couple(self, state: State, t: float) -> None:
        """Restore link capacity, then amplify risk and book exposure cost.

        Runs after ``transport`` and after the economic lens has set the base
        ``risk`` field, so multiplying here lands on real values.
        """
        sub = state.substrate
        if self._saved_edge_cap is not None and self._saved_edge_cap.shape == sub.edge_cap.shape:
            sub.edge_cap[:] = self._saved_edge_cap
        self._saved_edge_cap = None

        wet = self._wetness(t, self._shelter(state))
        # Multiplicatively amplify the standing crowd-safety risk field.
        if "risk" in state.fields:
            state.fields["risk"] = state.fields["risk"] * (1.0 + _MAX_RISK_BONUS * wet)
        # Exposure: people still in the system are standing in the rain this
        # step (unsheltered fraction), and that discomfort costs a little.
        dt = float(state.params.get("dt", 1.0))
        in_system = float(state.fields["load"].sum())
        exposure_person_min = in_system * wet * dt
        state.params["_weather_exposure_step"] = exposure_person_min
        # Track the realised wetness and in-system load for the observer/cost.
        state.params["_weather_wetness_step"] = wet
        state.params["_weather_in_system_step"] = in_system

    # ----------------------------------------------------------------- observe
    def observe(self, state: State, t: float) -> dict[str, float]:
        wet = float(state.params.get("_weather_wetness_step", 0.0))
        exposure = float(state.params.get("_weather_exposure_step", 0.0))
        in_system = float(state.params.get("_weather_in_system_step", 0.0))
        return {
            "rain_intensity": float(self._rain_at(t)),
            "wetness": wet,
            "exposure_cost": exposure * _EXPOSURE_COST,
            # Person·minutes of in-system load standing in the rain this step,
            # at the unsheltered-equivalent rain level (the staffing base before
            # the shelter fraction is applied). Integrated in cost().
            "shelter_load_min": in_system * self._rain_at(t),
        }

    # ------------------------------------------------------------------ levers
    def levers(self) -> list[Lever]:
        """Shelter coverage fraction in 0.25 steps, 0 (none) → max_shelter."""
        top = self.max_shelter
        grid = [v for v in np.arange(0.0, top + 1e-9, 0.25) if v <= top + 1e-9]
        if not grid:
            grid = [0.0]
        return [Lever(name="shelter_fraction", values=grid, label="Shelter coverage")]

    # -------------------------------------------------------------------- cost
    def cost(self, result: SimResult) -> float:
        """This lens's J term: exposure discomfort + shelter staffing dollars.

        Exposure is summed from the per-step series (the part the optimizer can
        shrink by deploying shelter). Shelter staffing is ``_SHELTER_COST`` per
        person·minute of **in-system load that is actually standing in the rain**,
        integrated over the run (``Σ in_system·rain·dt``) and scaled by the
        shelter fraction covering them. Re-basing on the live in-system load — not
        a static ``crowd_size`` — is the audit fix: holding the crowd longer
        drains the platforms before the rain peak, so fewer people are sheltered
        and the staffing bill *falls* with release (it is monotone, not the old
        3×-with-release blow-up). Non-zero only when shelter is engaged, so doing
        nothing pays full exposure but no staffing — that tension is the interior
        optimum, mirroring EventSurge's hold-discount.
        """
        exposure_dollars = float(sum(result.series("exposure_cost")))
        shelter = float(np.clip(result.params.get("shelter_fraction", 0.0), 0.0, 1.0))
        staffing = 0.0
        if shelter > 0.0:
            dt = float(result.dt)
            # Person·minutes of in-system load sheltered from the rain, integrated
            # over the run (recorded per step by observe()). Falls back to the
            # static crowd_size basis only if the metric is absent (e.g. a bare
            # WeatherLens with no observe series recorded).
            load_min = result.series("shelter_load_min")
            if load_min:
                staffing_basis = float(sum(load_min)) * dt
            else:  # pragma: no cover - defensive: no recorded series
                rain_minutes = sum(self._rain_at(t) for t in result.times) * dt
                staffing_basis = self.crowd_size * rain_minutes
            staffing = shelter * _SHELTER_COST * staffing_basis
        return exposure_dollars + staffing
