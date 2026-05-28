"""The hallucination guard must catch invented numbers/sources and fall back."""
from civic_analyst.agents.subagents import Finding, RiskNarratorAgent
from civic_analyst.agents.verify import (
    deterministic_summary,
    evidence_records,
    verify_narrative,
)

ADDRESS = "100 Queen St W"
FINDINGS = [
    Finding(
        "retrieval",
        "3 linked records for '100 Queen St W'.",
        [
            {"id": "inspection:1", "kind": "inspection", "dataset": "dinesafe", "outcome": "Fail"},
            {"id": "permit:1", "kind": "permit", "dataset": "permits", "status": "open"},
        ],
        0.0,
    ),
    Finding("compliance", "1 open permit(s), 1 infraction(s).", [], 0.5),
]

CLEAN = (
    "The address has 1 open permit and 1 infraction per DineSafe — Food Premises "
    "Inspections and Building Permits — Active Permits. Recommended action: inspect. "
    "Sources: DineSafe — Food Premises Inspections, Building Permits — Active Permits."
)


class _StubLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply

    def chat(self, system: str, user: str, temperature: float = 0.2) -> str:
        return self.reply


def test_clean_narrative_passes():
    assert verify_narrative(CLEAN, ADDRESS, FINDINGS) == []


def test_fabricated_number_is_caught():
    issues = verify_narrative("There are 7 infractions and a $5000 fine.", ADDRESS, FINDINGS)
    assert any("number" in i for i in issues)


def test_invented_source_is_caught():
    issues = verify_narrative("Per the Toronto Police Records, this is unsafe.", ADDRESS, FINDINGS)
    assert any("source" in i for i in issues)


def test_narrator_falls_back_on_hallucination():
    lie = "There are 42 infractions per the Secret Police Database."
    out = RiskNarratorAgent(llm=_StubLLM(lie)).run(ADDRESS, FINDINGS)
    assert out != lie
    assert "42" not in out
    assert out == deterministic_summary(ADDRESS, FINDINGS)


def test_narrator_keeps_clean_output():
    assert RiskNarratorAgent(llm=_StubLLM(CLEAN)).run(ADDRESS, FINDINGS) == CLEAN


def test_evidence_records_dedup_and_titles():
    recs = evidence_records(FINDINGS)
    assert {r["dataset"] for r in recs} == {
        "DineSafe — Food Premises Inspections",
        "Building Permits — Active Permits",
    }
