from civic_analyst.graph.builder import CivicGraph, normalize_address


def test_normalize_address_canonicalizes():
    assert normalize_address("100 Queen Street West") == "100 QUEEN ST W"
    assert normalize_address("100 queen st w") == normalize_address("100 QUEEN STREET WEST")


def test_normalize_strips_real_world_noise():
    # Real Toronto open data embeds 'None' (missing unit), postal codes, city/prov.
    assert normalize_address("1871 O'Connor Dr None M4A 1X1") == "1871 O'CONNOR DR"
    # Same location with/without postal+unit-placeholder must resolve to one key.
    assert normalize_address("100 Queen St W None M5H 2N2") == normalize_address(
        "100 Queen St West, Toronto, ON"
    )


def test_normalize_expands_more_street_types():
    # Full long-form, comma-laden, postal-coded address must collapse to the same
    # key the loader's part-based short form produces.
    assert normalize_address("123 Main Street West, Toronto, ON M5V 1A1") == "123 MAIN ST W"
    assert normalize_address("123 Main Street West, Toronto, ON M5V 1A1") == normalize_address(
        "123 MAIN ST W"
    )
    # Newly-supported street types all abbreviate to the canonical short form.
    for long, short in [
        ("Drive", "DR"),
        ("Road", "RD"),
        ("Court", "CRT"),
        ("Crescent", "CRES"),
        ("Place", "PL"),
        ("Terrace", "TER"),
    ]:
        assert normalize_address(f"50 Oak {long}") == f"50 OAK {short}"
    # LANE: the long word and the "LN" abbreviation must agree on one key.
    assert normalize_address("9 Foundry Lane") == normalize_address("9 Foundry Ln")


def test_normalize_strips_unit_suite_noise():
    base = "100 Queen St W"
    for noisy in [
        "100 Queen St W Unit 5",
        "100 Queen St W, Suite 200",
        "100 Queen St W Ste 12",
        "100 Queen St W #404",
        "100 Queen St W Flr 3",
        "100 Queen St W Apt 6B",
    ]:
        assert normalize_address(noisy) == normalize_address(base), noisy


def test_normalize_handles_punctuation_and_spacing_quirks():
    # "ST." vs "ST", doubled spaces and stray punctuation must not fragment the key.
    assert normalize_address("100 Queen St. W") == "100 QUEEN ST W"
    assert normalize_address("100   Queen   St   W") == "100 QUEEN ST W"
    assert normalize_address("100 Queen St W;") == "100 QUEEN ST W"


def test_real_world_variants_fuse_to_one_node():
    # Two real-world formats of the same address (long form + postal/unit vs. the
    # short loader form) must land on a single fused address node carrying all three.
    g = CivicGraph()
    g.add_record("permit", "P1", "12 Yonge Street, Toronto, ON M5E 1J9", status="open")
    g.add_record("inspection", "I1", "12 Yonge St Unit 3", outcome="Fail")
    g.add_record("licence", "L1", "12 YONGE ST", status="active")

    assert len(g.addresses()) == 1  # one physical building, one node
    kinds = sorted(r["kind"] for r in g.records_for("12 Yonge St"))
    assert kinds == ["inspection", "licence", "permit"]


def test_records_attach_to_address():
    g = CivicGraph()
    g.add_record("permit", "P1", "100 Queen St W", status="open")
    g.add_record("inspection", "I1", "100 Queen Street West", outcome="Fail")

    permits = g.records_for("100 QUEEN ST W", kind="permit")
    inspections = g.records_for("100 Queen St W", kind="inspection")

    assert len(permits) == 1 and permits[0]["status"] == "open"
    assert len(inspections) == 1 and inspections[0]["outcome"] == "Fail"
    assert g.records_for("999 Nowhere Rd") == []
