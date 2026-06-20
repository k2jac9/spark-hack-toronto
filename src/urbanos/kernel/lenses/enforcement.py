"""Enforcement lens — automated traffic-enforcement device density as an advisory display overlay.

Fit C of the data-driven roadmap (``docs/research/tpf-and-data-driven-lenses.md`` §6, the
"real source/demand lenses" track; ADR-0039). An automated-enforcement device (a red-light camera
or a speed camera) is a real, geocoded marker of *where the city actively manages dangerous
traffic*. Counting severity-weighted device records near each substrate node gives a static
**enforcement-coverage density** — a different axis of intelligence from the crowd crush, from the
civic Safety index (food inspections), from the historical RoadRisk danger field (KSI collisions),
and from the active RoadDisruption field (current closures). It completes the road-safety triad:
RoadRisk asks *where the road is historically dangerous*, RoadDisruption asks *where the road is
constrained right now*, and Enforcement asks *where the city actively enforces against dangerous
driving*. This lens lifts that field onto the substrate (``adapters.enforcement_by_node`` — real
data, synthetic fallback offline) and writes it as its OWN advisory overlay, so the map can show
*where automated enforcement is concentrated* next to *where the crush actually piles up* — and
report how much the egress funnels the crowd through actively enforced places.

Honesty stance (roadmap §7 — none regressed; mirrors RoadRisk/RoadDisruption/MobilityDemand)
--------------------------------------------------------------------------------------------
- **Display-only, additive, no headline movement.** Read-only on the crowd fields
  (``load``/``congestion``/``risk``): it only writes its own ``enforcement`` overlay and reports
  advisory metrics. It declares **no levers** and contributes **zero cost**, and it lives in
  ``scenarios.extra_display_lenses`` (excluded from the optimizer's objective ``J``), so it
  CANNOT move the chosen intervention or any headline dollar figure (the additivity contract
  test pins this).
- **Real devices under the demo, synthetic fallback in CI/dev.** A committed downtown slice
  (``demo_data/enforcement__downtown.csv`` — 51 real downtown red-light + speed cameras,
  ``scripts/fetch_enforcement.py``) backs the demo (``DATA_DIR=demo_data``). Without that slice
  on the loader's path (CI/dev) the adapter falls back to a deterministic synthetic field, so
  tests stay offline and the lens always runs. The device LOCATIONS are real (``PROVENANCE =
  "real/measured"``).
- **Static field.** Unlike the time-varying demand lenses, enforcement coverage is a fixed
  property of the network: the same per-node density every step. ``observe`` still reports each
  step so the exposure metric reflects how the *crush* (which does evolve) overlaps the fixed
  enforcement field.
- **Offline-safe.** Constructed bare (no field) the lens is an inert no-op.

Internal note: like ``RoadRiskLens`` / ``RoadDisruptionLens`` the baked normalised field is stored
on ``self._risk`` (NOT ``self._enforcement``), so the overlay helper ``services.enforcement_overlay``
reads it the same way (``getattr(lens, "_risk", None)``) — kept consistent with the rest of the
road-safety triad on purpose.
"""
from __future__ import annotations

import math

import numpy as np

from ..kernel.operators import Lens
from ..kernel.state import State, Substrate

# Provenance marker — automated-enforcement device LOCATIONS are real (red-light + speed cameras),
# so this is "real/measured" (matching the rest of the road-safety triad's sources). Under CI/dev
# the synthetic fallback stands in, but either way the lens is clearly ADVISORY — display-only,
# never priced. Not surfaced at runtime as a per-figure claim.
PROVENANCE = "real/measured"


class EnforcementLens(Lens):
    """Advisory display lens: severity-weighted automated-enforcement device density lifted onto the substrate.

    Construct with a ``{node_id: density}`` map (see ``adapters.enforcement_by_node``).
    Constructed bare it is inert (no field → writes nothing, reports nothing, never an error),
    so it is always safe to include in a stack. Declares no levers and contributes no cost — it
    is display-only and excluded from the optimizer's objective ``J``.
    """

    name = "enforcement"

    def __init__(
        self, node_enforcement: dict[str, float] | None = None, *, weight: float = 1.0
    ) -> None:
        self.node_enforcement = dict(node_enforcement) if node_enforcement else None
        self.weight = weight
        self._risk: np.ndarray | None = None   # baked, NORMALISED (0..1) per-node density

    # -- configuration ------------------------------------------------------
    def configure(self, substrate: Substrate) -> None:
        """Bake the per-node density into a normalised ``(N,)`` array. Only NON-SINK nodes carry
        enforcement (a sink is an abstract exit line, not a real road location). Values are
        validated (negative / NaN / inf dropped) and normalised by the peak so the overlay is a
        scale-free 0..1 enforcement-coverage field. Inert when constructed bare."""
        self._risk = None
        if not self.node_enforcement:
            return
        risk = np.zeros(substrate.n, dtype=float)
        for i, nid in enumerate(substrate.ids):
            if substrate.is_sink[i]:
                continue
            v = float(self.node_enforcement.get(nid, 0.0))
            if math.isfinite(v) and v > 0.0:
                risk[i] = v
        np.nan_to_num(risk, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(risk.max())
        if peak > 0.0:
            risk = risk / peak     # scale-free 0..1 (the relative coverage shape is the claim)
        self._risk = risk

    # -- per-step overlay ---------------------------------------------------
    def couple(self, state: State, t: float) -> None:
        """Write ONLY this lens's advisory ``enforcement`` overlay (read-only on
        ``load``/``congestion``/``risk`` — it never mutates a crowd field, so it cannot perturb
        the kernel or any other lens). The field is static (same every step). Inert when bare."""
        if self._risk is None:
            return
        state.fields["enforcement"] = self._risk

    # -- reporting ----------------------------------------------------------
    def observe(self, state: State, t: float) -> dict[str, float]:
        """Advisory, display-only metrics (no dollars, no lever influence):

        - ``enforcement_peak``: the most-enforced node's normalised density (constant over the run).
        - ``crush_enforcement_exposure``: a scale-free cosine in ``[0, 1]`` — how much *where the
          crowd is crushing* (``load``) overlaps *where automated enforcement is concentrated*
          (``enforcement``). A high value means the egress funnels the crowd through actively
          enforced places — where the city already watches for dangerous traffic. Purely
          informational: it prices nothing and steers nothing."""
        if self._risk is None:
            return {}
        out: dict[str, float] = {"enforcement_peak": float(self._risk.max())}
        load = np.asarray(state.fields.get("load"), dtype=float)
        if load.shape == self._risk.shape:
            nl = float(np.linalg.norm(load))
            nr = float(np.linalg.norm(self._risk))
            if nl > 0.0 and nr > 0.0:
                out["crush_enforcement_exposure"] = float(
                    np.clip(np.dot(load, self._risk) / (nl * nr), 0.0, 1.0)
                )
            else:
                out["crush_enforcement_exposure"] = 0.0
        return out

    def cost(self, result: object) -> float:
        """No J term — Enforcement is a display-only advisory overlay, never a priced lever, so it
        can never move a headline dollar figure."""
        return 0.0
