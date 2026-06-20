"""Bike-theft lens — reported bicycle-theft density as an advisory display overlay.

Fit C of the data-driven roadmap (``docs/research/tpf-and-data-driven-lenses.md`` §6, the
"real source/demand lenses" track; ADR-0040). A reported bicycle theft is a real, geocoded
record of *where bikes actually get stolen*. Counting severity-weighted theft records near each
substrate node gives a static **bike-theft density** — a property-crime / cycling-safety axis of
intelligence distinct from the crowd crush, the historical road-danger (RoadRisk / KSI), and the
civic Safety index (food inspections). It pairs naturally with the bike-demand (MobilityDemand,
ADR-0030) + footfall (ADR-0037) lenses: *where people ride and leave bikes* vs. *where those
bikes get stolen*. This lens lifts that field onto the substrate
(``adapters.bike_theft_by_node`` — real data, synthetic fallback offline) and writes it as its
OWN advisory overlay, so the map can show *where bikes are stolen* next to *where the crush
actually piles up* — and report how much the egress funnels the crowd through theft hotspots.

Honesty stance (roadmap §7 — none regressed; mirrors RoadRisk/MobilityDemand/TransitLoad)
-----------------------------------------------------------------------------------------
- **Display-only, additive, no headline movement.** Read-only on the crowd fields
  (``load``/``congestion``/``risk``): it only writes its own ``bike_theft`` overlay and reports
  advisory metrics. It declares **no levers** and contributes **zero cost**, and it lives in
  ``scenarios.extra_display_lenses`` (excluded from the optimizer's objective ``J``), so it
  CANNOT move the chosen intervention or any headline dollar figure (the additivity contract
  test pins this).
- **Real thefts under the demo, synthetic fallback in CI/dev.** A committed downtown slice
  (``demo_data/bike_theft__downtown.csv`` — real reported bicycle thefts 2024-26,
  ``scripts/fetch_bike_theft.py``) backs the demo (``DATA_DIR=demo_data``). Without that slice on
  the loader's path (CI/dev) the adapter falls back to a deterministic synthetic field, so tests
  stay offline and the lens always runs.
- **Static field.** Unlike the time-varying demand lenses, bike-theft density is a fixed property
  of the network: the same per-node density every step. ``observe`` still reports each step so the
  exposure metric reflects how the *crush* (which does evolve) overlaps the fixed theft field.
- **Offline-safe.** Constructed bare (no field) the lens is an inert no-op.
"""
from __future__ import annotations

import math

import numpy as np

from ..kernel.operators import Lens
from ..kernel.state import State, Substrate

# Provenance marker — the lens is ADVISORY (display-only, never priced) either way. Under the demo
# (DATA_DIR=demo_data) the field carries the real committed reported-theft density; the slice is a
# count of real geocoded thefts (severity uniformly 1 — a count density), so we label it
# real/measured (the relative shape is the claim). Not surfaced at runtime.
PROVENANCE = "real/measured"


class BikeTheftLens(Lens):
    """Advisory display lens: severity-weighted reported bicycle-theft density lifted onto the
    substrate.

    Construct with a ``{node_id: density}`` map (see ``adapters.bike_theft_by_node``).
    Constructed bare it is inert (no field → writes nothing, reports nothing, never an error),
    so it is always safe to include in a stack. Declares no levers and contributes no cost — it
    is display-only and excluded from the optimizer's objective ``J``.
    """

    name = "bike_theft"

    def __init__(
        self, node_theft: dict[str, float] | None = None, *, weight: float = 1.0
    ) -> None:
        self.node_theft = dict(node_theft) if node_theft else None
        self.weight = weight
        self._risk: np.ndarray | None = None   # baked, NORMALISED (0..1) per-node density
        # NB: the baked field lives on ``self._risk`` — the SAME attribute name RoadRiskLens uses
        # (ADR-0036) — so ``services.bike_theft_overlay`` can read it identically to the road
        # overlays (one helper shape across the static-density lenses).

    # -- configuration ------------------------------------------------------
    def configure(self, substrate: Substrate) -> None:
        """Bake the per-node density into a normalised ``(N,)`` array. Only NON-SINK nodes carry
        theft density (a sink is an abstract exit line, not a real place a bike is locked up).
        Values are validated (negative / NaN / inf dropped) and normalised by the peak so the
        overlay is a scale-free 0..1 theft field. Inert when constructed bare."""
        self._risk = None
        if not self.node_theft:
            return
        risk = np.zeros(substrate.n, dtype=float)
        for i, nid in enumerate(substrate.ids):
            if substrate.is_sink[i]:
                continue
            v = float(self.node_theft.get(nid, 0.0))
            if math.isfinite(v) and v > 0.0:
                risk[i] = v
        np.nan_to_num(risk, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(risk.max())
        if peak > 0.0:
            risk = risk / peak     # scale-free 0..1 (the relative theft shape is the claim)
        self._risk = risk

    # -- per-step overlay ---------------------------------------------------
    def couple(self, state: State, t: float) -> None:
        """Write ONLY this lens's advisory ``bike_theft`` overlay (read-only on
        ``load``/``congestion``/``risk`` — it never mutates a crowd field, so it cannot perturb
        the kernel or any other lens). The field is static (same every step). Inert when bare."""
        if self._risk is None:
            return
        state.fields["bike_theft"] = self._risk

    # -- reporting ----------------------------------------------------------
    def observe(self, state: State, t: float) -> dict[str, float]:
        """Advisory, display-only metrics (no dollars, no lever influence):

        - ``bike_theft_peak``: the highest-theft node's normalised density (constant over the run).
        - ``crush_bike_theft_exposure``: a scale-free cosine in ``[0, 1]`` — how much *where the
          crowd is crushing* (``load``) overlaps *where bikes are historically stolen*
          (``bike_theft``). A high value means the egress funnels the crowd through theft hotspots
          — a property-crime / cycling-safety concern. Purely informational: it prices nothing and
          steers nothing."""
        if self._risk is None:
            return {}
        out: dict[str, float] = {"bike_theft_peak": float(self._risk.max())}
        load = np.asarray(state.fields.get("load"), dtype=float)
        if load.shape == self._risk.shape:
            nl = float(np.linalg.norm(load))
            nr = float(np.linalg.norm(self._risk))
            if nl > 0.0 and nr > 0.0:
                out["crush_bike_theft_exposure"] = float(
                    np.clip(np.dot(load, self._risk) / (nl * nr), 0.0, 1.0)
                )
            else:
                out["crush_bike_theft_exposure"] = 0.0
        return out

    def cost(self, result: object) -> float:
        """No J term — BikeTheft is a display-only advisory overlay, never a priced lever, so it
        can never move a headline dollar figure."""
        return 0.0
