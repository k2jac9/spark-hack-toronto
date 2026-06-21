"""Offline geo-resolution engine — turn whatever geo a record has into (lat, lng).

Many real civic datasets carry only an **address**, an **intersection string**, or a
**ward / neighbourhood** — no lat/lng (we already skip 311 for exactly this reason). This
module is a reusable, **100% offline** resolver that maps any such record to a coordinate
plus a ``quality`` tier, using only **local committed gazetteers** (no geocoding API, no
CDN). It makes the "ingest any city's open data" claim real for messy-geo datasets.

Design (all deterministic, all offline-safe — ``resolve()`` never raises, construction
degrades to empty gazetteers when ``demo_data/`` lacks the files):

- It is built from existing primitives — ``normalize_address`` + ``in_toronto_bbox`` +
  ``_STREET_TYPES``/``_DIRECTIONS`` (graph.builder) and ``_find_col`` / ``_clean_address`` /
  ``_coord`` / ``_read_rows`` (ingest.loader) — plus stdlib :mod:`difflib` for the bounded
  fuzzy match. No new third-party dependency.
- ``normalize_address`` is pinned by ``tests/test_normalize.py`` and is **never edited**; the
  intersection path uses a *new* :func:`canonical_street` helper that reuses the same
  street-type / direction constants.
- Every coordinate — input **and** gazetteer-stored — is validated through
  ``in_toronto_bbox``, so a swapped / out-of-region coord falls through to the next tier
  instead of being trusted, and we never emit a ``(0, 0)`` pin.

Cascade (first in-bbox hit wins): measured → intersection-id → intersection-string →
address → area-centroid → unresolved. Each hit carries a numeric ``confidence`` (1.0 for
measured / exact, the difflib ratio for a fuzzy hit, a fixed coarse weight for an area
centroid) and a candidate below the active gate ``max(min_confidence, tier_gate)`` *falls
out* to the next tier rather than being accepted as a low-trust pin.

**Integration seam (documented here, not wired in this PR).** The resolver sits between raw
ingest and the existing Gaussian proximity-fusion: a future producer calls
``default_resolver().resolve(raw_row)`` and emits ``{location, lat, lng, value, quality}``
into a ``demo_data/{key}__downtown.csv`` that the existing ``timeseries.load_station_values``
reads **unchanged** (it already ignores the extra ``quality`` column), which a future
``*_by_node`` adapter then fuses onto the substrate. No kernel / adapter / api / UI file is
touched by this module.
"""
from __future__ import annotations

import difflib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..config import settings
from ..graph.builder import (
    _DIRECTIONS,
    _STREET_TYPES,
    in_toronto_bbox,
    normalize_address,
)
from .loader import _clean_address, _coord, _find_col, _read_rows

# Quality tiers, coarsest-trust last. Surfaced on every GeoResult so downstream fusion can
# weight (or drop) a record by how it was resolved.
QUALITY_MEASURED = "measured"
QUALITY_INTERSECTION = "resolved-intersection"
QUALITY_ADDRESS = "resolved-address"
QUALITY_AREA = "area-approx"
QUALITY_UNRESOLVED = "unresolved"

# Confidence gates. Measured / exact-key hits are effectively certain; a fuzzy hit reports
# its actual difflib ratio; an area centroid is the explicitly coarse tier.
_EXACT_CONFIDENCE = 0.99
_AREA_CONFIDENCE = 0.30

# Street-type / direction folding reuses the builder constants but is applied to a *single*
# street name (no house number), so we can't reuse normalize_address directly.
_PUNCT_RE = re.compile(r"[.,;:/\\]")
# Separators between the two streets of an intersection description.
_INTERSECTION_SPLIT_RE = re.compile(r"\s*(?:/|&|\bAND\b|\bAT\b|\bX\b)\s*", re.IGNORECASE)
# Everything that isn't a letter/digit collapses to a single space in an area key.
_AREA_PUNCT_RE = re.compile(r"[^A-Z0-9]+")


