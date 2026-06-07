"""Activity response distillation.

Strips polylines, null sensor fields, always-false booleans, and
redundant fields from activity summaries, details, laps, and zones.
"""

from __future__ import annotations

from typing import Any

from mcp_server.distillation.core import compact


# ---------------------------------------------------------------------------
# Field sets
# ---------------------------------------------------------------------------

# Fields to strip from every activity summary/detail
_ACTIVITY_STRIP: set[str] = {
    "resource_state",
    "map",               # summary_polyline — LLM cannot render or interpret
    "elapsed_time",      # nearly identical to moving_time for outdoor runs
    "start_date",        # UTC duplicate — start_date_local is more useful
    "timezone",          # redundant once start_date_local is present
    "average_speed",     # raw m/s — redundant with pace_min_per_km
    "max_speed",         # raw m/s — not interpretable without conversion
}

# Boolean fields that are almost always False — strip when False, keep when True
_NOISE_BOOLEANS: set[str] = {
    "trainer",
    "commute",
    "private",
}

# Additional fields to strip from laps
_LAP_STRIP: set[str] = {
    "resource_state",
    "start_date",        # UTC version, keep start_date_local
    "split",             # redundant with lap_index
}


# ---------------------------------------------------------------------------
# Distillation functions
# ---------------------------------------------------------------------------

def distill_summary(raw: dict[str, Any]) -> dict[str, Any]:
    """Distill a single activity summary from list_activities.

    Removes:
      - map (polyline the LLM can't interpret → biggest win per activity)
      - null sensor fields (no HR strap → null HR/watts/cadence)
      - elapsed_time, average_speed, max_speed (redundant with derived pace)
      - trainer/commute/private when False
      - comment_count when 0

    Keeps all derived fields: distance_km, pace_formatted, moving_time_hms.
    """
    result = compact(raw, remove_fields=_ACTIVITY_STRIP, noise_booleans=_NOISE_BOOLEANS)

    # Strip zero social counters (not analytically relevant)
    for field in ("comment_count", "kudos_count"):
        if result.get(field, -1) == 0:
            result.pop(field, None)

    return result


def distill_summaries(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distill a list of activity summaries (list_activities output)."""
    return [distill_summary(a) for a in activities]


def distill_detail(raw: dict[str, Any]) -> dict[str, Any]:
    """Distill a single detailed activity (get_activity_detail output).

    Same as summary stripping, plus:
      - Remove the empty final split (distance=0, artifact of Strava API)
      - Strip redundant fields from splits_metric
      - Strip resource_state from embedded laps
    """
    result = compact(raw, remove_fields=_ACTIVITY_STRIP, noise_booleans=_NOISE_BOOLEANS)

    # Strip zero social counters
    for field in ("comment_count", "kudos_count"):
        if result.get(field, -1) == 0:
            result.pop(field, None)

    # Clean up splits: remove empty trailing split and redundant fields
    if "splits_metric" in result:
        result["splits_metric"] = [
            _compact_split(s)
            for s in result["splits_metric"]
            if s.get("distance", 0) > 0  # drop empty final split
        ]

    # Clean up embedded laps
    if "laps" in result:
        result["laps"] = [_compact_lap(lap) for lap in result["laps"]]

    return result


def _compact_split(split: dict[str, Any]) -> dict[str, Any]:
    """Compact a single split_metric entry.

    Keeps: split, distance, elevation_difference, moving_time,
    pace_formatted, pace_zone.
    Removes: elapsed_time (≈ moving_time), average_speed (→ pace_formatted).
    """
    return compact(
        split,
        remove_fields={"elapsed_time", "average_speed", "resource_state"},
    )


def _compact_lap(lap: dict[str, Any]) -> dict[str, Any]:
    """Compact a single lap entry."""
    return compact(lap, remove_fields=_LAP_STRIP)


def distill_laps(laps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distill standalone lap list (get_activity_laps output)."""
    return [_compact_lap(lap) for lap in laps]


def distill_zones(raw: Any) -> Any:
    """Distill activity zone distribution — minimal cleanup."""
    if isinstance(raw, (dict, list)):
        return compact(raw, remove_fields={"resource_state"})
    return raw
