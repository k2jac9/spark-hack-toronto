# Audio takes — iteration log

Every generated take is kept (timestamped filenames never overwrite). The `.mp3`s themselves are
gitignored (binaries); **this manifest is committed** so each take is traceable to its script block,
voice, and settings. Spoken **source** = [`../NARRATION.md`](../NARRATION.md); numbers = the value
table in [`../VIDEO_SCRIPT.md`](../VIDEO_SCRIPT.md).

**Chosen narrator: Brian — Deep, Resonant** (`nPczCjzI2devNBz1zQrb`).
Common settings unless noted: model `eleven_multilingual_v2`, stability 0.45, similarity 0.8.

## Narration (VO)
| File | Section | Voice | Notes |
|---|---|---|---|
| `tts_Most__20260531_051013.mp3` | S2 hook | Eric | audition take (not chosen) |
| `tts_Most__20260531_051026.mp3` | S2 hook | **Brian** | audition take → **chosen voice**; serves as final S2 |
| `tts_Most__20260531_051032.mp3` | S2 hook | George | audition take (not chosen) |
| `tts_Safet_20260531_053659.mp3` | S3 — core loop | Brian | 8 permits · 140,800 ppl · 4× capacity |
| `tts_Under_20260531_053709.mp3` | S4 — how we built it (v1) | Brian | RAPIDS beat; **superseded by v2** (kept, not deleted) |
| `tts_Under_20260531_055019.mp3` | S4 — how we built it (**v2, current**) | Brian | adds **TensorRT-LLM** line (ADR-0027); ⚠️ audit cuGraph/cuDF/cuOpt/cuML + "TensorRT-LLM" pronunciation |
| `tts_Back__20260531_053726.mp3` | S5 — climax | Brian | rounded $: ~54k · ~11k · ~458k · −75% |
| `tts_Hi_—__20260531_054303.mp3` | S1 — intro | Brian | **SCRATCH only** (on-camera = your voice); team-name placeholdered |
| `tts_One_c_20260531_054305.mp3` | S5 — close | Brian | **SCRATCH only** (on-camera = your voice) |

## SFX (`text_to_sound_effects`)
| File | Cue | Duration |
|---|---|---|
| `sfx_short_20260531_054251.mp3` | boot-up / power-on whoosh (S1 open) | 1.5s |
| `sfx_a_cle_20260531_054253.mp3` | the unplug — power-cut thunk → silence (S2) | 1.0s |
| `sfx_subtl_20260531_054254.mp3` | lens-switch UI tick / shimmer (S3) | 0.5s |
| `sfx_risin_20260531_054255.mp3` | climax counter climb → resolve chime (S5) | 2.0s |

## Music (`compose_music`)
| File | Use | Length |
|---|---|---|
| `music__20260531_054257.mp3` | intro bed — cinematic tech swell, instrumental | 12s |

## Regenerate / re-audition
Re-run from `../NARRATION.md` via the ElevenLabs MCP `text_to_speech` (voice_id
`nPczCjzI2devNBz1zQrb`). New takes get a fresh timestamp — **add a row here, don't overwrite.**
