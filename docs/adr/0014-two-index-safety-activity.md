# 0014 — Two independent indices: Safety + Activity (un-blend the risk score)

Status: Accepted
Date: 2026-05-30

## Context

Until now a single `risk_score` (0..1) and one `risk_band` summarized every address.
That score was a saturating function of a *severity-weighted sum* of two unrelated
signals — open building permits (construction activity) and adverse food-safety
inspection visits:

```
weight = 0.5*open_permits + 0.8*minor_visits + 2.0*severe_visits
risk    = 1 - exp(-0.35 * weight)
```

This **conflates two different questions a city answers with two different teams.**
A block with eight active building permits and a clean kitchen, and a restaurant with
zero permits but a failed inspection, could land on the *same* number — yet one needs a
**building inspector** and the other a **public-health inspector**. Blending them:

- **hides which axis is driving the score** (the manager can't tell a construction
  hotspot from a food-safety hotspot from the number alone);
- makes the score **non-actionable for triage** — you can't deploy the right team;
- couples two feeds so a change in permit volume moves the "safety" reading.

The right model is **two independent indices**, each on its own 0..1 scale, each read
through the *same* band thresholds, never summed.

## Decision

Replace the single `risk_score`/`risk_band` with **two independent indices** and their
two bands. No blended public score exists anywhere in the API, UI, MCP tools, or digest.

### Formulas (`agents/verify.py`)

```
risk_activity = round(1 - exp(-0.06 * open_permits), 3)     # construction
risk_safety   = round(1 - exp(-0.45 * adverse_visits), 3)   # food safety
```

- `open_permits` — building permits whose status is not "closed".
- `adverse_visits` — count of **NON-pass inspection VISITS** for the address. Visits are
  already de-duped by `(estId, date)` in the loader (ADR 0013), collapsing deficiency
  line-items into one visit; a visit counts as adverse when its worst outcome != `pass`.

The two `k` constants are tuned so each axis produces a usable gradient on the committed
downtown slice (see Consequences), not a saturated single bucket.

### Bands (unchanged thresholds, applied to EACH index)

`risk_band(x)` (reused verbatim): `none` (≤0) / `low` (<0.34) / `medium` (<0.67) /
`high` (≥0.67). Each index gets its own band — `band_safety`, `band_activity`.

### Severity is in the PROSE, not the safety score

`adverse_visits` counts every non-pass visit equally — a Conditional Pass and a
conviction both add 1. Severity (minor vs severe) is **not** in the index; it stays in
the two-line narrative and the deterministic claims (ADR 0013's honesty rules are
intact). **Severity-weighting the safety index is a documented future refinement** — it
would let a conviction outweigh a routine Conditional Pass on the score itself, at the
cost of a less transparent formula. Deferred deliberately.

### Wiring

- `agents/subagents.py` — `ComplianceAgent` computes both indices on the `Finding`
  (`risk_safety`, `risk_activity`); the single `graded_score` is removed.
- `agents/supervisor.py` — `RiskReport` carries `risk_safety, band_safety,
  risk_activity, band_activity`. `score_only` returns BOTH (`{risk_safety,
  risk_activity}`) for pin coloring. Any single sort key is derived **locally** as
  `max(risk_safety, risk_activity)` — a site is flagged if **either** axis is elevated.
- `agents/verify.py` — `two_line_narrative(adverse_visits, open_permits)` renders a
  **Safety** line and a **Construction** line (ADR §8 templates), every figure traced to
  the counts. The hallucination guard on the per-claim assessment is unchanged.
- `api/server.py`, `mcp_server.py` — `/analyze`, `/addresses`, `/digest`, `top_risk`,
  `analyze_address` all return both scores + both bands; **no `risk_score` leaks**.
- `agents/digest.py` — TWO priority lists (Safety by `risk_safety`, Activity by
  `risk_activity`); the briefing names each axis's hotspots separately and says where to
  send health vs building inspectors. The `_clean_label` "None"-token fix is kept.
- `api/static/map.html` — TWO badges (Safety / Activity) in the side panel + the 3D
  presentation card; pins/list color by `max(band_safety, band_activity)`; the legend
  explains the two axes; per-claim ✓verify, the offline invariant, MapLibre v5, and
  presentation mode are all intact.

## Consequences

- **The golden invariant changes — deliberately.** The old `100 Queen St W → 0.826,
  high` no longer exists. The new golden (2 open permits + 2 severe inspection visits):

  ```
  risk_activity = 1 - exp(-0.06*2) = 0.113  → low
  risk_safety   = 1 - exp(-0.45*2) = 0.593  → medium
  ```

- **Triage is now per-team.** On the committed `demo_data/` slice (192 permits, 135
  inspection visits, 105 licences; 27 geocoded addresses) the two axes spread as:

  | Band   | Safety | Activity |
  |--------|:------:|:--------:|
  | high   |   1    |    2     |
  | medium |  21    |    3     |
  | low    |   0    |    8     |
  | none   |   5    |   14     |

  A manager can now read "where are the food-safety problems" and "where is construction
  hot" off two separate lists instead of one conflated number.

- **Hero pin (500 Bloor St W)** is `safety medium / activity medium` — it still fuses all
  three datasets and is flagged on both axes (the contract test asserts flagged on at
  least one). It is no longer "high", because a single failed inspection + a couple of
  permits is a moderate, not severe, signal — which is the honest read.

- **Grounded citations + offline map are untouched.** The narrator still cites only real
  evidence tags; the basemap stays 100% offline.

- **A focused test lane** (`tests/test_two_index.py`) pins both formulas, the per-index
  bands, the two-line narrative, the digest two-list split, and that no blended
  `risk_score` leaks through the API/MCP surface.
