"""Generic distillation utilities — recursive dict/list transformations.

These are composable primitives. Higher-level modules (athlete, activity,
streams) compose them into domain-specific pipelines via ``compact()``.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Atomic operations
# ---------------------------------------------------------------------------

def strip_nulls(obj: Any) -> Any:
    """Recursively remove keys with ``None`` values from nested dicts."""
    if isinstance(obj, dict):
        return {k: strip_nulls(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, list):
        return [strip_nulls(item) for item in obj]
    return obj


def strip_fields(obj: Any, fields: set[str]) -> Any:
    """Recursively remove specific field names from nested dicts."""
    if isinstance(obj, dict):
        return {k: strip_fields(v, fields) for k, v in obj.items() if k not in fields}
    if isinstance(obj, list):
        return [strip_fields(item, fields) for item in obj]
    return obj


def strip_false_booleans(obj: Any, fields: set[str]) -> Any:
    """Remove specific boolean fields *only when they are False*.

    Keeps the field when True (the interesting, non-default case).
    """
    if isinstance(obj, dict):
        return {
            k: strip_false_booleans(v, fields)
            for k, v in obj.items()
            if not (k in fields and v is False)
        }
    if isinstance(obj, list):
        return [strip_false_booleans(item, fields) for item in obj]
    return obj


def strip_empty(obj: Any) -> Any:
    """Remove empty strings, empty lists, and empty dicts (recursively)."""
    if isinstance(obj, dict):
        cleaned = {}
        for k, v in obj.items():
            v = strip_empty(v)
            if v != "" and v != [] and v != {}:
                cleaned[k] = v
        return cleaned
    if isinstance(obj, list):
        return [
            strip_empty(item)
            for item in obj
            if strip_empty(item) not in ("", [], {})
        ]
    return obj


def strip_zero_blocks(obj: dict[str, Any]) -> dict[str, Any]:
    """Remove top-level dict entries whose nested ``count`` field is 0.

    Designed for athlete stats — drops empty ride/swim totals for a
    runner-only athlete.
    """
    cleaned: dict[str, Any] = {}
    for k, v in obj.items():
        if isinstance(v, dict) and v.get("count", -1) == 0:
            continue  # skip entire zero-count block
        cleaned[k] = v
    return cleaned


# ---------------------------------------------------------------------------
# Composite pipeline
# ---------------------------------------------------------------------------

def compact(
    obj: Any,
    *,
    remove_fields: set[str] | None = None,
    noise_booleans: set[str] | None = None,
) -> Any:
    """Full compaction pipeline (order matters):

    1. Strip named fields        (polylines, resource_state, avatars…)
    2. Strip ``None`` values     (null HR when no strap, null watts…)
    3. Strip noise booleans      (trainer=False, commute=False…)
    4. Strip empty containers    (bio="", clubs=[]…)
    """
    result = obj
    if remove_fields:
        result = strip_fields(result, remove_fields)
    result = strip_nulls(result)
    if noise_booleans:
        result = strip_false_booleans(result, noise_booleans)
    result = strip_empty(result)
    return result