@dataclass(frozen=True)
class GeoResult:
    """A resolution outcome. ``matched`` echoes the gazetteer key that matched (``None`` for
    measured / unresolved) so every fuzzy join is auditable; ``confidence`` ∈ [0, 1]."""

    lat: float | None
    lng: float | None
    quality: str
    provenance: str
    matched: str | None
    confidence: float


_UNRESOLVED = GeoResult(None, None, QUALITY_UNRESOLVED, "none", None, 0.0)


@dataclass(frozen=True)
class Gazetteers:
    """The three offline lookup tables, built once. Each value is an in-bbox ``(lat, lng)``.
    The ``*_keys`` tuples are the difflib search spaces, precomputed for determinism."""

    intersections_by_id: dict[str, tuple[float, float]]
    intersections_by_key: dict[str, tuple[float, float]]
    addresses: dict[str, tuple[float, float]]
    areas: dict[str, tuple[float, float]]
    intersection_keys: tuple[str, ...]
    address_keys: tuple[str, ...]

    def is_empty(self) -> bool:
        return not (
            self.intersections_by_id
            or self.intersections_by_key
            or self.addresses
            or self.areas
        )


_EMPTY_GAZETTEERS = Gazetteers({}, {}, {}, {}, (), ())


# --------------------------------------------------------------------------------------
# Canonicalisation helpers (reuse builder constants; never edit normalize_address)
# --------------------------------------------------------------------------------------
def canonical_street(name: str) -> str:
    """Canonicalise a single street name for an intersection key. Reuses the same
    ``_STREET_TYPES`` / ``_DIRECTIONS`` folding as ``normalize_address`` (which is pinned by
    tests and must not change): uppercase, strip BOM + punctuation, fold long street types
    and compass words, collapse whitespace. Returns ``""`` for an empty / null name."""
    s = str(name).replace("﻿", "").upper().strip()
    s = _PUNCT_RE.sub(" ", s)
    for long, short in _STREET_TYPES.items():
        s = re.sub(rf"\b{long}\b", short, s)
    for long, short in _DIRECTIONS.items():
        s = re.sub(rf"\b{long}\b", short, s)
    return re.sub(r"\s+", " ", s).strip()


def _intersection_key(desc: str) -> str | None:
    """Order-independent canonical key for an intersection description. Splits on the common
    separators (``/ & AND AT X``), canonicalises each street, drops blanks, **sorts** the
    segments so "A / B" == "B / A", and joins with " X ". ``None`` when fewer than two
    distinct streets survive (so a lone street name can't masquerade as an intersection)."""
    if not desc:
        return None
    parts = [canonical_street(p) for p in _INTERSECTION_SPLIT_RE.split(desc)]
    parts = sorted({p for p in parts if p})
    if len(parts) < 2:
        return None
    return " X ".join(parts)


def _normalize_area(val: str) -> str:
    """Key for a ward / neighbourhood name or code: uppercase, non-alphanumerics → space,
    drop a leading ``WARD`` token so "Ward 20" / "20" collapse, collapse whitespace."""
    s = _AREA_PUNCT_RE.sub(" ", str(val).replace("﻿", "").upper()).strip()
    if s.startswith("WARD "):
        s = s[5:].strip()
    s = re.sub(r"\s+", " ", s).strip()
    if s.isdigit():            # "07" / "7" / "Ward 07" all collapse to the same code key
        s = str(int(s))
    return s


# --------------------------------------------------------------------------------------
# Gazetteer loading (schema-tolerant, offline-safe — empty on absence)
# --------------------------------------------------------------------------------------
def _iter_files(data_dir: Path, stem: str) -> list[Path]:
    return sorted([*data_dir.glob(f"{stem}*.csv"), *data_dir.glob(f"{stem}*.json")])


