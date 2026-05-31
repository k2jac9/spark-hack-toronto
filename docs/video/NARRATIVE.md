# Demo Video — Narrative & Story Bible

The positioning, arc, and reusable language behind the 5-minute submission video.
**Why** the script ([`VIDEO_SCRIPT.md`](VIDEO_SCRIPT.md)) is shaped the way it is. The
spoken-line source of truth stays [`docs/PITCH.md`](../PITCH.md) +
[`docs/DEMO_SCRIPT.md`](../DEMO_SCRIPT.md); this file is the *strategy* layer on top.

---

## 1. The one sentence (memorize this)
> **An operating system for the city: on a peak FIFA World Cup 2026 day, we fuse the data,
> simulate four venues letting out at once, and optimize one coordinated lever across transit,
> public safety, and local business — grounded, and 100% on one box.**

If a judge remembers nothing else, they should remember **"one lever, every lens, on one box —
and no number is hallucinated."**

---

## 2. The arc (problem → solution → proof → so-what)
A three-act spine wrapped in the official 5-section format:

1. **Problem.** Cities run on **single-purpose dashboards** — one tool for inspections, another
   for transit, another for events. They don't talk, so no one can optimize *across* them. And
   the data is sensitive, so a cloud LLM that might invent a number is a non-starter.
2. **Solution.** We built a **microkernel for urban dynamics**: a domain-agnostic kernel
   (substrate + time loop + four operators) + a city driver model + portable **lenses** +
   a **governor** that optimizes interventions. New urban intelligence is a **plugin (~90 lines),
   not a rewrite.**
3. **Proof.** Four lenses on one kernel — **City · Safety · Flow · Economy** — re-skin *one*
   Toronto map. We stress it with a **real FIFA-window convergence crunch** (four concurrent
   let-outs, 140,800 people) and let the optimizer find **one coordinated lever** that moves
   **every** lens at once. Every figure is computed, cited, and **✓-verifiable live.** It all
   runs on an **NVIDIA GX10 with the cord pulled out.**
4. **So what.** One ops chief, one lever, optimized across transit + public safety + local
   business — the operations side of closing a multi-million-dollar event deficit. And it's
   **agent-drivable** (NemoClaw over MCP, grounded). One OS, many lenses, on one box.

---

## 3. Patterns we're stealing (from research + the reference video)

### From the official guidelines + 2025–26 winning-video research
- **Hook in the first 5–10 seconds.** Don't warm up. The interface (real pixels, not slides)
  should be on screen by ~0:20.
- **Storytelling over a feature list.** Walk one coherent scenario end-to-end.
- **Minimize cuts** — show the thing actually running; live > edited.
- **Polished UI moves the "innovation" score** — lead with the most visually exciting state
  (the unified shell + the climax animation).
- **Address the judging criteria explicitly:** on-device / DGX Spark, best use of **Nemotron**,
  **ARM64** optimization, and verifiability. Say these words.
- **Prove it's alive:** today's date on screen + the **live unplug**.

### From the "Policy Angel" reference video (teardown)
| What they did | What we do with it |
|---|---|
| Opened on the **money shot** (detect → audio warning → supervisor alert "in seconds") | Open on the **unplug + the climax tease**: one map, four lenses, "watch them all move on one lever." |
| Immediately said **"that speed is why DGX matters"** | Right after our money shot: **"and it's still unplugged — that's why on-box matters for a city's sensitive data."** |
| **"Under the hood"** beat naming the exact model + latency ("Nemotron Nano… on DGX Spark… in milliseconds") | Our **how-we-built-it** beat: **Nemotron-3-Nano via Ollama**, deterministic kernel + hallucination guard, ARM64 GX10, sub-2s warm narration. |
| On-prem framed as a **value** ("important to not rely on a cloud provider") | Same, but for **civic data** — permits, inspections, licences shouldn't leave the box. |
| **"You can imagine this applied to…"** extensibility | Our **platform thesis**: a new lens is **~90 lines**, not a rewrite — medical, logistics, utilities all plug into the same kernel. |
| Warm, human close + forward vision | Close on the human stakes (crowd safety, local business) + "this is the operations layer for any city." |

---

## 4. Voice & tone
- **Confident, concrete, fast.** Short sentences. Real numbers (once locked) said off the
  *screen*, not the page.
- **Engineering pride, not hype.** We say "deterministic," "computed," "verifier," "grounded."
- **Honest by design.** The number differs by lens stack *on purpose* — that's the platform
  point, not a bug. One surface per breath.

