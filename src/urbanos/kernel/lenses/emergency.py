"""Emergency lens — fire-service incident-response density as an advisory display overlay.

Fit C of the data-driven roadmap (``docs/research/tpf-and-data-driven-lenses.md`` §6, the
"real source/demand lenses" track; ADR-0041). A Toronto Fire Services incident response is a
real, geocoded record of *where the city's emergency-response load actually lands*. Counting
severity-weighted response records near each substrate node gives a static **emergency-response
density** — a different axis of intelligence from the crowd crush, the civic Safety index (food
inspections), and the historical road danger (KSI). It pairs naturally with the EMS-access
overlay: that one shows where blocked roads make help *slow to arrive*; this one shows where the
city is *called to respond most often* in the first place. This lens lifts that field onto the
substrate (``adapters.emergency_by_node`` — real data, synthetic fallback offline) and writes it
as its OWN advisory overlay, so the map can show *where emergencies cluster* next to *where the
crush actually piles up* — and report how much the egress funnels the crowd through those places.

Honesty stance (roadmap §7 — none regressed; mirrors RoadRisk/MobilityDemand/TransitLoad)
-----------------------------------------------------------------------------------------
- **What this signal IS (and is not).** The backing dataset is TFS *fire-incident **responses***,
  which INCLUDE alarm activations and outdoor/grass fires — NOT only structure fires. So this is
  honestly a **"where emergencies cluster / where response load concentrates"** signal, NOT a
  "structure-fire count". The relative shape is the claim, not the absolute magnitude.
- **Display-only, additive, no headline movement.** Read-only on the crowd fields
  (``load``/``congestion``/``risk``): it only writes its own ``emergency`` overlay and reports
  advisory metrics. It declares **no levers** and contributes **zero cost**, and it lives in
  ``scenarios.extra_display_lenses`` (excluded from the optimizer's objective ``J``), so it
  CANNOT move the chosen intervention or any headline dollar figure (the additivity contract
  test pins this).
- **Real responses under the demo, synthetic fallback in CI/dev.** A committed downtown slice
  (``demo_data/emergency__downtown.csv`` — real TFS incident responses, ``scripts/fetch_fire_incidents.py``)
  backs the demo (``DATA_DIR=demo_data``). Without that slice on the loader's path (CI/dev) the
  adapter falls back to a deterministic synthetic field, so tests stay offline and the lens always
  runs.
- **Static field.** Unlike the time-varying demand lenses, emergency-response density is a fixed
  property of the network: the same per-node density every step. ``observe`` still reports each
  step so the exposure metric reflects how the *crush* (which does evolve) overlaps the fixed
  response-load field.
- **Offline-safe.** Constructed bare (no field) the lens is an inert no-op.
"""
from __future__ import annotations

import math

import numpy as np

from ..kernel.operators import Lens
from ..kernel.state import State, Substrate

# Provenance marker — REAL/measured: the committed slice is real, geocoded TFS incident-response
# locations (severity-weighted). The relative shape is the claim. Either way the lens is clearly
# ADVISORY — display-only, never priced — and is honestly a RESPONSE-LOAD signal (includes alarms),
# not a structure-fire count.
PROVENANCE = "real/measured"


class EmergencyLens(Lens):
    """Advisory display lens: severity-weighted fire-service incident-response density on the substrate.

    Construct with a ``{node_id: density}`` map (see ``adapters.emergency_by_node``).
    Constructed bare it is inert (no field → writes nothing, reports nothing, never an error),
    so it is always safe to include in a stack. Declares no levers and contributes no cost — it
    is display-only and excluded from the optimizer's objective ``J``.
    """

    name = "emergency"

    def __init__(
        self, node_emergency: dict[str, float] | None = None, *, weight: float = 1.0
    ) -> None:
        self.node_emergency = dict(node_emergency) if node_emergency else None
        self.weight = weight
        # Baked, NORMALISED (0..1) per-node density. Same attribute name as RoadRiskLens
        # (``self._risk``) by design: ``services.emergency_overlay`` reads ``_risk`` exactly the
        # way ``road_risk_overlay`` does, so the two static-density overlays share one read path.
        self._risk: np.ndarray | None = None

    # -- configuration ------------------------------------------------------
    def configure(self, substrate: Substrate) -> None:
        """Bake the per-node density into a normalised ``(N,)`` array. Only NON-SINK nodes carry
        emergency load (a sink is an abstract exit line, not a real city location). Values are
        validated (negative / NaN / inf dropped) and normalised by the peak so the overlay is a
        scale-free 0..1 response-load field. Inert when constructed bare."""
        self._risk = None
        if not self.node_emergency:
            return
        risk = np.zeros(substrate.n, dtype=float)
        for i, nid in enumerate(substrate.ids):
            if substrate.is_sink[i]:
                continue
            v = float(self.node_emergency.get(nid, 0.0))
            if math.isfinite(v) and v > 0.0:
                risk[i] = v
        np.nan_to_num(risk, copy=False, nan=0.0, posinf=0.0, neginf=0.0)
        peak = float(risk.max())
        if peak > 0.0:
            risk = risk / peak     # scale-free 0..1 (the relative response shape is the claim)
        self._risk = risk

    # -- per-step overlay ---------------------------------------------------
    def couple(self, state: State, t: float) -> None:
        """Write ONLY this lens's advisory ``emergency`` overlay (read-only on
        ``load``/``congestion``/``risk`` — it never mutates a crowd field, so it cannot perturb
        the kernel or any other lens). The field is static (same every step). Inert when bare."""
        if self._risk is None:
            return
        state.fields["emergency"] = self._risk

    # -- reporting ----------------------------------------------------------
    def observe(self, state: State, t: float) -> dict[str, float]:
        """Advisory, display-only metrics (no dollars, no lever influence):

        - ``emergency_peak``: the highest-response node's normalised density (constant over the run).
        - ``crush_emergency_exposure``: a scale-free cosine in ``[0, 1]`` — how much *where the
          crowd is crushing* (``load``) overlaps *where the city's emergency-response load
          concentrates* (``emergency``). A high value means the egress funnels the crowd through
          high-incident areas — an emergency-response concern the lever can ease by spreading the
          crowd. Purely informational: it prices nothing and steers nothing."""
        if self._risk is None:
            return {}
        out: dict[str, float] = {"emergency_peak": float(self._risk.max())}
        load = np.asarray(state.fields.get("load"), dtype=float)
        if load.shape == self._risk.shape:
            nl = float(np.linalg.norm(load))
            nr = float(np.linalg.norm(self._risk))
            if nl > 0.0 and nr > 0.0:
                out["crush_emergency_exposure"] = float(
                    np.clip(np.dot(load, self._risk) / (nl * nr), 0.0, 1.0)
                )
            else:
                out["crush_emergency_exposure"] = 0.0
        return out

    def cost(self, result: object) -> float:
        """No J term — Emergency is a display-only advisory overlay, never a priced lever, so it
        can never move a headline dollar figure."""
        return 0.0
