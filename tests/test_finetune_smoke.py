"""Offline smoke tests for the QLoRA fine-tune script's --check / dry-run path.

These never import torch/peft/trl/unsloth, never hit the network, and never touch a
GPU. They exercise the plumbing (config validation + training-data builder) so the
GX10 stretch goal stays verifiable from a laptop / CI.
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "finetune_address_resolution.py"


def _load_module():
    """Import the script as a module without running training (it guards heavy deps)."""
    if not SCRIPT.exists():
        pytest.skip(f"script not found: {SCRIPT}")
    spec = importlib.util.spec_from_file_location("finetune_address_resolution", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # must not require torch/peft/etc.
    return mod


def test_module_imports_without_training_stack():
    """Importing the module must not pull in torch/unsloth/trl."""
    mod = _load_module()
    assert hasattr(mod, "run_check")
    assert hasattr(mod, "build_examples")
    # Heavy deps must not have been imported as a side effect of import.
    for heavy in ("torch", "unsloth", "trl", "peft", "bitsandbytes"):
        assert heavy not in sys.modules, f"{heavy} was imported at module load time"


def test_build_examples_shape():
    """The data builder emits well-formed 3-message chat examples."""
    mod = _load_module()
    rows = [{"raw": "100 Queen Street West", "canonical": "100 QUEEN ST W"}]
    examples = mod.build_examples(rows)
    assert len(examples) == 1
    msgs = examples[0]["messages"]
    assert [m["role"] for m in msgs] == ["system", "user", "assistant"]
    assert msgs[1]["content"] == "100 Queen Street West"
    assert msgs[2]["content"] == "100 QUEEN ST W"
    assert msgs[0]["content"] == mod.SYSTEM


def test_run_check_synthetic(capsys):
    """run_check with a non-existent data path falls back to the synthetic sample, exits 0."""
    mod = _load_module()
    args = mod.build_parser().parse_args(
        ["--check", "--data", "/nonexistent/does_not_exist.jsonl"]
    )
    rc = mod.run_check(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK: plumbing valid" in out
    assert "synthetic sample" in out
    assert "no model loaded" in out.lower()


def test_run_check_with_real_fixture(capsys):
    """run_check reads the committed JSONL fixture when present."""
    mod = _load_module()
    fixture = REPO_ROOT / "fixtures" / "address_resolution.sample.jsonl"
    if not fixture.exists():
        pytest.skip("fixture not present in this checkout")
    args = mod.build_parser().parse_args(["--check", "--data", str(fixture)])
    rc = mod.run_check(args)
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK: plumbing valid" in out
    assert str(fixture) in out


def test_validate_args_rejects_bad_hyperparams():
    """Bad hyperparameters raise DataError, not a mid-train traceback."""
    mod = _load_module()
    args = mod.build_parser().parse_args(["--check", "--epochs", "0"])
    with pytest.raises(mod.DataError):
        mod.validate_args(args)


def test_load_rows_rejects_malformed(tmp_path):
    """A row missing 'canonical' is rejected at the boundary with a clear error."""
    mod = _load_module()
    bad = tmp_path / "bad.jsonl"
    bad.write_text(json.dumps({"raw": "100 Queen St W"}) + "\n", encoding="utf-8")
    with pytest.raises(mod.DataError) as exc:
        mod.load_rows(bad)
    assert "canonical" in str(exc.value)


def test_cli_check_subprocess():
    """End-to-end: the --check CLI path exits 0 with no training stack installed."""
    if not SCRIPT.exists():
        pytest.skip(f"script not found: {SCRIPT}")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--data", "/nonexistent/x.jsonl"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK: plumbing valid" in proc.stdout
