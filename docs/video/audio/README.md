# audio/ — generated narration & SFX (not committed)

ElevenLabs MCP writes generated `.mp3`/`.wav` here (the binaries are gitignored).
The committed **source** for narration is [`../NARRATION.md`](../NARRATION.md); regenerate
audio from it with the ElevenLabs MCP `text_to_speech` / `text_to_sound_effects` tools.

Server output is configured via the MCP env `ELEVENLABS_MCP_BASE_PATH` → this folder.
**Chosen narrator: Brian — Deep, Resonant** (`nPczCjzI2devNBz1zQrb`); override per call.
Every generated take is logged in [`MANIFEST.md`](MANIFEST.md) (timestamped, never overwritten).
