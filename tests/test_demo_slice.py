"""Guard the committed REAL downtown slice so `make demo` always works on real data."""
from pathlib import Path

from civic_analyst.agents.supervisor import Supervisor
from civic_analyst.graph.builder import CivicGraph
from civic_analyst.ingest.loader import load_into_graph

SLICE = Path(__file__).resolve().parent.parent / "demo_data"


def test_real_slice_loads_in_bbox_with_some_risk():
    g = CivicGraph()
    summary = load_into_graph(g, SLICE)
    assert summary.get("dinesafe", 0) > 0

    addrs = g.addresses(with_coords=True)
    assert addrs, "expected geocoded downtown addresses"
    # Every pin must fall inside the offline PMTiles basemap extent.
    assert all(
        43.62 <= a["lat"] <= 43.69 and -79.43 <= a["lng"] <= -79.34 for a in addrs
    )
    # At least one at-risk address so the map shows a non-green pin.
    sup = Supervisor(g)
    assert any(sup.score_only(a["label"]) > 0 for a in addrs)


def test_real_cross_dataset_fusion():
    """The slice must show genuine multi-dataset linking across all three sources."""
    g = CivicGraph()
    summary = load_into_graph(g, SLICE)
    assert summary.get("licences", 0) > 0
    assert summary.get("permits", 0) > 0

    triple = [
        a["label"]
        for a in g.addresses(with_coords=True)
        if g.records_for(a["label"], kind="inspection")
        and g.records_for(a["label"], kind="licence")
        and g.records_for(a["label"], kind="permit")
    ]
    assert triple, "expected ≥1 address linking inspection + licence + permit"
