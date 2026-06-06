"""Activity service.

Bridges abstract tool parameters to Strava API calls.

Parameter routing:
  NATIVE TO API   → passed directly in the HTTP request params
  ABSTRACT (ours) → applied client-side after the API response

  Native (GET /athlete/activities):
    before, after, page, per_page

  Abstract (client-side):
    sport_types, name_contains, min_distance_m, max_distance_m,
    sort_by, sort_order, min_elevation_gain, has_heartrate
"""

from __future__ import annotations

import time
from typing import Any

from strava_mcp.api import endpoints, get
from strava_mcp.models.enums import SortField, SortOrder, SportType
from strava_mcp.models.responses import DetailedActivity, Lap, SplitMetric, SummaryActivity


# ---------------------------------------------------------------------------
# List activities
# ---------------------------------------------------------------------------

def list_activities(
    # ---- native Strava API params ----
    before: int | None = None,
    after: int | None = None,
    page: int = 1,
    per_page: int = 30,
    # ---- abstract params (client-side) ----
    sport_types: list[SportType] | None = None,
    name_contains: str | None = None,
    min_distance_m: float | None = None,
    max_distance_m: float | None = None,
    min_elevation_gain: float | None = None,
    has_heartrate: bool | None = None,
    sort_by: SortField = SortField.DATE,
    sort_order: SortOrder = SortOrder.DESC,
) -> list[dict[str, Any]]:
    """
    Fetch a page of activities, applying both native API filters and
    abstract client-side filters in sequence.
    """
    raw: list[dict[str, Any]] = get(
        endpoints.activities_list(),
        params={"before": before, "after": after, "page": page, "per_page": per_page},
    )

    activities = [SummaryActivity.model_validate(a) for a in raw]

    # --- client-side narrowing (order: cheap checks first) ---
    if sport_types:
        allowed = {st.value for st in sport_types}
        activities = [a for a in activities if a.sport_type in allowed]

    if name_contains:
        needle = name_contains.lower()
        activities = [a for a in activities if needle in a.name.lower()]

    if min_distance_m is not None:
        activities = [a for a in activities if a.distance >= min_distance_m]

    if max_distance_m is not None:
        activities = [a for a in activities if a.distance <= max_distance_m]

    if min_elevation_gain is not None:
        activities = [a for a in activities if a.total_elevation_gain >= min_elevation_gain]

    if has_heartrate is not None:
        activities = [a for a in activities if a.has_heartrate == has_heartrate]

    # --- sort (client-side always) ---
    reverse = sort_order == SortOrder.DESC
    sort_attr = sort_by.value
    activities.sort(key=lambda a: getattr(a, sort_attr) or 0, reverse=reverse)

    return [_serialize_summary(a) for a in activities]


# ---------------------------------------------------------------------------
# Single activity
# ---------------------------------------------------------------------------

def get_detail(
    activity_id: int,
    # native param
    include_all_efforts: bool = False,
) -> dict[str, Any]:
    """Fetch the full DetailedActivity. Adds derived pace fields."""
    raw = get(
        endpoints.activity_detail(activity_id),
        params={"include_all_efforts": str(include_all_efforts).lower()},
    )
    activity = DetailedActivity.model_validate(raw)
    return _serialize_detail(activity)


def get_multiple_details(
    activity_ids: list[int],
    include_all_efforts: bool = False,
) -> list[dict[str, Any]]:
    """Batch detail fetch — sequential to respect rate limits."""
    return [get_detail(aid, include_all_efforts) for aid in activity_ids]


# ---------------------------------------------------------------------------
# Laps
# ---------------------------------------------------------------------------

def get_laps(activity_id: int) -> list[dict[str, Any]]:
    """Fetch laps and enrich each with derived pace."""
    raw: list[dict[str, Any]] = get(endpoints.activity_laps(activity_id))
    return [_serialize_lap(Lap.model_validate(lap)) for lap in raw]


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

def get_zones(activity_id: int) -> list[dict[str, Any]]:
    """Fetch HR / power zone distribution (Summit feature)."""
    return get(endpoints.activity_zones(activity_id))


# ---------------------------------------------------------------------------
# Utility: epoch helpers
# ---------------------------------------------------------------------------

def days_to_epoch(days_back: int) -> int:
    """Convert N days back to a Unix epoch timestamp."""
    return int(time.time()) - (days_back * 86400)


def iso_to_epoch(iso_str: str) -> int:
    """Parse an ISO 8601 string to a Unix epoch int."""
    from datetime import datetime, timezone
    dt = datetime.fromisoformat(iso_str)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


# ---------------------------------------------------------------------------
# Serialisers — keep derived field computation here, not in tools
# ---------------------------------------------------------------------------

def _serialize_summary(a: SummaryActivity) -> dict[str, Any]:
    d = a.model_dump()
    d["distance_km"]       = round(a.distance_km, 3)
    d["pace_min_per_km"]   = round(a.pace_min_per_km, 2) if a.pace_min_per_km else None
    d["pace_formatted"]    = a.pace_formatted
    d["moving_time_hms"]   = a.moving_time_formatted
    d["start_date_local"]  = a.start_date_local.isoformat()
    d["start_date"]        = a.start_date.isoformat()
    return d


def _serialize_detail(a: DetailedActivity) -> dict[str, Any]:
    d = _serialize_summary(a)
    d["splits_metric"] = [
        {
            **s.model_dump(),
            "pace_min_per_km": round(s.pace_min_per_km, 2) if s.pace_min_per_km else None,
            "pace_formatted":  s.pace_formatted,
        }
        for s in a.splits_metric
    ]
    d["laps"] = [_serialize_lap(lap) for lap in a.laps]
    return d


def _serialize_lap(lap: Lap) -> dict[str, Any]:
    d = lap.model_dump()
    d["pace_min_per_km"]  = round(lap.pace_min_per_km, 2) if lap.pace_min_per_km else None
    d["pace_formatted"]   = lap.pace_formatted
    d["start_date_local"] = lap.start_date_local.isoformat()
    d["start_date"]       = lap.start_date.isoformat()
    return d