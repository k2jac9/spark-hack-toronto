# Urban-OS — Pitch (flagship track: Urban Operations)

## Tagline
**An operating system for the city: fuse the data, simulate the what-if, and
optimize one lever across transit, public safety, and local business — grounded,
and 100% on one box.**

## Thesis (10 seconds)
Most civic tools are single-purpose dashboards. We built a **microkernel for urban
dynamics** — a domain-agnostic kernel + a driver model for cities + portable
domain *lenses* + a governor that optimizes interventions — and proved it with
**four lenses on one kernel**, end-to-end on an NVIDIA GX10, with **no cloud and
no hallucinated numbers**.

## Run-of-show (~90 seconds, spoken)

> "Everything you'll see runs **100% on this GX10** — no cloud, no tile server, no
> internet. Watch — I'll unplug it. *[unplug]*
>
> First, the **Safety lens**. This is downtown Toronto, offline. Every pin is
> risk-scored on **two independent indices — Safety and Activity** — so a busy
> construction zone isn't confused with an unsafe one. I click **500 Bloor St
> West**: **medium Activity** (8 open permits — active construction to verify) and
> a flagged food-safety item. And every claim is grounded: it cites the open
> permits, a DineSafe conditional pass, a licence — across **three real City of
> Toronto datasets**, fused on the address.
> I click **✓ verify** — there's the source record. The local Nemotron model only
> **phrases** the numbers; it can't invent them. It once claimed '9 permits' when
> the data showed 8 — our verifier caught it. **A hallucinated number physically
> cannot reach the screen.**
>
> Now the move: that risk app isn't a separate tool — it's **one lens on a
> kernel**. Watch what the kernel does with time. A stadium empties — 45,000
> people. Our simulation runs the egress wave: **Union Station hits 2.5× safe
> capacity 14 minutes after full-time. A 14-minute staggered release cuts that
> peak 62%.**
>
> And the same lever, scored across **every** lens at once: it eliminates
> **$21,700** of public-safety exposure — the civic-risk data deciding we
> shouldn't crush a crowd through the least-safe districts — and recovers
> **$33,800** of local business a crush would have killed. **One lever. $116,000.
> Transit, public safety, and the local economy — optimized together.**
>
> And it's agent-drivable: *[to the NemoClaw agent]* 'top three riskiest
> addresses.' *[it calls our tool]* — grounded, matching the data exactly. One OS,
> many lenses, on one box. Thank you."

## Why we win (mapped to the rubric)
1. **The flagship track's literal ask — raw data → on-box processing → actionable
   result.** We ingest Toronto open data, run a deterministic **simulation kernel**
   on the Spark, and emit a quantified, cited intervention. Not a lookup —
   *systems engineering.*
2. **The Verifiers bounty is the architecture, not a feature.** Every number is
   computed; the model only phrases it; a verifier rejects any unverified figure →
   deterministic fallback; click-to-verify makes it auditable live — and the
   **same guarantee holds through the NemoClaw agent** (its answer matched our tool
   exactly).
3. **A platform, demonstrated.** Four lenses — EventSurge, Economic, **Safety (the
   civic risk app, made literal)**, **BusinessFlow (sports/economics)** — run on one
   kernel, optimized by one lever. A new urban intelligence is a **plugin (~90
   lines), not a rewrite.** That is the digital-twin / "operating system for the
   city" thesis, proven.

## Anticipated judge Q&A
- **"Is it really on-device?"** Fully. Local Nemotron via Ollama; self-hosted
  PMTiles basemap + vendored MapLibre — no CDN. Unplug it and it keeps working.
  The point for a city handling sensitive permit/inspection data.
- **"How do you know it isn't hallucinating?"** The model never produces numbers —
  it phrases them. Figures (risk, peak, the $116k) are computed deterministically;
  the verifier rejects invented numbers/sources; audit any claim with ✓-verify.
  The "9 vs 8 permits" catch is a real rejection.
- **"The $116k — real or hardcoded?"** Reproducible: `make urbanos-cli` runs the
  optimizer (grid search over the release lever minimizing `J = Σ wₚ·Jₚ`) on the
  box every run. The breakdown — $60k transit + $21.7k public-safety + $33.8k
  business — is emergent from the lenses, not stored. Calibration constants are
  synthetic and flagged in provenance; the *shape* is the claim.
- **"What's 'OS' about it?"** A microkernel (substrate + time loop), a syscall ABI
  (the four operators `source/transport/couple/observe`), a driver model (city
  adapters), portable apps (lenses), and a governor (the optimizer) — same
  architecture as a real OS, applied to a digital twin of the city.

## The numbers (reproducible, current)
| | value | source |
|---|---|---|
| Union peak | 2.5× capacity, 14 min after full-time | `urban_os.cli` |
| Lever | 14-min staggered release → **−62% peak** | optimizer |
| Transit benefit | ~$60k (J $94k → $34k) | default |
| + Public safety | $21.7k → **$0** | `--safety` |
| + Local business | **$33.8k** recovered | `--business` |
| **Total, one lever** | **$115,993** saved | `--safety --business` |

Reproduce:
```bash
make urbanos-cli                                   # transit egress insight
PYTHONPATH=src python -m urban_os.cli --safety --business   # the full OS, four lenses
```
