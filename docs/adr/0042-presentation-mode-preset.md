# ADR-0042 — Presentation Mode is the preset across every lens

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** ADR-0033 (platform unification —
the shell + lens rail), ADR-0035 (cyber default look + the Risk lens embedding the full civic
analyst via `/civic/?embed=1`)

## Context

"Presentation Mode" (cyber theme + a pitched 3D building skyline + a floating holographic info
board) existed only inside the civic Risk app (`/civic/`), behind a floating **◢ Presentation**
button, and shipped **default OFF**. The unified shell (`/`) drives the four-lens rail
(City · Risk · Flow · Economy) over its own map and embeds the civic app as the Risk lens. The
shell map already carried a `buildings-3d` fill-extrusion layer, but it was only revealed for a
one-shot rise during the boot flourish and then flattened — so day-to-day the shell was 2D and
the rich 3D presentation was reachable only inside the Risk lens, one lens out of four.

We want the demo to **open in the cinematic 3D view by default, on every lens**, with a single,
obvious on/off control — not a per-surface toggle the presenter has to hunt for.

## Decision

Make Presentation Mode the **preset (default ON)** across the whole shell, governed by **one
global toggle in the top bar**.

- **Shell (`urbanos.kernel`/static/os.html).** A `#pres-toggle` pill in the top bar drives a
  shared `PRES` state (persisted as `localStorage['os-pres']`; `'off'` opts out, anything else —
  incl. unset — is ON). `setPres(on)` re-tilts the camera (`pitch 52° / bearing −18°`, or
  `jumpTo` under `prefers-reduced-motion`), flips `buildings-3d` ↔ flat `buildings` visibility,
  and toggles an `html.pres` hook. Each lens's `easeTo` reads `presPitch()/presBearing()` so a
  lens switch keeps the chosen tilt; the boot sequence stays pitched when ON (only settles flat
  when OFF). The `buildings-3d` minzoom dropped 13 → 12 so the skyline reads at the overview
  framing. The camera re-tilt runs **before** the visibility flip, because `setLayoutProperty`
  briefly drops `isStyleLoaded()`.
- **Embedded Risk lens (`urbanos.risk`/static/map.html).** The iframe is created with
  `/civic/?embed=1&pres=<0|1>` so it opens matching the shell; live toggles arrive as a
  same-origin `os-pres` `postMessage`. When embedded, the civic app's own floating
  `#presmode-btn` is hidden — the shell's top-bar button is the single control. Standalone
  `/civic/` keeps its own button and saved preference.

## Consequences

- The demo opens in the 3D skyline on any lens; one top-bar click flattens/restores it, and the
  choice persists.
- **Visual/integration only.** No data, objective, optimizer, narrator, or golden number changes;
  the map stays 100% offline (the extrusion reuses the existing PMTiles `buildings` source — no
  new assets). The offline + a11y gates (`test_urban_ui_offline`, `test_civic_ui_offline`) cover
  the new markers, default-ON behaviour, and the shell→embed handoff.