---

## 5. Reusable lines (the kit)
Pull from these when recording — all already battle-tested in `PITCH.md`/`DEMO_SCRIPT.md`:

- **Open:** "Everything you'll see runs **100% on this one box** — no cloud, no internet. Watch — I'll unplug it."
- **Trust beat:** "The local Nemotron model only **phrases** the numbers; it can't invent them.
  It once said '9 permits' when the data showed 8 — the verifier caught it. **A hallucinated
  number physically cannot reach this screen.**"
- **Grounding:** "Three real City of Toronto datasets, **fused on the address** — and I can
  **✓-verify** any claim against the source record, live."
- **Crunch:** "Peak FIFA 2026 day — four venues let out into the same corridor at once,
  **140,800 people** — and **Union Station hits ⟨peak⟩ safe capacity.**"
- **Climax:** "One coordinated lever… I drag it **once**… and **every lens moves together.**
  **One lever. ⟨combined-$⟩ of combined benefit** across transit, safety, and the local economy."
- **Platform:** "That risk app isn't a separate tool — it's **one lens on a kernel.** A new
  lens is **~90 lines, not a rewrite.**"
- **Close:** "One city. One substrate. Every lens. **100% on this box — still unplugged.** And
  it's even **agent-drivable.**"

---

## 6. Judging-criteria → moment map
| Criterion | The moment in the video that earns it |
|---|---|
| **On-device / DGX Spark** | The unplug; "still running"; the architecture beat. |
| **Best use of Nemotron** | The narrator phrasing + the verifier "9 vs 8" catch; served behind **TensorRT-LLM** (NVFP4/Blackwell FP4) — a runtime-portable narrator with an Ollama fallback (capability, not a decode speedup). |
| **ARM64 / optimization** | How-we-built-it: aarch64 wheels, MoE small-active model choice, deterministic kernel (numpy/Rust core), sub-2s warm, **Nemotron served via TensorRT-LLM** (runtime portability — not a speedup claim). |
| **The Stack (NVIDIA libraries)** | How-we-built-it GPU beat: six NVIDIA libs *invoked* — NeMo (Nemotron) + RAPIDS **cugraph / cuDF / cuOpt / cuML** + **TensorRT-LLM** (narrator runtime), opt-in with CPU/Ollama fallback, `make gpu-check` / `make llm-check` proof; **PhysicsNeMo** surrogate wired as a seam (next-step, no checkpoint). **Honest:** RAPIDS numerics show no demo-scale speedup (city-scale win); TensorRT-LLM is a **capability** (Nemotron served on the box), **not** a decode speedup — single-stream is *not* faster than Ollama (54.5 vs 61.2 tok/s); throughput-under-load is unproven (next-step). |
| **Flagship: raw data → on-box → action** | Datasets fused → kernel sim → optimized lever with a $ result. |
| **Verifiers bounty** | ✓-verify live; "a hallucinated number cannot reach the screen"; same guarantee through NemoClaw. |
| **Platform / digital twin** | Four lenses on one kernel; "a new lens is ~90 lines." |

---

## 7. What NOT to do
- Don't blend two number surfaces in one breath (cite the surface you're showing).
- Don't read a figure off this repo if the live screen disagrees — **say the screen.**
- Don't bury the product behind a long intro — pixels by ~0:20.
- Don't overscope the narration; one flawless scenario beats five half-shown features.
- **Be precise about *which* claim.** The RAPIDS **numerics** seams (cugraph/cuDF/cuOpt/cuML) have
  **no win at demo scale** — say "wired, opt-in, city-scale," show `make gpu-check`, never imply a
  benchmark we can't reproduce. **TensorRT-LLM** is a **capability, not a speedup**: the box engine IS
  built and Nemotron-3-Nano serves via TRT-LLM (NVFP4/Blackwell FP4, OpenAI-compatible, Ollama
  fallback — a runtime-portable narrator, ADR-0027), but measured **single-stream decode is NOT faster
  than Ollama (54.5 vs 61.2 tok/s)** — claim the **capability** (Nemotron served via TRT-LLM on the
  box), shown by `make llm-check`, **never a decode speedup**. TRT-LLM's throughput-under-load
  advantage is **unproven (next-step)**. PhysicsNeMo/Modulus is a **seam + next-step only** (no trained
  checkpoint ships) — never imply a working surrogate.
