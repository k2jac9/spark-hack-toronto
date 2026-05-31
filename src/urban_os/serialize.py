"""JSON-boundary helpers for the Urban-OS API (ADR-0022 extraction; ADR-0006 rules).

Every numeric payload the API returns is coerced from numpy to native Python here
— numpy scalars are NOT JSON-serializable and would otherwise leak across the
boundary — and non-finite floats (NaN/±inf, not legal JSON) are clamped to 0.0.
Pure functions, no urban_os imports, so this is a safe leaf module.
"""
from __future__ import annotations

import math
import numbers

import numpy as np


def r(x: float, places: int = 3) -> float:
    """Round to keep the payload small; always returns a native float.

    Coerces numpy scalars to a native ``float`` (numpy scalars are NOT
    JSON-serializable — this is the boundary that guarantees no numpy leaks into
    a response). Non-finite values (NaN/±inf) are clamped to ``0.0`` so a
    degenerate field can never produce an invalid JSON token.
    """
    v = float(x)
    if not math.isfinite(v):
        return 0.0
    return round(v, places)


def native(obj):
    """Recursively coerce a (possibly numpy-laced) structure to native Python.

    ``optimize.OptResult.to_dict()`` carries lever values straight off an
    ``np.arange`` grid, so its ``params``/``trials`` hold ``numpy.float64``
    scalars. Those happen to JSON-encode today (numpy floats subclass ``float``)
    but still violate the "no numpy leakage at the boundary" invariant and would
    break a stricter encoder. Non-finite floats are clamped to 0.0 to keep the
    JSON strictly valid.
    """
    if isinstance(obj, dict):
        return {k: native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [native(v) for v in obj]
    if isinstance(obj, bool):  # bool before int/float (bool is an int subclass)
        return bool(obj)
    if isinstance(obj, np.bool_):  # numpy bool is NOT a python bool/Integral
        return bool(obj)
    if isinstance(obj, numbers.Integral):
        return int(obj)
    if isinstance(obj, numbers.Real):
        f = float(obj)
        return f if math.isfinite(f) else 0.0
    return obj  # str / None / already-native pass through unchanged


def peak_dict(result) -> dict:
    """A run's peak-congestion summary as a native dict (node/label/congestion/t)."""
    p = result.peak_congestion()
    return {
        "node": p["node"],
        "label": p["label"],
        "congestion": r(p["congestion"]),
        "t": r(p["t"], 1),
    }
