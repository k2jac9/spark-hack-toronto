# ADR-0033 — UrbanOS: one integrated, city-agnostic platform

**Status:** Accepted · **Date:** 2026-06-20 · **Relates:** ADR-0001 (urban_os kernel on civic_analyst), ADR-0022 (one shared lens stack), ADR-0026 (public-UI clarity) · **Supersedes the framing of:** the "two apps on two ports" model

## Context

The project began as two apps — `civic_analyst` (address-level civic risk, `:8000`) and `urban_os` (urban-stress simulation, `:8001`) — already sharing one architecture (the kernel + the adapter×lens model; `urban_os.api` mounts civic at `/civic` and treats civic risk as the Safety lens). The product direction is now explicit:

> **UrbanOS** — a **city-agnostic platform** that ingests **any city's open data (Toronto first)** and turns it into **insightful lenses of intelligence**. Tagline: **"Turning urban data into real-time insight through AI."**

So the two apps should present as **one platform**, not two products.

## Decision

1. **One brand: UrbanOS.** Rebrand everywhere (UI titles, wordmark, boot splash, help, README, CLAUDE.md). Tagline as above. Repo renamed `k2jac9/spark-hack-toronto` → **`k2jac9/urbanos`**.
2. **One integrated platform, civic risk as the Risk lens.** The unified UrbanOS app is the single front door; the civic address-risk UI becomes the **Risk lens** within the shell (it already serves under the mounted `/civic`). The standalone `:8000` is retired as a *product surface* (still reachable internally via the mount); UrbanOS serves the unified UI with a lens nav (Risk · Flow · Economy · …) over one map.
3. **City-agnostic by construction.** The adapter×lens architecture already makes the substrate city-agnostic (a city adapter builds the substrate; lenses are portable). Toronto is the first adapter; the platform framing makes "add a city" a first-class concept.
4. **Rename depth — brand + integrate first; defer the source-package rename.** Keep the Python packages (`urban_os`, `civic_analyst`) as-is for now — renaming them is a large refactor (imports, tests, 30+ ADR refs) for a later, dedicated ADR. The *product* is "UrbanOS" regardless of the package names.
5. **Local folder rename** (`…\spark-hack-toronto` → `…\UrbanOS`) is a final, separate step (a live working dir can't be renamed mid-work).

## Honesty / invariants (unchanged)

Offline map (no CDN), the hallucination guard, and the golden numbers (do-nothing **J $323,222** → best 14-min **$105,050**) all hold. The integration is brand + serving + UI/IA, not a change to the data contracts or the kernel. Origin history (NVIDIA Spark Hack) preserved in the older ADRs / pitch / video kit (see ADR framing in CLAUDE.md).

## Rollout (sequence of verified PRs)

1. **Rebrand** strings + tagline across UI/docs (this PR). 2. **Unified shell / lens IA** — the Risk lens first-class in the nav over one map; one `make` front door. 3. **UI/UX rethink** — bolder identity + integrated lenses (builds on the shared tokens + the map-heat legend/grouping, #111). 4. **(later, own ADR)** source-package rename + the local folder rename.
