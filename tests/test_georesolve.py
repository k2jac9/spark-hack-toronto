"""Offline geo-resolution engine (PR1) — engine + confidence/fall-out + holdout + slice guard.

All offline: tiny in-test gazetteers, no network. The committed-slice guard reads the real
demo_data/ gazetteers. The engine has no kernel consumer in this PR, so the golden numbers
are untouched by construction (see test_transit_load.py).
"""
from __future__ import annotations

import math
from pathlib import Path

from urbanos.risk.graph.builder import in_toronto_bbox
from urbanos.risk.ingest import georesolve as gr
from urbanos.risk.ingest.georesolve import (
    Gazetteers,
    OfflineGeoResolver,
    canonical_street,
    default_resolver,
    load_gazetteers,
    reset_gazetteer_cache,
)

_DEMO = Path(__file__).resolve().parent.parent / "demo_data"

# Ground truth for the in-test gazetteer (the real Grand Ave / Melrose St node).
_GRAND_MELROSE = (43.6217, -79.4918)
_QUEEN = (43.6525, -79.3839)
_WARD_CENTROID = (43.6400, -79.4000)


def _metres(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    x = math.radians(lng2 - lng1) * math.cos(math.radians((lat1 + lat2) / 2.0))
    y = math.radians(lat2 - lat1)
    return r * math.hypot(x, y)


def _tiny_gz() -> Gazetteers:
    by_id = {"42": _GRAND_MELROSE}
    by_key = {gr._intersection_key("Grand Ave / Melrose St"): _GRAND_MELROSE}
    addresses = {gr.normalize_address("100 Queen St W"): _QUEEN}
    areas = {"SPADINA FORT YORK": _WARD_CENTROID, "20": _WARD_CENTROID}
    return Gazetteers(by_id, by_key, addresses, areas, tuple(by_key), tuple(addresses))


def _resolver(**kw) -> OfflineGeoResolver:
    return OfflineGeoResolver(_tiny_gz(), **kw)


# -- canonicalisation -----------------------------------------------------------------
def test_canonical_street_folds_types_and_directions():
    assert canonical_street("Grand Avenue") == "GRAND AVE"
    assert canonical_street("queen street west") == "QUEEN ST W"
    assert canonical_street(" Melrose St. ") == "MELROSE ST"


def test_intersection_key_is_order_independent_and_canonical():
    a = gr._intersection_key("Grand Ave / Melrose St")
    assert a == gr._intersection_key("Melrose St / Grand Ave")          # sorted
    assert a == gr._intersection_key("Grand Avenue & Melrose Street")   # long-form + sep
    assert gr._intersection_key("Grand Ave") is None                    # one street → not a join


# -- cascade priority -----------------------------------------------------------------
def test_measured_beats_everything():
    r = _resolver()
    res = r.resolve({"lat": 43.6217, "lng": -79.4918,
                     "intersection_id": "42", "address": "100 Queen St W"})
    assert res.quality == "measured" and res.provenance == "input_coord"
    assert res.confidence == 1.0 and res.matched is None


def test_intersection_id_beats_string_and_address():
    r = _resolver()
    res = r.resolve({"intersection_id": "42", "intersection_desc": "Grand Ave / Melrose St",
                     "address": "100 Queen St W"})
    assert res.quality == "resolved-intersection" and res.provenance == "intersection_id"
    assert res.matched == "42" and res.confidence == 1.0


def test_intersection_string_beats_address():
    r = _resolver()
    res = r.resolve({"intersection_desc": "Grand Ave / Melrose St", "address": "100 Queen St W"})
    assert res.provenance == "intersection_exact"
    assert (res.lat, res.lng) == _GRAND_MELROSE


def test_address_beats_area():
    r = _resolver()
    res = r.resolve({"address": "100 Queen St W", "ward": "Ward 20"})
    assert res.quality == "resolved-address" and res.provenance == "address_exact"
    assert (res.lat, res.lng) == _QUEEN


def test_area_centroid_is_last_resort():
    r = _resolver()
    by_name = r.resolve({"ward": "Spadina-Fort York"})
    by_code = r.resolve({"ward": "Ward 20"})
    assert by_name.quality == "area-approx" and by_name.matched == "SPADINA FORT YORK"
    assert by_code.matched == "20" and (by_code.lat, by_code.lng) == _WARD_CENTROID


# -- resolver accuracy (variants land on the truth) -----------------------------------
def test_resolver_accuracy_for_swapped_and_longform_variants():
    r = _resolver()
    for desc in ("Grand Ave / Melrose St", "Melrose St / Grand Ave",
                 "Grand Avenue / Melrose Street"):
        res = r.resolve({"intersection_desc": desc})
        assert res.lat is not None
        assert _metres(*_GRAND_MELROSE, res.lat, res.lng) < 5.0
    # the street1/street2 pair shape resolves the same way
    pair = r.resolve({"street1": "Grand Ave", "street2": "Melrose St"})
    assert (pair.lat, pair.lng) == _GRAND_MELROSE


# -- fuzzy bound + no false pin -------------------------------------------------------
def test_typo_resolves_at_cutoff_and_absent_pair_is_unresolved():
    r = _resolver()
    typo = r.resolve({"intersection_desc": "Grand Ave / Melrne St"})
    assert typo.provenance == "intersection_fuzzy"
    assert typo.confidence >= 0.92 and typo.matched == "GRAND AVE X MELROSE ST"
    absent = r.resolve({"intersection_desc": "Nowhere Rd / Madeup Ln"})
    assert absent.quality == "unresolved" and absent.lat is None      # never a false pin


def test_address_fuzzy_reuses_normalize_address():
    r = _resolver()
    # unit + postal + city are stripped by normalize_address → the same exact key.
    res = r.resolve({"address": "100 QUEEN STREET WEST, UNIT 5, TORONTO M5H 2N2"})
    assert res.provenance == "address_exact" and (res.lat, res.lng) == _QUEEN


# -- confidence + fall-out (the runtime validation layer) -----------------------------
def test_confidence_values_per_tier():
    r = _resolver()
    assert r.resolve({"lat": 43.6217, "lng": -79.4918}).confidence == 1.0
    assert r.resolve({"intersection_desc": "Grand Ave / Melrose St"}).confidence == 0.99
    fuzzy = r.resolve({"intersection_desc": "Grand Ave / Melrne St"}).confidence
    assert 0.92 <= fuzzy < 1.0
    assert r.resolve({"ward": "Ward 20"}).confidence == 0.30
    assert r.resolve({"address": "999 Nonexistent Blvd"}).confidence == 0.0


def test_min_confidence_makes_low_tiers_fall_out():
    # A floor above the area weight makes an area-only record fall out to unresolved.
    strict = _resolver(min_confidence=0.5)
    assert strict.resolve({"ward": "Ward 20"}).quality == "unresolved"
    # A floor above a fuzzy ratio drops the fuzzy hit too (here: above any possible ratio).
    no_fuzzy = _resolver(min_confidence=0.999)
    assert no_fuzzy.resolve({"intersection_desc": "Grand Ave / Melrne St"}).quality == "unresolved"
    # ...but exact/measured still pass that same floor.
    assert no_fuzzy.resolve({"lat": 43.6217, "lng": -79.4918}).quality == "measured"


# -- bbox rejection -------------------------------------------------------------------
def test_vancouver_coord_is_not_measured():
    r = _resolver()
    res = r.resolve({"lat": 49.2827, "lng": -123.1207})   # Vancouver
    assert res.quality == "unresolved"                    # out-of-bbox coord not trusted


def test_out_of_bbox_gazetteer_rows_dropped_at_load(tmp_path: Path):
    (tmp_path / "intersections__test.csv").write_text(
        "intersection_id,desc,lat,lng\n"
        "1,A St / B St,43.65,-79.38\n"          # in Toronto
        "2,C St / D St,49.28,-123.12\n",        # Vancouver — must be dropped
        encoding="utf-8",
    )
    reset_gazetteer_cache()
    gz = load_gazetteers(tmp_path)
    assert gz.intersections_by_id == {"1": (43.65, -79.38)}


# -- degrade / offline-safe -----------------------------------------------------------
def test_empty_resolver_never_raises_and_is_unresolved():
    r = OfflineGeoResolver()                               # no gazetteers
    assert r.resolve({"address": "100 Queen St W"}).quality == "unresolved"
    assert r.resolve({"garbage": object()}).quality == "unresolved"   # never raises


def test_missing_directory_degrades_to_empty():
    reset_gazetteer_cache()
    gz = load_gazetteers(Path("/no/such/dir/xyz"))
    assert gz.is_empty()


# -- determinism ----------------------------------------------------------------------
def test_determinism():
    r = _resolver()
    rec = {"intersection_desc": "Grand Ave / Melrne St"}
    assert r.resolve(rec) == r.resolve(rec)


# -- holdout accuracy logic (the harness, exercised without committed data) ------------
def test_holdout_accuracy_and_fallout_bucket():
    r = _resolver()
    # Holdout: resolve from the desc alone (coords discarded) → lands on the truth.
    resolved = r.resolve({"intersection_desc": "Grand Ave / Melrose St"})
    assert _metres(*_GRAND_MELROSE, resolved.lat, resolved.lng) < 5.0
    # An injected bogus desc lands in the fallout bucket (unresolved, no pin).
    miss = r.resolve({"intersection_desc": "Bogus Pkwy / Imaginary Cres"})
    assert miss.lat is None and miss.quality == "unresolved"


# -- committed-slice guard (reads the real demo_data gazetteers) ----------------------
def test_committed_gazetteer_slices_are_present_and_in_bbox():
    reset_gazetteer_cache()
    gz = load_gazetteers(_DEMO)
    assert not gz.is_empty(), "expected committed gazetteer slices under demo_data/"
    assert gz.intersections_by_id and gz.intersections_by_key and gz.areas
    coords = [*gz.intersections_by_id.values(), *gz.intersections_by_key.values(),
              *gz.areas.values()]
    assert all(in_toronto_bbox(lat, lng) for lat, lng in coords)


def test_committed_slice_resolves_a_real_intersection():
    reset_gazetteer_cache()
    r = OfflineGeoResolver(load_gazetteers(_DEMO))
    res = r.resolve({"intersection_desc": "King St W / Dufferin St"})
    assert res.quality == "resolved-intersection"
    assert in_toronto_bbox(res.lat, res.lng)


# -- cache parity ---------------------------------------------------------------------
def test_default_resolver_cached_and_reset():
    reset_gazetteer_cache()
    first = default_resolver()
    assert first is default_resolver()        # process-cached singleton
    reset_gazetteer_cache()
    assert first is not default_resolver()     # reset rebuilds
