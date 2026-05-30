"""Load pre-downloaded Toronto open-data files into a CivicGraph.

Reads the files produced by scripts/download_data.py (named `<key>__*.csv|json`)
and attaches each row to its address node. Schemas vary across datasets, so column
resolution is heuristic with light per-dataset hints — it degrades gracefully when
a column is missing rather than failing the whole load. If DATA_DIR is empty the
graph simply stays empty and the API still boots (offline-safe).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from ..config import settings
from ..graph.builder import CivicGraph
from .datasets import REGISTRY

# Registry key -> graph node kind.
KIND_BY_KEY: dict[str, str] = {
    "permits": "permit",
    "permits_cleared": "permit",
    "dinesafe": "inspection",
    "311": "request",
    "licences": "licence",
}

# Which graph attribute the ComplianceAgent reads, by kind, and the source-column
# keywords that map to it (first matching column wins, case-insensitive substring).
_STATE_ATTR: dict[str, tuple[str, tuple[str, ...]]] = {
    "permit": ("status", ("status",)),
    "inspection": ("outcome", ("status", "outcome", "result", "severity")),
    "request": ("status", ("status",)),
    "licence": ("status", ("status",)),
}

_ADDRESS_PART_KEYWORDS = (
    ("num", ("street_num", "st_num", "street number", "streetnum")),
    ("name", ("street_name", "st_name", "street name", "streetname")),
    ("type", ("street_type", "st_type", "street type")),
    ("dir", ("street_dir", "direction")),
)

_ROW_LIMIT = 5000  # cap per file for a snappy demo on the GX10


def _norm_header(col: Any) -> str:
    """Lowercase + strip a header for matching, tolerating BOM, NBSP, stray
    surrounding whitespace and embedded newlines from real-world CSV exports.
    The original column name is what we look up rows by, so this only affects
    matching — never the row-key used to read a value."""
    return (
        str(col)
        .replace("﻿", "")  # UTF-8 BOM pandas can leave on the first header
        .replace("\xa0", " ")  # non-breaking space
        .replace("\n", " ")
        .replace("\r", " ")
        .strip()
        .lower()
    )


def _find_col(columns: list[str], keywords: tuple[str, ...]) -> str | None:
    """First column whose normalized name contains any keyword. Returns the
    *original* column name so row lookups by the unmodified header still work."""
    for col in columns:
        low = _norm_header(col)
        if any(kw in low for kw in keywords):
            return col
    return None


def _resolve_plan(columns: list[str], kind: str) -> dict[str, Any]:
    """Decide once per file how to read address / id / state from its columns."""
    single = _find_col(columns, ("address",))
    parts = {tag: _find_col(columns, kws) for tag, kws in _ADDRESS_PART_KEYWORDS}
    id_col = _find_col(columns, ("_id", "permit_num", "licence", "license", "id"))
    state_attr, state_kws = _STATE_ATTR.get(kind, ("status", ("status",)))
    return {
        "address_single": single,
        "address_parts": [parts[t] for t in ("num", "name", "type", "dir") if parts[t]],
        "id_col": id_col,
        "state_attr": state_attr,
        "state_col": _find_col(columns, state_kws),
        # A date column makes each evidence row traceable to a real, dated record (#5).
        "date_col": _find_col(columns, ("date", "issued", "inspection_date", "_dt")),
        "lat_col": _find_col(columns, ("latitude", "lat")),
        "lng_col": _find_col(columns, ("longitude", "long", "lng")),
    }


def _clean_value(val: Any) -> str:
    """Collapse any whitespace (incl. embedded newlines/tabs from multiline CSV
    cells) to single spaces and strip. Empty / missing becomes ''."""
    if val is None:
        return ""
    return " ".join(str(val).split())


def _address(row: dict[str, Any], plan: dict[str, Any]) -> str | None:
    if plan["address_single"]:
        val = _clean_value(row.get(plan["address_single"]))
        return val or None
    if plan["address_parts"]:
        parts = [_clean_value(row.get(c)) for c in plan["address_parts"]]
        joined = " ".join(p for p in parts if p)
        return joined or None
    return None


def _read_rows(path: Path) -> tuple[list[str], list[dict[str, Any]]]:
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text())
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("records", [])
        else:
            rows = []
        # Keep only dict rows (a stray scalar/list entry shouldn't break the load).
        rows = [r for r in rows[:_ROW_LIMIT] if isinstance(r, dict)]
        columns = list(rows[0].keys()) if rows else []
        return columns, rows
    df = pd.read_csv(path, dtype=str, nrows=_ROW_LIMIT).fillna("")
    return list(df.columns), df.to_dict("records")


def load_file(graph: CivicGraph, key: str, path: Path) -> int:
    kind = KIND_BY_KEY.get(key, key)
    columns, rows = _read_rows(path)
    if not rows:
        return 0
    plan = _resolve_plan(columns, kind)
    added = 0
    for i, row in enumerate(rows):
        address = _address(row, plan)
        if not address:
            continue
        record_id = str(row.get(plan["id_col"], f"{key}-{i}")) if plan["id_col"] else f"{key}-{i}"
        attrs: dict[str, Any] = {"dataset": key}
        if plan["state_col"]:
            attrs[plan["state_attr"]] = row.get(plan["state_col"])
        if plan["date_col"]:
            date_val = str(row.get(plan["date_col"], "")).strip()
            if date_val:
                attrs["date"] = date_val
        graph.add_record(kind, record_id, address, lat=_coord(row, plan["lat_col"]),
                         lng=_coord(row, plan["lng_col"]), **attrs)
        added += 1
    return added


def _coord(row: dict[str, Any], col: str | None) -> float | None:
    """Parse a lat/lng cell, swallowing missing/blank/malformed values."""
    if not col:
        return None
    raw = row.get(col)
    if raw is None:
        return None
    try:
        text = str(raw).strip()
        if not text:
            return None
        return float(text)
    except (TypeError, ValueError):
        return None


def load_into_graph(graph: CivicGraph, data_dir: Path | None = None) -> dict[str, int]:
    """Load every registered dataset found in data_dir. Returns rows-added per key."""
    data_dir = data_dir or settings.data_dir
    summary: dict[str, int] = {}
    if not data_dir.exists():
        return summary
    for key in REGISTRY:
        count = 0
        for path in sorted([*data_dir.glob(f"{key}__*.csv"), *data_dir.glob(f"{key}__*.json")]):
            try:
                count += load_file(graph, key, path)
            except Exception:
                # A single malformed/unreadable file must not abort the whole load
                # (offline-safe boundary): skip it and keep ingesting the rest.
                continue
        if count:
            summary[key] = count
    return summary
