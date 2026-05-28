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
