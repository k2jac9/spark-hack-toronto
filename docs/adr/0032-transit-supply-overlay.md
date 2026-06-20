# ADR-0032 — Transit-supply overlay: real GTFS scheduled departures (Fit C)

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** ADR-0030 (MobilityDemand — bike demand overlay), ADR-0031 (TTC boardings source), the hardened CKAN client (#106) · **Research:** `docs/research/tpf-and-data-driven-lenses.md` §5–§6 "Fit C"

## Context

The demand sources show *where people want to leave* (Bike Share origins, ADR-0030) and *who is already on transit* (TTC boardings, ADR-0031). The missing half is **supply**: how much scheduled transit actually serves each area. The TTC GTFS feed (`ttc-routes-and-schedules`) carries exactly that — every scheduled stop event in `stop_times.txt`.

## Decision

A real, static **transit-supply** map overlay (display-only).

1. **Real data (committed slice).** `scripts/fetch_gtfs_supply.py` streams the GTFS `stop_times.txt` (≈4.2M rows) via the hardened `CKANClient`, counts scheduled departures in the evening window (17:00–19:00) per stop, joins `stops.txt` coordinates, filters the downtown bbox, and writes `demo_data/transit_supply__downtown.csv` (945 downtown stops, real evening departure counts). Pure real data — a count of scheduled departures, no modelling.
2. **Per-node fusion.** `adapters.transit_supply_by_node` lifts the per-stop counts onto the substrate by proximity-weighted average → a static per-node supply intensity (`{node_id: departures}`), mirroring the civic overlays. Provenance `real/measured`.
3. **Surfacing.** `services.transit_supply_overlay` returns the per-node array; `/overlays` adds a `transit_supply` field normalised 0..1; `os.html` adds a "Transit supply" button to the existing Map-heat toggle group (advisory tooltip), driving the same heat layer. No new map layer.

## Honesty notes (none regressed)

- **Display-only, no headline movement.** This is a static overlay surfaced by `/overlays` (which runs its own baseline sim for the other fields); `transit_supply` is computed directly from the adapter and prices nothing — no lever, no `J` term. Golden numbers untouched (do-nothing **J $323,222** → best **14 min → $105,050**).
- **Real, not modelled.** Unlike the TTC *boardings source* (real magnitude / modelled intraday shape, ADR-0031), this is a straight count of real scheduled departures — provenance `real/measured`. The known GTFS caveat (no clean subway-*station* coords) doesn't apply here: we use each stop's own `stops.txt` coordinate.
- **Opt-in data + CPU fallback.** Loads only under `DATA_DIR=demo_data`; no slice / no network → deterministic synthetic fallback, so CI/dev stay offline and the layer always renders. Offline-safe fetch (notes + exit 0). Raw GTFS ZIP never committed.

## What's next (when justified)

A supply-vs-demand ratio overlay (transit_supply ÷ bike_demand / boardings) would highlight under-served demand pockets — a clean follow-up reading from the fields already surfaced. Per-mode supply (subway vs surface) needs a `stop_times→trips→routes` route_type join (heavier); deferred until needed.
