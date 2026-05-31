# ADR-0018 — FIFA-window convergence-crunch substrate (multi-venue EventSurge)

## Status
Accepted. Reshapes the downtown scenario the Urban-OS lenses run on; builds on
the multi-lever cost model of [ADR-0015](0015-shelter-as-real-lever-and-cost-transparency.md)
and [ADR-0016](0016-shelter-interior-optimum-coverage-premium.md).

## Context
The old demo scenario was a single abstract stadium let-out (45k) draining into a
ring of abstract sinks clustered at Union. It made the point ("one lever saves the
city money") but the *crowd* was generic and the geography was invented — easy for
a judge to wave off as a toy. The Spark Hack runs inside the **FIFA World Cup 2026
Fan-Festival window**, and that window hands us a far stronger, *real* scenario: on
a peak FIFA day, multiple major downtown venues let out into the **same Union /
Exhibition-GO transit corridor at once**. That concurrency — not any single venue —
is the planning problem a city operations chief actually faces.

Real anchors (researched, cited in the substrate header):
- **BMO Field** ("Toronto Stadium") is Toronto's FIFA 2026 venue — opener Canada v
  Bosnia (Jun 12), Germany v Côte d'Ivoire (Jun 20), Round-of-32 (Jul 2); FIFA
  capacity **45,736**. Its *only* adjacent rail is **Exhibition GO**, one stop from
  Union on Lakeshore West — so ~46k funnel through a single secondary station.
  (kickoffadventures.com, fwcumc.com)
- **Rogers Centre** (Blue Jays v Yankees, Jun 12 7:07pm) is ~500 m from BMO Field;
  **Scotiabank Arena** (concert, e.g. Jun 20) is *attached to Union Station*. Both
  empty straight onto Union. (mlb.com, scotiabankarena.com)
- The **FIFA Fan Festival** (Fort York / The Bentway, Jun 12 – Jul 2) is now
  **ticketed at $10** — originally promised free — to offset a **$6.2M city
  deficit**, with **2M+ visitors** expected over the run. Pop-up fan pitches add
  sustained load: **Floating Futsal at Harbourfront** and a **Nathan Phillips
  Square** pitch. (blogto.com, toronto.ca)

## Decision
Reshape `adapters/toronto.py` into a **concurrent-event convergence crunch** and
give `EventSurge` multi-venue injection.

- **Multi-venue EventSurge.** `EventSurge` now accepts a list of
  `(venue, crowd, event_end)`. Each event seeds its own Gaussian egress pulse at
  its venue node; the pulses **superimpose** on the shared substrate. One single
  `release_minutes` lever still governs every pulse — modelling **one coordinated,
  city-wide release policy**, not per-venue micromanagement.
- **The four concurrent let-outs** (staggered ends 28–42 min so the egress *tails*
  pile up, as real schedules do): BMO Field FIFA (46,000 @ 28 min) · Fort York fan
  festival (30,000 @ 35 min) · Scotiabank Arena concert (19,800 @ 38 min) · Rogers
  Centre ballgame (45,000 @ 42 min) — **140,800 people** across **17 nodes / 25
  edges**.
- **Union is the convergence bottleneck.** Rogers Centre, Scotiabank Arena, the
  Exhibition-GO overflow and the waterfront fan zones all route into Union, whose
  outbound rail/subway throughput (~2,450/min) is the binding constraint, so a
  queue piles up there. **Exhibition GO is the FIFA-specific secondary crush** — the
  single station serving BMO Field's ~46k, one stop from Union on Lakeshore West.
- **Real exit lines replace the old abstract sinks.** The drains are now named real
  egress corridors — Lakeshore West → Mimico, Lakeshore East → Danforth, Line 1 →
  Bloor — and the subway relief valves (St Andrew/King, St Patrick/Queen, Osgoode)
  have ample downstream capacity, so they drain freely and never spuriously become
  the bottleneck. The drawn graph equals the simulated routing (the
  ADR-0015 §6 map==engine invariant holds).

## Honest-calibration caveat
Crowd sizes are anchored to real announced capacities; **node/edge capacities and
the degree of crowd-overlap are plausibility-calibrated and flagged in provenance,
not measured**. The claim is the **shape**, not the decimals: under realistic
worst-case simultaneity, Union saturates and one coordinated release/shelter lever
is what relieves it. The worst-case-simultaneity *is* the planning scenario — the
day a city ops chief must prepare for — so calibrating toward it is the honest
choice, not an inflation. On the GX10 the graph is swapped for a real TTC GTFS +
traffic-volume build via the existing `CKANClient`; the lenses and kernel are
unchanged (that swap is the whole point of an adapter).

## Consequences
- **Bigger crowd → bigger, more legible savings.** The concurrent crunch makes
  Union the unambiguous failure point and gives the optimizer real headroom. The
  reproducible headline numbers (see PITCH §"The numbers") are now:
  - **`make urbanos-cli`** (transit core, 2-lens): Union peaks **3.7×** @ t=47 min;
    best **14-min release** → **−67% peak**, net benefit **~$218k**.
  - **`urban_os.cli --safety --business`** (full cross-domain): same lever →
    **~$281k** combined; public safety **$53.7k → $1.6k**, local business **$10.4k**
    recovered.
  - **`/optimize`** (live UI, 3-lens *with* weather/shelter): baseline Union
    **4.0× → 1.0×** (−75%), best **16-min release + 80% shelter coverage**, net
    benefit **~$394k**, combined cross-domain benefit **~$458k**; safety
    **$53.7k → $0**, business **$10.7k** recovered.
- **Ties to the $6.2M deficit.** The framing the demo leans on: one coordinated
  lever, optimized across *every* concurrent event, saves the city money — and that
  operations saving directly helps offset the Fan Festival's $6.2M deficit (the very
  deficit that forced the $10 ticket).
- The numbers differ by surface **because the lens stack differs** (2-lens vs
  cross-domain vs 3-lens-with-weather), not because anything is hardcoded — each
  bullet above names the command that reproduces it, so a judge can verify and the
  pitch never drifts from the live demo.
- `total_crowd` is now the sum across events; single-venue callers/tests keep
  working via the `Scenario`'s primary-event mirror (`crowd_size` override touches
  only BMO Field). EventSurge/Economic outputs are unchanged when the safety/business
  lenses are off (the additive-lens test still holds).
