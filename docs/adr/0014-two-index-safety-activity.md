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
risk_activity = round(1 - exp(-0.06 * open_permits), 3)                       # construction
risk_safety   = round(1 - exp(-0.45 * (0.3*minor_visits + 1.0*severe_visits)), 3)  # food safety
```

- `open_permits` — building permits whose status is not "closed".
- `minor_visits` / `severe_visits` — **NON-pass inspection VISITS** for the address,
  split by severity via `classify_inspection`: a **Conditional Pass** is `minor`, a
  **Fail / Closed / Suspended / conviction** is `severe`. Visits are already de-duped by
  `(estId, date)` in the loader (ADR 0013), collapsing deficiency line-items into one
  visit; a visit's severity is its worst outcome.

The two `k` constants are tuned so each axis produces a usable gradient on the committed
downtown slice (see Consequences), not a saturated single bucket.

### Bands (unchanged thresholds, applied to EACH index)

`risk_band(x)` (reused verbatim): `none` (≤0) / `low` (<0.34) / `medium` (<0.67) /
`high` (≥0.67). Each index gets its own band — `band_safety`, `band_activity`.

### Severity weighting on the safety index (IMPLEMENTED — Section 6)

The safety index **is severity-weighted**: a minor (Conditional Pass) visit weighs
`0.3`, a severe (Fail / Closed / conviction) visit weighs `1.0`. This was originally
deferred as a "future refinement", but verification found it was **required, not
optional** — an *unweighted* count `1 - exp(-0.45 * adverse_visits)` is mathematically
broken for triage:

> `adverse_visits = 1` → `1 - exp(-0.45) = 0.362`, which is **already ≥ 0.34 = MEDIUM**.
> So **no integer visit count can ever land in LOW** (`0 < x < 0.34`) — the LOW band is
> structurally **dead**, and on the real slice the safety axis collapsed to a wall of
> MEDIUM (HIGH 1 / **MED 21** / **LOW 0** / NONE 5). This is the very saturation the
> two-index split was meant to cure, reintroduced by treating a gentle Conditional Pass
> as a full-weight adverse visit.

Down-weighting minors to `0.3` restores a real gradient:

| signal | weighted sum | safety | band |
|---|---|---|---|
| 1 Conditional Pass | 0.3 | 0.126 | **LOW** |
| 2 Conditional Pass | 0.6 | 0.237 | LOW |
| 3 Conditional Pass | 0.9 | 0.333 | LOW |
| 4 Conditional Pass | 1.2 | 0.417 | MEDIUM |
| 1 severe (Fail) | 1.0 | 0.362 | MEDIUM |
| 2 severe (Fail) | 2.0 | 0.593 | MEDIUM |

So a Conditional-Pass-only address now reads **LOW** (a routine follow-up), while the
single real **conviction** site and other Fail sites stand out as genuine MEDIUM. The
weights are documented and transparent; severity still also appears in the two-line
narrative (it names the total adverse visits and breaks out the severe count) and the
deterministic claims (ADR 0013's honesty rules are intact).

### Wiring

- `agents/subagents.py` — `ComplianceAgent` computes both indices on the `Finding`
  (`risk_safety`, `risk_activity`); the single `graded_score` is removed.
- `agents/supervisor.py` — `RiskReport` carries `risk_safety, band_safety,
  risk_activity, band_activity`. `score_only` returns BOTH (`{risk_safety,
  risk_activity}`) for pin coloring. Any single sort key is derived **locally** as
  `max(risk_safety, risk_activity)` — a site is flagged if **either** axis is elevated.
- `agents/verify.py` — `safety_index(minor_visits, severe_visits)` applies the §6
  severity weights; `compliance_counts` returns `(minor, severe, open_permits)`;
  `two_line_narrative(minor_visits, severe_visits, open_permits)` renders a **Safety**
  line (naming total adverse visits + the severe breakout) and a **Construction** line
  (ADR §8 templates), every figure traced to the counts. The hallucination guard on the
  per-claim assessment is unchanged.
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
  high` no longer exists. The new golden (2 open permits + 2 **severe** inspection
  visits) survives severity weighting unchanged, because severe visits weigh 1.0:

  ```
  risk_activity = 1 - exp(-0.06*2)         = 0.113  → low
  risk_safety   = 1 - exp(-0.45*(1.0*2))   = 0.593  → medium
  ```

- **Triage is now per-team — and the safety LOW band is alive.** On the committed
  `demo_data/` slice (192 permits, 135 inspection visits, 105 licences; 27 geocoded
  addresses) the two axes spread as (after severity weighting):

  | Band   | Safety | Activity |
  |--------|:------:|:--------:|
  | high   |   0    |    2     |
  | medium |   2    |    3     |
  | low    |  20    |    8     |
  | none   |   5    |   14     |

  The safety axis is no longer a wall of MEDIUM (the un-weighted version gave
  HIGH 1 / MED 21 / **LOW 0** / NONE 5). It is now a real spread: the bulk of sites are
  Conditional-Pass follow-ups (LOW), with only the genuine Fail/conviction sites rising
  to MEDIUM. A manager can read "where are the food-safety problems" and "where is
  construction hot" off two separate lists instead of one conflated number.

- **Hero pin (500 Bloor St W)** is `safety low / activity medium` — it still fuses all
  three datasets and is flagged on the activity axis (the contract test asserts flagged
  on at least one). Its lone Conditional Pass correctly reads LOW on safety now (a
  routine follow-up), while its open permits drive the activity MEDIUM — the honest read.

- **Grounded citations + offline map are untouched.** The narrator still cites only real
  evidence tags; the basemap stays 100% offline.

- **A focused test lane** (`tests/test_two_index.py`) pins both formulas, the per-index
  bands, the two-line narrative, the digest two-list split, and that no blended
  `risk_score` leaks through the API/MCP surface.
