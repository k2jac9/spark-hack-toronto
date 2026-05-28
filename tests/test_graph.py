from civic_analyst.graph.builder import CivicGraph, normalize_address


def test_normalize_address_canonicalizes():
    assert normalize_address("100 Queen Street West") == "100 QUEEN ST W"
    assert normalize_address("100 queen st w") == normalize_address("100 QUEEN STREET WEST")


def test_records_attach_to_address():
    g = CivicGraph()
    g.add_record("permit", "P1", "100 Queen St W", status="open")
    g.add_record("inspection", "I1", "100 Queen Street West", outcome="Fail")

    permits = g.records_for("100 QUEEN ST W", kind="permit")
    inspections = g.records_for("100 Queen St W", kind="inspection")

    assert len(permits) == 1 and permits[0]["status"] == "open"
    assert len(inspections) == 1 and inspections[0]["outcome"] == "Fail"
    assert g.records_for("999 Nowhere Rd") == []
