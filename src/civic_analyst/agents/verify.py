"""Deterministic guards against LLM hallucination in the risk narrative.

The risk score and findings are computed WITHOUT an LLM; the model only writes
prose. These functions verify that prose against the findings and, on failure, the
caller substitutes a deterministic templated summary — so a hallucinated sentence
can never reach the user. (Maps to the Prime Intellect "Verifiers" bounty.)

No import from subagents here (avoids a cycle); `findings` are duck-typed objects
exposing `.summary` (str) and `.evidence` (list[dict]).
"""
from __future__ import annotations

import re

from ..ingest.datasets import REGISTRY


def consulted_datasets(findings) -> list[str]:
    """Human dataset titles actually present in the evidence (the allowed sources)."""
    names: list[str] = []
    for f in findings:
        for rec in f.evidence:
            key = rec.get("dataset")
            name = REGISTRY[key].title if key in REGISTRY else (key or "")
            if name and name not in names:
                names.append(name)
    return names


def evidence_records(findings, cap: int = 12) -> list[dict]:
    """Compact, de-duplicated record list for provenance display ('show your work')."""
    seen: set = set()
    out: list[dict] = []
    for f in findings:
        for rec in f.evidence:
            rid = rec.get("id")
            if rid in seen:
                continue
            seen.add(rid)
            key = rec.get("dataset")
            out.append(
                {
                    "dataset": REGISTRY[key].title if key in REGISTRY else (key or "?"),
                    "kind": rec.get("kind", "record"),
                    "detail": rec.get("outcome") or rec.get("status") or "",
                }
            )
            if len(out) >= cap:
                return out
    return out


def _ints(s: str) -> set[int]:
    return {int(x) for x in re.findall(r"\d+", s or "")}


def verify_narrative(text: str, address: str, findings) -> list[str]:
    """Return a list of hallucination issues; empty means the narrative checks out."""
    issues: list[str] = []

    # 1) Every number stated must be traceable to the findings, address, or a year.
    allowed = _ints(address)
    for f in findings:
        allowed |= _ints(f.summary)
        for rec in f.evidence:
            allowed |= _ints(str(rec.get("outcome", ""))) | _ints(str(rec.get("status", "")))
    bad_nums = {n for n in (_ints(text) - allowed) if not 1900 <= n <= 2100}
    if bad_nums:
        issues.append(f"unverified number(s): {sorted(bad_nums)}")

    # 2) Any named "<X> dataset/records/database" must be an allowed source.
    allowed_titles = [t.lower() for t in consulted_datasets(findings)]
    for phrase in re.findall(
        r"([A-Z][\w&'-]+(?:\s+[A-Z][\w&'-]+)*)\s+(?i:datasets?|database|records?|data)\b",
        text,
    ):
        p = phrase.lower()
        if not any(p in t or t in p for t in allowed_titles):
            issues.append(f"unverified source: {phrase!r}")

    return issues


def deterministic_summary(address: str, findings) -> str:
    """Correct-by-construction summary built only from the findings (no LLM)."""
    sources = ", ".join(consulted_datasets(findings)) or "the linked Toronto open datasets"
    facts = "; ".join(f.summary.rstrip(".") for f in findings)
    return (
        f"Risk summary for {address} based on {sources}. {facts}. "
        "Recommended action: schedule an on-site inspection to verify compliance."
    )
