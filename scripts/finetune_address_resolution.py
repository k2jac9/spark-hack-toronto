"""STRETCH GOAL — QLoRA fine-tune of Nemotron Nano for Toronto address/entity resolution.

The hard, defensible problem in this project is matching messy municipal address
strings ("100 Queen St W" == "100 QUEEN STREET WEST" == "100 Queen St. West, Toronto").
A small QLoRA adapter teaches the model that mapping. This is a STRETCH GOAL: only
attempt it if the core demo is solid — training can eat the weekend.

Runs on the ASUS Ascent GX10 (GB10 GPU). Heavy deps (unsloth/trl/peft/torch) are
imported inside the training function so this file stays importable on a laptop
without a GPU. Use ``--check`` to validate the plumbing offline first.

    pip install unsloth trl peft datasets        # on the GX10 (ARM64 + CUDA)
    python scripts/finetune_address_resolution.py --check          # offline dry-run
    python scripts/finetune_address_resolution.py --data fixtures/address_resolution.sample.jsonl

Serve the resulting adapter with vLLM:
    vllm serve nvidia/nemotron-3-nano --enable-lora \
        --lora-modules toronto-addr=./out/toronto-addr-lora
Then set LLM_MODEL=toronto-addr so /analyze uses the fine-tuned adapter.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SYSTEM = "Normalize the Toronto address to canonical form: '<NUM> <NAME> <TYPE> <DIR>', uppercase."

DEFAULT_DATA = "fixtures/address_resolution.sample.jsonl"
DEFAULT_BASE_MODEL = "nvidia/nemotron-3-nano"
DEFAULT_OUT = "./out/toronto-addr-lora"
DEFAULT_EPOCHS = 3
DEFAULT_LORA_R = 16
DEFAULT_LORA_ALPHA = 16
DEFAULT_MAX_SEQ_LEN = 512
DEFAULT_BATCH_SIZE = 2

# Tiny synthetic sample so ``--check`` can prove the data builder works even when
# no JSONL fixture is present. Mirrors fixtures/address_resolution.sample.jsonl shape.
_SYNTHETIC_ROWS: list[dict[str, str]] = [
    {"raw": "100 Queen Street West", "canonical": "100 QUEEN ST W"},
    {"raw": "100 Queen St. W., Toronto, ON", "canonical": "100 QUEEN ST W"},
    {"raw": "55 John Street", "canonical": "55 JOHN ST"},
]


class DataError(ValueError):
    """Raised when training data is missing or malformed (boundary validation)."""


def load_rows(data_path: Path) -> list[dict[str, str]]:
    """Read a JSONL file of {"raw", "canonical"} rows, validating each at the boundary."""
    if not data_path.exists():
        raise DataError(
            f"training data not found: {data_path}\n"
            f"  expected a JSONL file with one {{'raw': ..., 'canonical': ...}} object per line.\n"
            f"  try: --data {DEFAULT_DATA}  (or run with --check to use the synthetic sample)."
        )
    if not data_path.is_file():
        raise DataError(f"training data path is not a file: {data_path}")

    rows: list[dict[str, str]] = []
    text = data_path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DataError(f"{data_path}:{lineno}: invalid JSON: {exc.msg}") from exc
        rows.append(_validate_row(obj, data_path, lineno))

    if not rows:
        raise DataError(f"no usable rows found in {data_path} (file is empty or all blank lines).")
    return rows


def _validate_row(obj: Any, source: Any, lineno: int) -> dict[str, str]:
    """Ensure a single row is a well-formed {raw, canonical} pair."""
    if not isinstance(obj, dict):
        raise DataError(f"{source}:{lineno}: expected a JSON object, got {type(obj).__name__}.")
    for key in ("raw", "canonical"):
        if key not in obj:
            raise DataError(f"{source}:{lineno}: missing required field '{key}'.")
        if not isinstance(obj[key], str) or not obj[key].strip():
            raise DataError(f"{source}:{lineno}: field '{key}' must be a non-empty string.")
    return {"raw": obj["raw"], "canonical": obj["canonical"]}


def build_examples(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Turn {raw, canonical} rows into chat-format SFT examples."""
    return [
        {
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": r["raw"]},
                {"role": "assistant", "content": r["canonical"]},
            ]
        }
        for r in rows
    ]


