import textwrap
from pathlib import Path

from civic_analyst.graph.builder import CivicGraph
from civic_analyst.ingest.loader import load_into_graph


def _write(p: Path, name: str, content: str) -> None:
    (p / name).write_text(textwrap.dedent(content).strip() + "\n")


def test_loads_single_address_and_composite_address(tmp_path: Path):
    # DineSafe-style: single address column + a STATUS column -> inspection.outcome
    _write(
        tmp_path,
        "dinesafe__sample.csv",
        """
        _id,Establishment Name,Establishment Address,STATUS
        1,Joe's Diner,100 Queen St W,Fail
        2,Cafe Ok,200 King St E,Pass
        """,
    )
    # Permit-style: composite address columns + STATUS -> permit.status
    _write(
        tmp_path,
        "permits__sample.csv",
        """
        PERMIT_NUM,STREET_NUM,STREET_NAME,STREET_TYPE,STATUS
        P1,100,QUEEN,ST,open
        """,
    )

    graph = CivicGraph()
    summary = load_into_graph(graph, tmp_path)

    assert summary == {"permits": 1, "dinesafe": 2}

    inspections = graph.records_for("100 Queen St W", kind="inspection")
    assert len(inspections) == 1
    assert inspections[0]["outcome"] == "Fail"

    permits = graph.records_for("100 QUEEN ST", kind="permit")
    assert len(permits) == 1 and permits[0]["status"] == "open"


def test_missing_data_dir_is_safe(tmp_path: Path):
    assert load_into_graph(CivicGraph(), tmp_path / "nope") == {}
