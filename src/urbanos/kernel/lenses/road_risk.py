"""RoadRisk lens — Vision Zero / KSI collision history as an advisory display overlay.

Fit C of the data-driven roadmap (``docs/research/tpf-and-data-driven-lenses.md`` §6, the
"real source/demand lenses" track; ADR-0036). A Killed-or-Seriously-Injured collision is a
real, geocoded record of *where the road has historically been dangerous*. Counting
severity-weighted KSI records near each substrate node gives a static **road-danger density**
— a different axis of intelligence from the crowd crush and from the civic Safety index (food
inspections). This lens lifts that field onto the substrate (``adapters.road_risk_by_node`` —
real data, synthetic fallback offline) and writes it as its OWN advisory overlay, so the map
can show *where the road is dangerous* next to *where the crush actually piles up* — and report
how much the egress funnels the crowd through historically dangerous places.

Honesty stance (roadmap §7 — none regressed; mirrors MobilityDemand/TransitLoad)
--------------------------------------------------------------------------------
- **Display-only, additive, no headline movement.** Read-only on the crowd fields
  (``load``/``congestion``/``risk``): it only writes its own ``road_risk`` overlay and reports
  advisory metrics. It declares **no levers** and contributes **zero cost**, and it lives in
  ``scenarios.extra_display_lenses`` (excluded from the optimizer's objective ``J``), so it
  CANNOT move the chosen intervention or any headline dollar figure (the additivity contract
  test pins this).
- **Real danger under the demo, synthetic fallback in CI/dev.** A committed downtown slice
  (``demo_data/ksi__downtown.csv`` — real 2014+ KSI records, ``scripts/fetch_ksi.py``) backs the
  demo (``DATA_DIR=demo_data``). Without that slice on the loader's path (CI/dev) the adapter
  falls back to a deterministic synthetic field, so tests stay offline and the lens always runs.
- **Static field.** Unlike the time-varying demand lenses, road risk is a fixed property of the
  network: the same per-node density every step. ``observe`` still reports each step so the
  exposure metric reflects how the *crush* (which does evolve) overlaps the fixed danger field.
- **Offline-safe.** Constructed bare (no field) the lens is an inert no-op.
"""
from __future__ import annotations

import math

import numpy as np

from ..kernel.operators import Lens
from ..kernel.state import State, Substrate

# Provenance marker — the FALLBACK label, accurate in CI/dev where the synthetic field is used.
# Under the demo (DATA_DIR=demo_data) the same shape carries the real committed KSI density.
# Not surfaced at runtime; either way the lens is clearly ADVISORY — display-only, never priced.
PROVENANCE = "synthetic/advisory"


class RoadRiskLens(Lens):
    """Advisory display lens: severity-weighted KSI collision density lifted onto the substrate.

    Construct with a ``{node_id: density}`` map (see ``adapters.road_risk_by_node``).
    Constructed bare it is inert (no field → writes nothing, reports nothing, never an error),
    so it is always safe to include in a stack. Declares no levers and contributes no cost — it
    is display-only and excluded from the optimizer's objective ``J``.
    """

    name = "road_risk"

    def __init__(
        self, node_risk: dict[str, float] | None = None, *, weight: float = 1.0
    ) -> None:
        self.node_risk = dict(node_risk) if node_risk else None
        self.weight = weight
        self._risk: np.ndarray | None = None   # baked, NORMALISED (0..1) per-node density

    # -- configuration ------------------------------------------------------
    def configure(self, substrate: Substrate) -> None:
        """Bake the per-node density into a normalised ``(N,)`` array. Only NON-SINK nodes carry
        risk (a sink is an abstract exit line, not a real road location). Values are validated
        (negative / NaN / inf dropped) and normalised by the peak so the overlay is a scale-free
        0..1 danger field. Inert when constructed bare."""
        self._risk = None
        if not self.node_risk:
            return
        risk = np.zeros(substrate.n, dtype=float)
        for i, nid in enumerate(substrate.ids):
            if substrate.is_sink[i]:
                continue
            v = float(self.node_risk.get(nid, 0.0))
            if math.isfinite(v) and v > 0.0:
                risk[i] = v
        np.nan_to_num(risk, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(risk.max())
        if peak > 0.0:
            risk = risk / peak     # scale-free 0..1 (the relative danger shape is the claim)
        self._risk = risk

    # -- per-step overlay ---------------------------------------------------
    def couple(self, state: State, t: float) -> None:
        """Write ONLY this lens's advisory ``road_risk`` overlay (read-only on
        ``load``/``congestion``/``risk`` — it never mutates a crowd field, so it cannot perturb
        the kernel or any other lens). The field is static (same every step). Inert when bare."""
        if self._risk is None:
            return
        state.fields["road_risk"] = self._risk

    # -- reporting ----------------------------------------------------------
    def observe(self, state: State, t: float) -> dict[str, float]:
        """Advisory, display-only metrics (no dollars, no lever influence):

        - ``road_risk_peak``: the most dangerous node's normalised density (constant over the run).
        - ``crush_road_exposure``: a scale-free cosine in ``[0, 1]`` — how much *where the crowd is
          crushing* (``load``) overlaps *where the road is historically dangerous* (``road_risk``).
          A high value means the egress funnels the crowd through KSI hotspots — a road-safety
          concern the lever can ease by spreading the crowd. Purely informational: it prices
          nothing and steers nothing."""
        if self._risk is None:
            return {}
        out: dict[str, float] = {"road_risk_peak": float(self._risk.max())}
        load = np.asarray(state.fields.get("load"), dtype=float)
        if load.shape == self._risk.shape:
            nl = float(np.linalg.norm(load))
            nr = float(np.linalg.norm(self._risk))
            if nl > 0.0 and nr > 0.0:
                out["crush_road_exposure"] = float(
                    np.clip(np.dot(load, self._risk) / (nl * nr), 0.0, 1.0)
                )
            else:
                out["crush_road_exposure"] = 0.0
        return out

    def cost(self, result: object) -> float:
        """No J term — RoadRisk is a display-only advisory overlay, never a priced lever, so it
        can never move a headline dollar figure."""
        return 0.0