def _load_intersections(data_dir: Path) -> tuple[dict, dict]:
    by_id: dict[str, tuple[float, float]] = {}
    by_key: dict[str, tuple[float, float]] = {}
    for path in _iter_files(data_dir, "intersections__"):
        try:
            columns, rows = _read_rows(path)
        except Exception:  # noqa: BLE001 — a bad slice must not break the load
            continue
        lat_col = _find_col(columns, ("latitude", "lat"))
        lng_col = _find_col(columns, ("longitude", "long", "lng"))
        if not (lat_col and lng_col):
            continue
        id_col = _find_col(columns, ("intersection_id", "intersectionid", "int_id"))
        # "desc" before any bare "intersection" keyword: the latter also matches the
        # intersection_id column (substring), which would key the gazetteer off id numbers.
        desc_col = _find_col(columns, ("intersection_desc", "desc", "cross"))
        for row in rows:
            lat, lng = _coord(row, lat_col), _coord(row, lng_col)
            if not in_toronto_bbox(lat, lng):
                continue
            if id_col:
                rid = str(row.get(id_col, "")).strip()
                if rid:
                    by_id.setdefault(rid, (lat, lng))
            if desc_col:
                key = _intersection_key(str(row.get(desc_col, "")))
                if key:
                    by_key.setdefault(key, (lat, lng))
    return by_id, by_key


# Our own gazetteer outputs are not an address corpus — skip them when scanning for one.
_NON_ADDRESS_PREFIXES = (
    "intersections__",
    "ward_centroids",
    "neighbourhood_centroids",
    "gazetteer_validation",
)


def _load_addresses(data_dir: Path) -> dict:
    """Address corpus = every committed slice that carries BOTH an ``address`` column and
    coordinates (DineSafe qualifies; permits/licences only if they ever ship coords). The
    key is the same ``normalize_address`` join key the civic graph uses."""
    out: dict[str, tuple[float, float]] = {}
    for path in sorted([*data_dir.glob("*.csv"), *data_dir.glob("*.json")]):
        if path.name.startswith(_NON_ADDRESS_PREFIXES):
            continue
        try:
            columns, rows = _read_rows(path)
        except Exception:  # noqa: BLE001
            continue
        addr_col = _find_col(columns, ("address",))
        lat_col = _find_col(columns, ("latitude", "lat"))
        lng_col = _find_col(columns, ("longitude", "long", "lng"))
        if not (addr_col and lat_col and lng_col):
            continue
        for row in rows:
            lat, lng = _coord(row, lat_col), _coord(row, lng_col)
            if not in_toronto_bbox(lat, lng):
                continue
            key = normalize_address(_clean_address(row.get(addr_col)))
            if key:
                out.setdefault(key, (lat, lng))
    return out


def _load_areas(data_dir: Path) -> dict:
    """Ward + neighbourhood centroids keyed by both their name and their code, validated
    against the **city** bbox so a non-downtown ward still resolves to its own centroid."""
    out: dict[str, tuple[float, float]] = {}
    specs = (
        ("ward_centroids", ("code", "ward", "area_code"), ("name", "ward_name", "area")),
        (
            "neighbourhood_centroids",
            ("code", "short_code", "number", "id"),
            ("name", "neighbourhood", "neighborhood", "area"),
        ),
    )
    for stem, code_kws, name_kws in specs:
        for path in _iter_files(data_dir, stem):
            try:
                columns, rows = _read_rows(path)
            except Exception:  # noqa: BLE001
                continue
            lat_col = _find_col(columns, ("centroid_lat", "latitude", "lat"))
            lng_col = _find_col(columns, ("centroid_lng", "centroid_long", "longitude", "long", "lng"))
            if not (lat_col and lng_col):
                continue
            code_col = _find_col(columns, code_kws)
            name_col = _find_col(columns, name_kws)
            for row in rows:
                lat, lng = _coord(row, lat_col), _coord(row, lng_col)
                if not in_toronto_bbox(lat, lng):
                    continue
                for col in (name_col, code_col):
                    if not col:
                        continue
                    key = _normalize_area(str(row.get(col, "")))
                    if key:
                        out.setdefault(key, (lat, lng))
    return out


