# 0013 — De-dup inspections by visit + severity/prose honesty

Status: Accepted
Date: 2026-05-30

## Context

DineSafe is published **one CSV row per deficiency line-item**, not one row per
inspection. In the committed `demo_data/dinesafe__downtown.csv` slice this means
**250 raw rows collapse to ~89 distinct (address, inspectionDate) visits** — so a
single dated inspection of a busy premises showed up as N separate "inspections".
Because the risk score sums per-inspection weight, this **inflated risk**: a building
with one Conditional-Pass visit carrying 9 deficiencies scored as if it had 9
inspections. The net effect was a useless triage signal — **~19 of the demo
addresses landed in HIGH** with almost nothing in MEDIUM/LOW.

Two related honesty problems surfaced alongside the over-count:

1. **"Adverse" was applied to Conditional Pass.** The prose called every non-Pass
   inspection "adverse", but a Conditional Pass is a routine minor follow-up, not an
   enforcement event. The score already weighted it correctly (minor 0.8 vs severe
   2.0) — only the *words* were wrong.
2. **Real enforcement outcomes were invisible.** The dataset's `OutcomeDesc` column
   carries the genuine signal (one real `"Conviction - Fined"` record in the slice),
   but the pipeline only read `inspectionStatus` (Pass / Conditional Pass), so an
   actual court conviction was scored identically to a clean Conditional Pass.

## Decision

Three coherent changes, score formula and weights unchanged:

1. **De-dup inspections by visit (`ingest/loader.py`).** When loading
   inspection-kind records and a usable date column exists, collapse rows sharing
   the same (normalized address, date) into **one visit record**: keep the **worst
   severity** across the group, and expose a `deficiency_count` attribute for
   display. If a file has **no usable date column**, fall back to per-row (so other
   feeds and fixtures are unaffected). Grouping is on the *normalized* (street-level)
   address — the same key the rest of the system joins on — which fuses unit-level
   variants of one building inspected the same day; the 250-row slice resolves to 76
   visits at that granularity.

2. **Prose honesty (`agents/subagents.py`, `agents/verify.py`).** Reserve the word
   **"adverse" for SEVERE outcomes only** (fail / closed / conviction). A Conditional
   Pass is reported as a **"Conditional Pass inspection visit"** (with its
   deficiency count, e.g. *"1 Conditional Pass inspection visit (9 deficiencies)"*),
   not "adverse". `graded_score` is untouched.

3. **Additive conviction severity (`ingest/loader.py`).** `inspectionStatus` stays
   the **primary** outcome (Conditional Pass → minor). **Additively**, if a visit's
   `OutcomeDesc` contains a conviction/order/closure keyword
   (`conviction`, `closed`, `closure`, `order`, `suspend`, `fined`), the visit is
   escalated to **SEVERE**. This makes the single real `"Conviction - Fined"` record
   a genuine severe site. We do **not** switch the primary column to `OutcomeDesc`
   (that would erase the Conditional-Pass minor signal), and the logic is robust to
   fixtures with no `OutcomeDesc` column.

## Consequences

- **Triage is now usable.** On the committed demo slice the band distribution moves
  from **HIGH 19 / MED 6 / LOW 0 / NONE 2** to **HIGH 6 / MED 11 / LOW 8 / NONE 2** —
  a real risk gradient instead of a saturated HIGH bucket. The single real conviction
  is the only SEVERE inspection site.
- **The golden invariant holds.** `100 Queen St W → 0.826, high` is preserved: the
  pinned `fixtures/dinesafe__sample.csv` gained an `inspectionDate` column giving its
  two "Fail" rows **distinct dates**, so they remain **two visits → two severe → weight
  5.0 → 0.826**.
- **Grounded-citation behavior is intact** — claims still cite only real evidence
  tags; the narrator prompt is unchanged.
- The `demo_data` count guard moves from `dinesafe: 250` to `dinesafe: 76` to lock in
  the de-dup.
