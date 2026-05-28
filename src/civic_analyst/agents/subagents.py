"""Specialized sub-agents. Each does one job over the knowledge graph.

These are deliberately thin: deterministic signal-gathering + a focused LLM call.
The supervisor (supervisor.py) routes to them and composes the final answer.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..graph.builder import CivicGraph
from ..ingest.datasets import REGISTRY
from .llm import LocalLLM, interactive_llm
from .verify import deterministic_summary, verify_narrative


@dataclass
class Finding:
    agent: str
    summary: str
    evidence: list[dict]
    score: float  # 0..1 risk contribution


class RetrievalAgent:
    """Pulls every graph record attached to an address."""

    name = "retrieval"

    def run(self, graph: CivicGraph, address: str) -> Finding:
        records = graph.records_for(address)
        return Finding(
            agent=self.name,
            summary=f"{len(records)} linked records for {address!r}.",
            evidence=records,
            score=0.0,
        )


class ComplianceAgent:
    """Flags open permits and recent inspection infractions."""

    name = "compliance"

    def run(self, graph: CivicGraph, address: str) -> Finding:
        permits = graph.records_for(address, kind="permit")
        inspections = graph.records_for(address, kind="inspection")
        open_permits = [p for p in permits if str(p.get("status", "")).lower() != "closed"]
        infractions = [i for i in inspections if i.get("outcome") not in (None, "Pass")]
        score = min(1.0, 0.2 * len(open_permits) + 0.3 * len(infractions))
        return Finding(
            agent=self.name,
            summary=f"{len(open_permits)} open permit(s), {len(infractions)} infraction(s).",
            evidence=open_permits + infractions,
            score=score,
        )


class RiskNarratorAgent:
    """Turns the structured findings into a plain-language risk read + action.

    This is where the local model earns its keep: reasoning over heterogeneous
    municipal records and drafting an inspector-ready rationale, fully on-device.
    """

    name = "risk_narrator"
    SYSTEM = (
        "You are a municipal risk analyst. Using ONLY the datasets named in the "
        "Evidence below, write a 3-sentence risk assessment and one concrete "
        "recommended action for an inspector. Cite the exact dataset name from the "
        "Evidence behind each claim. Use only numbers that appear in the Evidence or "
        "Findings; if a figure is not given, do not state one. Never invent dataset "
        "names, records, or statistics. End with a line: 'Sources: <comma-separated "
        "dataset names from the Evidence>'."
    )

    def __init__(self, llm: LocalLLM | None = None) -> None:
        self.llm = llm or interactive_llm()

    def _grounding(self, findings: list[Finding]) -> tuple[str, str]:
        """Build (datasets-consulted, evidence-lines) from the actual records."""
        seen: set = set()
        names: list[str] = []
        lines: list[str] = []
        for f in findings:
            for rec in f.evidence:
                rid = rec.get("id")
                if rid in seen:
                    continue
                seen.add(rid)
                key = rec.get("dataset")
                name = REGISTRY[key].title if key in REGISTRY else (key or "unknown")
                if name not in names:
                    names.append(name)
                state = rec.get("outcome") or rec.get("status") or ""
                kind = rec.get("kind", "record")
                lines.append(f"- [{name}] {kind}{f': {state}' if state else ''}")
                if len(lines) >= 12:
                    break
            if len(lines) >= 12:
                break
        return ", ".join(names) or "none", "\n".join(lines) or "(no records)"

    def run(self, address: str, findings: list[Finding]) -> str:
        bullets = "\n".join(f"- [{f.agent}] {f.summary}" for f in findings)
        consulted, evidence = self._grounding(findings)
        user = (
            f"Address: {address}\n"
            f"Datasets consulted: {consulted}\n"
            f"Evidence (cite ONLY these datasets):\n{evidence}\n"
            f"Findings:\n{bullets}"
        )
        try:
            text = self.llm.chat(self.SYSTEM, user, temperature=0.0)
        except Exception:  # offline / no model
            return deterministic_summary(address, findings)
        # Trust but verify: a narrative that cites unknown sources or invents numbers
        # is discarded in favor of the correct-by-construction summary.
        if verify_narrative(text, address, findings):
            return deterministic_summary(address, findings)
        return text
