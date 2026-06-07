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

from mcp_server.api import endpoints, get
from mcp_server.distillation import activity as distill
from mcp_server.models.enums import SortField, SortOrder, SportType
from mcp_server.models.responses import DetailedActivity, Lap, SplitMetric, SummaryActivity


# ---------------------------------------------------------------------------
# List activities
# ---------------------------------------------------------------------------

_API_BATCH_SIZE = 50   # activities fetched per Strava API page when auto-paginating
_MAX_SCAN_TOTAL = 500  # hard cap: never scan more than this many raw activities

def _has_client_filters(
    sport_types: list[SportType] | None,
    name_contains: str | None,
    min_distance_m: float | None,
    max_distance_m: float | None,
    min_elevation_gain: float | None,
    has_heartrate: bool | None,
) -> bool:
    """Return True if any client-side filter is active."""
    return any([
        sport_types,
        name_contains is not None,
        min_distance_m is not None,
        max_distance_m is not None,
        min_elevation_gain is not None,
        has_heartrate is not None,
    ])


def _apply_filters(
    activities: list,
    sport_types: list[SportType] | None,
    name_contains: str | None,
    min_distance_m: float | None,
    max_distance_m: float | None,
    min_elevation_gain: float | None,
    has_heartrate: bool | None,
) -> list:
    """Apply all client-side filters to a list of SummaryActivity objects."""
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

    return activities


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
    Fetch activities, applying both native API filters and abstract client-side
    filters in sequence.

    When client-side filters are active (e.g. sport_types), the Strava API does
    not support them natively — it always returns all sport types. To ensure
    `per_page` matching results are returned, the service auto-paginates through
    the API (fetching _API_BATCH_SIZE raw activities at a time) until it has
    collected `per_page` matching results or exhausted all available data
    (capped at _MAX_SCAN_TOTAL raw activities to avoid excessive API usage).

    When no client-side filters are active, a single API page is fetched using
    the caller-supplied `page` and `per_page` directly (original behaviour).
    """
    use_autopaginate = _has_client_filters(
        sport_types, name_contains, min_distance_m, max_distance_m,
        min_elevation_gain, has_heartrate,
    )

    if not use_autopaginate:
        # Fast path: no client-side filters — single API call, exact page/per_page.
        raw: list[dict[str, Any]] = get(
            endpoints.activities_list(),
            params={"before": before, "after": after, "page": page, "per_page": per_page},
        )
        activities = [SummaryActivity.model_validate(a) for a in raw]
    else:
        # Auto-paginate: keep fetching until we have `per_page` matching results.
        collected: list = []
        scanned   = 0
        api_page  = 1

        while len(collected) < per_page and scanned < _MAX_SCAN_TOTAL:
            batch_size = min(_API_BATCH_SIZE, _MAX_SCAN_TOTAL - scanned)
            raw_batch: list[dict[str, Any]] = get(
                endpoints.activities_list(),
                params={
                    "before":   before,
                    "after":    after,
                    "page":     api_page,
                    "per_page": batch_size,
                },
            )

            if not raw_batch:
                break  # no more activities available

            scanned += len(raw_batch)
            batch = [SummaryActivity.model_validate(a) for a in raw_batch]
            matching = _apply_filters(
                batch, sport_types, name_contains,
                min_distance_m, max_distance_m, min_elevation_gain, has_heartrate,
            )
            collected.extend(matching)

            if len(raw_batch) < batch_size:
                break  # Strava returned fewer than requested → last page reached

            api_page += 1

        activities = collected[:per_page]

    # --- sort (client-side always) ---
    reverse = sort_order == SortOrder.DESC
    sort_attr = sort_by.value
    activities.sort(key=lambda a: getattr(a, sort_attr) or 0, reverse=reverse)

    return distill.distill_summaries([_serialize_summary(a) for a in activities])


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
    return distill.distill_detail(_serialize_detail(activity))


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
    return distill.distill_laps([_serialize_lap(Lap.model_validate(lap)) for lap in raw])


# ---------------------------------------------------------------------------
# Zones
# ---------------------------------------------------------------------------

def get_zones(activity_id: int) -> list[dict[str, Any]]:
    """Fetch HR / power zone distribution (Summit feature)."""
    return distill.distill_zones(get(endpoints.activity_zones(activity_id)))


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