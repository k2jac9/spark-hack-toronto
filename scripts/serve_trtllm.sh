#!/usr/bin/env bash
# Serve the Nemotron narrator behind NVIDIA TensorRT-LLM (ADR-0027) — BOX ONLY (GB10,
# aarch64/Grace, CUDA). The narrator client is runtime-agnostic (OpenAI-compatible HTTP),
# so this is the *activation* step: stand up `trtllm-serve`, then point the app at it.
#
# Box-proven (2026-05-31): Nemotron-3-Nano (NVFP4) serves this way. NB: this is a
# CAPABILITY, not a speedup — measured single-stream decode is NOT faster than Ollama
# (54.5 vs 61.2 tok/s; ADR-0027). `make llm-check` reports which runtime answered. The app
# falls back to Ollama / the deterministic narrator with ZERO code change, so the demo is
# never blocked. (On the GB10 prefer the NGC container — ADR-0027 §Box verification — bare-
# metal aarch64 hits a torch-ABI wall.) Run on the box:
#
#     bash scripts/serve_trtllm.sh
#     # in the app's env:  export LLM_RUNTIME=tensorrt-llm LLM_BASE_URL=http://localhost:8009/v1
#     make llm-check       # expect runtime='tensorrt-llm' + a tok/s number
#
set -euo pipefail

# HF model id or local path of the interactive narrator model. trtllm-serve builds the
# TRT engine on first run (cached afterwards). Override for a pre-built engine dir.
MODEL="${TRTLLM_MODEL:-nvidia/Nemotron-3-Nano}"
PORT="${TRTLLM_PORT:-8009}"
HOST="${TRTLLM_HOST:-0.0.0.0}"
MAX_BATCH="${TRTLLM_MAX_BATCH:-8}"

echo "=== TensorRT-LLM serve (ADR-0027) ==="
echo "model=${MODEL}  host=${HOST}  port=${PORT}"

if ! command -v trtllm-serve >/dev/null 2>&1; then
  cat <<'EOF'
[!] trtllm-serve not found. Install TensorRT-LLM on the box first, e.g.:
      pip install --extra-index-url https://pypi.nvidia.com tensorrt-llm
    or use the NGC TensorRT-LLM aarch64 container. Verify your Nemotron variant is a
    supported architecture before the demo — if not, KEEP Ollama (the app needs no
    change; this seam is opt-in). See docs/ON_THE_BOX.md §2b.
EOF
  exit 1
fi

echo "[i] Building/loading the TRT engine and serving (first run compiles; then cached)."
echo "[i] When it reports 'Application startup complete', in the app's env run:"
echo "      export LLM_RUNTIME=tensorrt-llm LLM_BASE_URL=http://localhost:${PORT}/v1"
echo "      make llm-check"

# trtllm-serve exposes an OpenAI-compatible server at /v1 (chat/completions, models).
exec trtllm-serve "${MODEL}" --host "${HOST}" --port "${PORT}" --max_batch_size "${MAX_BATCH}"