def validate_args(args: argparse.Namespace) -> None:
    """Boundary checks on hyperparameters so bad args fail clearly, not mid-train."""
    problems: list[str] = []
    if args.epochs < 1:
        problems.append(f"--epochs must be >= 1 (got {args.epochs})")
    if args.lora_r < 1:
        problems.append(f"--lora-r must be >= 1 (got {args.lora_r})")
    if args.lora_alpha < 1:
        problems.append(f"--lora-alpha must be >= 1 (got {args.lora_alpha})")
    if args.max_seq_length < 16:
        problems.append(f"--max-seq-length must be >= 16 (got {args.max_seq_length})")
    if args.batch_size < 1:
        problems.append(f"--batch-size must be >= 1 (got {args.batch_size})")
    if not str(args.base_model).strip():
        problems.append("--base-model must not be empty")
    if not str(args.out).strip():
        problems.append("--out must not be empty")
    if problems:
        raise DataError("invalid arguments:\n  - " + "\n  - ".join(problems))


def run_check(args: argparse.Namespace) -> int:
    """Offline dry-run: validate config + data plumbing, print plan, exit without a GPU.

    Never imports torch/peft/trl/unsloth and never touches the network.
    """
    print("== finetune_address_resolution --check (offline dry-run) ==")
    validate_args(args)

    data_path = Path(args.data)
    if data_path.exists():
        rows = load_rows(data_path)
        source = str(data_path)
    else:
        rows = [dict(r) for r in _SYNTHETIC_ROWS]
        source = f"<synthetic sample> (no file at {data_path})"

    examples = build_examples(rows)

    # Verify each built example has the expected chat shape.
    for i, ex in enumerate(examples):
        msgs = ex.get("messages")
        if not isinstance(msgs, list) or len(msgs) != 3:
            raise DataError(f"built example {i} is malformed: expected 3 messages, got {msgs!r}")
        roles = [m["role"] for m in msgs]
        if roles != ["system", "user", "assistant"]:
            raise DataError(f"built example {i} has wrong roles: {roles}")

    print(f"data source       : {source}")
    print(f"rows loaded       : {len(rows)}")
    print(f"examples built    : {len(examples)}")
    print(f"base model        : {args.base_model}")
    print(f"output dir        : {args.out}")
    print(
        "hyperparameters   : "
        f"epochs={args.epochs} lora_r={args.lora_r} lora_alpha={args.lora_alpha} "
        f"max_seq_len={args.max_seq_length} batch_size={args.batch_size}"
    )
    print("system prompt     : " + SYSTEM)
    sample = examples[0]["messages"]
    print("first example     :")
    print(f"  system    -> {sample[0]['content']}")
    print(f"  user      -> {sample[1]['content']}")
    print(f"  assistant -> {sample[2]['content']}")
    print(
        "WOULD: load base model in 4-bit, attach LoRA adapter, run SFTTrainer, "
        f"save adapter to {args.out}."
    )
    print("OK: plumbing valid. No model loaded, no GPU used, no network touched.")
    return 0


def train(args: argparse.Namespace) -> None:
    """Real QLoRA fine-tune. Heavy deps imported here — GX10 only."""
    validate_args(args)

    data_path = Path(args.data)
    rows = load_rows(data_path)  # boundary-validated
    examples = build_examples(rows)

    try:
        from datasets import Dataset
        from trl import SFTConfig, SFTTrainer
        from unsloth import FastLanguageModel
    except ImportError as exc:  # pragma: no cover - exercised only on the GX10
        raise SystemExit(
            "training stack not installed. This path needs a GPU box (GX10).\n"
            "  install: pip install unsloth trl peft datasets\n"
            "  to validate plumbing without a GPU, run with --check.\n"
            f"  (missing: {exc.name})"
        ) from exc

    model, tokenizer = FastLanguageModel.from_pretrained(
        args.base_model, max_seq_length=args.max_seq_length, load_in_4bit=True
    )
    model = FastLanguageModel.get_peft_model(model, r=args.lora_r, lora_alpha=args.lora_alpha)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=Dataset.from_list(examples),
        args=SFTConfig(
            output_dir=args.out,
            num_train_epochs=args.epochs,
            per_device_train_batch_size=args.batch_size,
        ),
    )
    trainer.train()
    model.save_pretrained(args.out)
    tokenizer.save_pretrained(args.out)
    print(f"LoRA adapter saved to {args.out}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="QLoRA fine-tune Nemotron Nano for Toronto address resolution (GX10 stretch goal)."
    )
    parser.add_argument("--data", default=DEFAULT_DATA)
    parser.add_argument("--base-model", default=DEFAULT_BASE_MODEL)
    parser.add_argument("--out", default=DEFAULT_OUT)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--lora-r", type=int, default=DEFAULT_LORA_R)
    parser.add_argument("--lora-alpha", type=int, default=DEFAULT_LORA_ALPHA)
    parser.add_argument("--max-seq-length", type=int, default=DEFAULT_MAX_SEQ_LEN)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument(
        "--check",
        "--dry-run",
        dest="check",
        action="store_true",
        help="Validate config + data plumbing offline and exit (no model, no GPU, no network).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.check:
            return run_check(args)
        train(args)
        return 0
    except DataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
