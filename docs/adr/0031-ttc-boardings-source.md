# ADR-0031 — TTC boardings: a real-magnitude / modelled-shape TransitLoad source (Fit C)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** ADR-0029 (TransitLoad lens — the source this feeds), ADR-0030 (MobilityDemand — sibling real-data lens), the hardened CKAN client (#106) · **Research:** `docs/research/tpf-and-data-driven-lenses.md` §5–§6 "Fit C"

## Context

`TransitLoadLens` (ADR-0029) injects real background ridership as a kernel `source`. It shipped reading **TMC** 15-min throughput (`observed_counts_by_node`) — real *intraday shape*, but intersection counts are a *proxy* for transit boardings. The on-point quantity is **TTC subway boardings**. We initially dismissed TTC as "no open data," but a proper catalog search (via the new `scripts/catalog.py`) found `ttc-ridership-subway-scarborough-rt-station-usage`: real typical-weekday boardings **per station**.

The catch, stated plainly: that dataset is a **daily total per station — no 15-min/intraday breakdown** (TTC publishes no public APC at that grain), and it carries **no coordinates** (the TTC GTFS feed exposes no clean subway-*station* coordinates either — only mixed platform/surface stops needing a route_type join). So a fully-measured 15-min boardings series is not possible from open data. What *is* possible, honestly, is **real magnitude + modelled intraday shape**.

## Decision

A new opt-in TransitLoad **source**: real per-station boardings, distributed over the sim window by a documented shape.

1. **Real data (committed slice).** `scripts/fetch_ttc_boardings.py` pulls the latest station-usage XLSX via the hardened `CKANClient` (`find_resource` + `download_resource`), sums the real "Total" per station, and writes `demo_data/ttc_boardings__downtown.csv` — the downtown-core subway stations with **real daily boardings** (UNION 128,655; KING 60,495; ST ANDREW 57,477; QUEEN 48,701; ST PATRICK 34,056; OSGOODE 23,669) at their **real coordinates**. The slice is **pure real data** — a daily total per station, no modelled shape baked in. (Coordinates are the verified real station locations the substrate uses, since GTFS has no clean subway-station coords — documented in the fetch script.)
2. **Modelled intraday shape (in the adapter, not the data).** `adapters.ttc_boardings_by_node` distributes each station's real boardings to non-sink nodes by normalized proximity (conserving magnitude), then spreads it across the sim window with a documented normalized evening-peak Gaussian (`_ttc_intraday_shape`) scaled by `_TTC_PM_SHARE` (≈0.20 — a standard transit-planning share of weekday boardings in the ~2h PM peak; documented, not fit to any headline number). Output: `{node: {minute: count}}`, **provenance `real-magnitude/modelled-shape`** — deliberately distinct from TMC's `real/measured`.
3. **Opt-in source choice.** `default_lens_stack(..., transit_load=True, transit_source="tmc"|"ttc")` (CLI `--transit-source`, env `URBANOS_TRANSIT_SOURCE`). Default `"tmc"` → byte-identical to before. `"ttc"` feeds TransitLoad the real-boardings source.

## Honesty notes (none regressed)

- **Default surfaces byte-identical.** TransitLoad is off by default; even on, the default source stays TMC. The golden CLI numbers are unchanged (do-nothing **J $323,222**, best **14 min → $105,050**) — verified.
- **Real vs modelled boundary is explicit.** Committed data = real boardings only. The modelled piece (intraday distribution + PM share) lives in code, is named, and is labelled in the provenance string and the dataset registry note. We do **not** claim 15-min measured boardings — none are public.
- **No new lever / no J term.** This only changes *which real series* TransitLoad sources; TransitLoad itself stays a no-cost, no-lever realism source (ADR-0029). The exact kernel still prices every person.
- **Opt-in + CPU fallback.** No slice / no openpyxl / no network → synthetic fallback; CI/dev never need the XLSX. The fetch script is offline-safe (notes + exit 0).
- **No private deps.** openpyxl is a *fetch-only* tool (the committed slice is CSV); runtime/CI never import it.

## What's next (when justified)

If TTC ever publishes APC 15-min boardings, the adapter swaps the modelled shape for the measured one with no lens/kernel change. The `ttc-routes-and-schedules` GTFS could add a service-frequency overlay (supply vs demand). Promoting boardings to a *priced decision* objective would move headline numbers and needs its own ADR.