def _build_gazetteers(data_dir: Path) -> Gazetteers:
    if not data_dir.exists():
        return _EMPTY_GAZETTEERS
    by_id, by_key = _load_intersections(data_dir)
    addresses = _load_addresses(data_dir)
    areas = _load_areas(data_dir)
    return Gazetteers(
        intersections_by_id=by_id,
        intersections_by_key=by_key,
        addresses=addresses,
        areas=areas,
        intersection_keys=tuple(by_key.keys()),
        address_keys=tuple(addresses.keys()),
    )


# Process-cached, keyed by resolved directory, so the default resolver and the committed-slice
# guard test share a build while still allowing isolated dirs. reset_gazetteer_cache() clears it.
_GAZETTEER_CACHE: dict[str, Gazetteers] = {}
_DEFAULT_RESOLVER: "OfflineGeoResolver | None" = None


def load_gazetteers(data_dir: Path | None = None) -> Gazetteers:
    """Build (and cache) the gazetteers under ``data_dir`` (default ``settings.data_dir``,
    matching ``load_counts`` / ``load_station_values``). Empty — not an error — when the
    directory or files are absent: the offline-safe boundary."""
    d = Path(data_dir) if data_dir is not None else settings.data_dir
    cache_key = str(d.resolve()) if d.exists() else str(d)
    cached = _GAZETTEER_CACHE.get(cache_key)
    if cached is not None:
        return cached
    gz = _build_gazetteers(d)
    _GAZETTEER_CACHE[cache_key] = gz
    return gz


def reset_gazetteer_cache() -> None:
    """Clear the cached gazetteers and default resolver (parity with the adapters'
    ``reset_*_cache`` functions — lets tests / long-running servers reset deterministically)."""
    global _GAZETTEER_CACHE, _DEFAULT_RESOLVER
    _GAZETTEER_CACHE = {}
    _DEFAULT_RESOLVER = None


def default_resolver() -> "OfflineGeoResolver":
    """Process-cached resolver over the default-directory gazetteers."""
    global _DEFAULT_RESOLVER
    if _DEFAULT_RESOLVER is None:
        _DEFAULT_RESOLVER = OfflineGeoResolver(load_gazetteers())
    return _DEFAULT_RESOLVER


