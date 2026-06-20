# ADR-0035 — Cyber/holographic look becomes the default

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** ADR-0033 (UrbanOS platform
unification + UX redesign), the Identity-v2 work (PR #115) · **Reverses:** the *default* chosen
in #115 (azure→iris as the primary look)

## Context

The design system already carries **two palettes over one token set**
(`src/urbanos/risk/api/static/vendor/tokens.css`): `:root` = the conservative **azure→iris**
"Identity v2" brand (shipped as the default in #115), and `html[data-theme="cyber"]` = a
**cyan→violet holographic** look (glow, scanlines, 3D skyline, floating info board). The cyber
look only appeared transiently — the shell flipped to it for the optimize "light the room"
climax, and the civic Risk view exposed it via a Presentation-Mode toggle.

Product direction: make the cyber/holographic aesthetic **the default look across the whole
UrbanOS**, not a transient state — a deliberate, eyes-open reversal of #115's default.

## Decision

Make **cyber the shipped default**, attribute-driven, with azure→iris retained as a reachable
alternate (fully reversible).

- **Attribute default, not a token re-anchor.** `data-theme="cyber"` is set on the `<html>` tag of
  both `os.html` (the shell) and `map.html` (the Risk view). `:root` stays the azure→iris alt;
  clearing the attribute (`removeAttribute('data-theme')`) returns it. The whole two-theme system
  is unchanged — only which one is default flips.
- **`tokens.css` is the single source of truth.** `--accent-2` and `--os-boot-bg` (read by
  `os-boot.js` for the boot splash) were moved out of an inline `:root` override in `os.html` into
  `tokens.css` — defined in `:root` (azure) and the cyber block (cyan) — so the boot overlay tints
  correctly under the default.
- **Holographic effects ported into the shell.** The glow/scanline/text-shadow effects that aren't
  plain colour tokens were ported from `map.html` into `os.html` (scoped to the shell's selectors)
  so the City/Flow/Economy lenses read holographic, not merely recoloured.
- **The optimize climax is now an intensifier, not a theme switch.** `runOptimize` added
  `documentElement.setAttribute('data-theme','cyber')` as its "light the room" climax — a no-op
  once cyber is the floor. It now toggles a one-shot `html.climax` class that intensifies the map
  filter (the `#flash` one-shot is unchanged). Honours `prefers-reduced-motion`.
- **Presentation Mode no longer owns the theme.** `map.html`'s Presentation toggle previously wrote
  `data-theme = on ? 'cyber' : ''`, so toggling OFF (or a stale `presmode='0'`) would flip the page
  back to azure under the cyber default. It now keeps the cyber floor and owns only the 3D skyline +
  holographic info board.
- **Reachable alt.** The "How it works" dialog has an **Appearance** toggle that switches between
  cyber and azure→iris and persists the choice (`localStorage 'os-theme'`), honoured before first
  paint.

## Honesty / invariants (unchanged)

Visual/integration only — no compute path, route, schema, or fetch URL changes. The golden numbers
(do-nothing **J $323,222** → best **$105,050**), the 100%-offline map (vendored assets + PMTiles,
no CDN), the hallucination guard, and all data contracts hold. Suite stays **584 passed / 1
skipped**.
