# Narration — VO-only cut (ready for ElevenLabs TTS)

The spoken lines from [`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md), stripped of screen directions, so
each block can be fed straight to ElevenLabs `text_to_speech` → one `.mp3` per section.
Generated audio writes to [`audio/`](audio/) (gitignored). **This file is the committed source.**

> ✅ **Tokens RESOLVED (2026-05-31)** from the live `:8001 /optimize` — see the value table in
> `VIDEO_SCRIPT.md`. Spoken figures below are **rounded for the ear** (e.g. "about fifty-four
> thousand dollars"); the **on-screen** figure is exact (`$53,745`) — say the screen, the VO rounds.
> Dates/jargon are spelled for clean TTS in the generated audio ("twenty twenty-six", "ARM sixty-four").
> The **camera-on intro (S1) and close (S5 last line) are your own voice on camera** — Brian TTS
> scratch tracks exist in `audio/` as a timing/fallback reference only. Generated takes logged in
> [`audio/MANIFEST.md`](audio/MANIFEST.md).

## Recommended voice + model
- **Model:** `eleven_multilingual_v2` (reliable, natural) — or `eleven_v3` for more expressive
  delivery (newer; audition first).
- **Narrator candidates** (confident, credible, "explainer" timbre):
  | Voice | ID | Feel |
  |---|---|---|
  | **Eric — Smooth, Trustworthy** *(current default)* | `cjVigY5qzO86Huf0OWal` | American, calm authority |
  | Brian — Deep, Resonant | `nPczCjzI2devNBz1zQrb` | American, deep trailer voice |
  | George — Warm, Captivating | `JBFqnCBsd6RMkjVDRZzb` | British, narrative |
  | Matilda — Knowledgeable | `XrExE9yKIg1WjnnlVkGX` | American female, informative |
  | Daniel — Steady British | `onwK4e9ZLuTAKqWW03F9` | British, news-explainer |
- **Settings to try:** stability ~0.4–0.5 (some expressiveness), similarity ~0.8, speed ~1.0.

---

## S1 — Intro *(your voice on camera; TTS = scratch only)*
> Hi — we're ⟨team name⟩: ⟨name⟩ and ⟨name⟩. For Spark Hack Toronto we built Urban-OS — an operating system for the city, running entirely on the NVIDIA GX10.

## S2 — Hook / elevator pitch
> Most civic tools are single-purpose dashboards — inspections here, transit there, events somewhere else. They never talk, so nobody can optimize across them.
>
> So we built a microkernel for urban dynamics: one kernel, one Toronto map, and four lenses — City, Safety, Flow, and Economy — that re-skin the same city. A governor then optimizes one coordinated lever across all of them.
>
> Everything runs one hundred percent on this one box — no cloud, no internet. Watch — I'll unplug it. Still running. For a city's sensitive permit and inspection data, that's the point.

## S3 — Live demo: the core loop
> Safety lens first. Every pin is scored on two independent indices — Safety and Activity — so a busy construction zone isn't mistaken for a dangerous one.
>
> I click 500 Bloor Street West: medium Activity — eight open permits, active construction — and a flagged food-safety item. Every claim is grounded — open permits, a DineSafe conditional pass, a licence: three real City of Toronto datasets, fused on the address.
>
> I hit verify — there's the source record. The local Nemotron model only phrases these numbers; it can't invent them. It once said nine permits when the data showed eight — the verifier caught it. A hallucinated number physically cannot reach this screen.
>
> Now the Flow lens — same city, in motion. Peak FIFA World Cup 2026 day: four venues let out into the same corridor at once — a hundred and forty thousand people — and Union Station hits four times safe capacity.

## S4 — How we built it
> Under the hood it's a real microkernel: a substrate — Toronto's road and transit graph from open data — plus a time loop and four operators: source, transport, couple, and observe. Each lens is a plugin on that kernel.
>
> The figures are computed deterministically in a numpy field engine — with an optional Rust core — over a networkx graph. The model never produces a number; a verifier rejects anything not in the evidence and falls back to deterministic phrasing.
>
> And the heavy numerics ride NVIDIA RAPIDS: the graph on cugraph, ingest on cuDF, the evacuation-flow solve on cuOpt, risk hotspots on cuML — each an opt-in seam with a CPU fallback, so the demo never needs the GPU. On this small demo graph there's no speedup; the payoff is at city scale.
>
> It's all local on the GX10: Nemotron-3-Nano for interactive narration — warm in under two seconds, served behind NVIDIA TensorRT-LLM — a runtime-portable narrator, with an Ollama fallback — and a larger mixture-of-experts Nemotron for batch digests. We deliberately chose small-active MoE models for the box's memory bandwidth, and built it ARM64, end to end.
>
> The hardest part was honesty at speed: keeping every dollar figure traceable while the model talks. So a number is either computed and cited — or it doesn't render. The same guarantee holds even when an agent drives it: NemoClaw calls our tools over MCP and answers grounded.
>
> And because a lens is just a plugin — about ninety lines, not a rewrite — the platform extends to any domain: logistics, utilities, public health.

## S5 — Climax + so-what
> Back to the crunch — and the whole point. One coordinated lever: a sixteen-minute staggered release with eighty percent shelter coverage — one city-wide policy across every venue. I drag it once… and every lens moves together.
>
> Union drops from four times safe capacity back down to one — minus seventy-five percent. Public-safety exposure: about fifty-four thousand dollars, gone — the risk data refusing to crush a crowd through the least-safe districts. Local business a crush would've killed: nearly eleven thousand dollars, recovered. One lever. About four hundred and fifty-eight thousand dollars of combined benefit.
>
> Transit, public safety, and the local economy — optimized together. The Fan Festival runs a six point two million dollar deficit; this is the operations side of closing it.

## S5 — Close *(your voice on camera; TTS = scratch only)*
> One city. One substrate. Every lens. One hundred percent on this box — still unplugged. That's Urban-OS. Thanks for watching.

---

## Sound-effects shot list (for `text_to_sound_effects`, optional)
| Cue | Prompt to generate |
|---|---|
| Boot-up (S1 open) | "short futuristic UI power-on whoosh with a soft synth swell, 1.5s" |
| The unplug (S2) | "a clean electrical power-cut thunk, then silence, very short" |
| Lens switch (S3) | "subtle glassy UI tick / soft data shimmer, 0.4s" |
| Climax counter (S5) | "rising digital tally / counter climbing then a confident resolve chime, 2s" |

## When the session is back — generation order
1. `check_subscription` (confirm budget; we're Starter, 90k chars, ~0 used).
2. Audition: generate **S2** with 2–3 candidate voices → pick one.
3. Generate **S2, S3, S4, S5(climax)** with the chosen voice/model → `audio/`.
4. (Optional) SFX from the table above; (optional) `compose_music` for an intro bed.
5. Leave S1 + S5-close for your on-camera voice (only TTS them as a scratch fallback).