# --------------------------------------------------------------------------------------
# The resolver
# --------------------------------------------------------------------------------------
class OfflineGeoResolver:
    """Resolve a record to ``(lat, lng, quality)`` via the offline cascade. Construction with
    no gazetteers (or empty ones) is valid — every record then resolves to ``unresolved``."""

    def __init__(
        self,
        gazetteers: Gazetteers | None = None,
        *,
        fuzzy_cutoff: float = 0.92,
        min_confidence: float = 0.0,
    ) -> None:
        self.gz = gazetteers if gazetteers is not None else _EMPTY_GAZETTEERS
        self.fuzzy_cutoff = float(fuzzy_cutoff)
        self.min_confidence = float(min_confidence)

    def resolve(self, record: Mapping[str, object]) -> GeoResult:
        """Never raises — any unexpected error degrades to ``unresolved`` (offline-safe)."""
        try:
            return self._resolve(record)
        except Exception:  # noqa: BLE001 — a malformed record must not break ingest
            return _UNRESOLVED

    # -- cascade --------------------------------------------------------------
    def _resolve(self, record: Mapping[str, object]) -> GeoResult:
        keys = list(record.keys())

        # 1) measured — a valid in-bbox coordinate already on the record.
        lat = _coord(record, _find_col(keys, ("latitude", "lat")))
        lng = _coord(record, _find_col(keys, ("longitude", "long", "lng")))
        if in_toronto_bbox(lat, lng):
            return GeoResult(lat, lng, QUALITY_MEASURED, "input_coord", None, 1.0)

        # 2) intersection by id — exact key in the Centreline gazetteer.
        id_col = _find_col(keys, ("intersection_id", "intersectionid", "int_id"))
        if id_col and self.gz.intersections_by_id and self._gate(1.0):
            rid = str(record.get(id_col, "")).strip()
            hit = self.gz.intersections_by_id.get(rid)
            if hit is not None:
                return GeoResult(*hit, QUALITY_INTERSECTION, "intersection_id", rid, 1.0)

        # 3) intersection by string — canonical 2-street key, exact then bounded fuzzy.
        res = self._resolve_intersection_string(record, keys)
        if res is not None:
            return res

        # 4) address — normalize_address key, exact then bounded fuzzy.
        res = self._resolve_address(record, keys)
        if res is not None:
            return res

        # 5) area centroid — ward / neighbourhood name or code (coarsest, approximate).
        res = self._resolve_area(record, keys)
        if res is not None:
            return res

        # 6) unresolved — honest miss, never a (0, 0) pin.
        return _UNRESOLVED

    # -- tiers ----------------------------------------------------------------
    def _gate(self, confidence: float) -> bool:
        """A candidate is accepted only at or above the global ``min_confidence`` floor."""
        return confidence >= self.min_confidence

    def _closest(self, key: str, candidates: Sequence[str]) -> tuple[str | None, float]:
        match = difflib.get_close_matches(key, candidates, n=1, cutoff=self.fuzzy_cutoff)
        if not match:
            return None, 0.0
        return match[0], difflib.SequenceMatcher(None, key, match[0]).ratio()

    def _resolve_intersection_string(
        self, record: Mapping[str, object], keys: list[str]
    ) -> GeoResult | None:
        if not self.gz.intersections_by_key:
            return None
        desc_col = _find_col(keys, ("intersection_desc", "desc", "cross", "at_street"))
        desc = str(record.get(desc_col, "")).strip() if desc_col else ""
        if not desc:
            s1 = _find_col(keys, ("street1", "street_1", "from_street", "main"))
            s2 = _find_col(keys, ("street2", "street_2", "to_street", "cross_street", "side"))
            if s1 and s2:
                desc = f"{record.get(s1, '')} / {record.get(s2, '')}"
        key = _intersection_key(desc)
        if not key:
            return None
        hit = self.gz.intersections_by_key.get(key)
        if hit is not None:
            if self._gate(_EXACT_CONFIDENCE):
                return GeoResult(*hit, QUALITY_INTERSECTION, "intersection_exact", key, _EXACT_CONFIDENCE)
            return None
        cand, score = self._closest(key, self.gz.intersection_keys)
        if cand is not None and self._gate(score):
            hit = self.gz.intersections_by_key[cand]
            return GeoResult(*hit, QUALITY_INTERSECTION, "intersection_fuzzy", cand, score)
        return None

    def _resolve_address(
        self, record: Mapping[str, object], keys: list[str]
    ) -> GeoResult | None:
        if not self.gz.addresses:
            return None
        addr_col = _find_col(keys, ("address", "addr"))
        if not addr_col:
            return None
        key = normalize_address(_clean_address(record.get(addr_col)))
        if not key:
            return None
        hit = self.gz.addresses.get(key)
        if hit is not None:
            if self._gate(_EXACT_CONFIDENCE):
                return GeoResult(*hit, QUALITY_ADDRESS, "address_exact", key, _EXACT_CONFIDENCE)
            return None
        cand, score = self._closest(key, self.gz.address_keys)
        if cand is not None and self._gate(score):
            hit = self.gz.addresses[cand]
            return GeoResult(*hit, QUALITY_ADDRESS, "address_fuzzy", cand, score)
        return None

    def _resolve_area(
        self, record: Mapping[str, object], keys: list[str]
    ) -> GeoResult | None:
        if not self.gz.areas or not self._gate(_AREA_CONFIDENCE):
            return None
        col = _find_col(keys, ("ward", "neighbourhood", "neighborhood", "area", "district"))
        if not col:
            return None
        key = _normalize_area(str(record.get(col, "")))
        if not key:
            return None
        hit = self.gz.areas.get(key)
        if hit is None:
            return None
        return GeoResult(*hit, QUALITY_AREA, "area_centroid", key, _AREA_CONFIDENCE)
