"""Segment service."""

from __future__ import annotations

from typing import Any

from mcp_server.api import endpoints, get, put
from mcp_server.models.enums import SegmentActivityType

def get_starred_segments(page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
    """List the authenticated athlete's starred segments."""
    return get(
        endpoints.starred_segments(),
        params={"page": page, "per_page": per_page}
    )

def get_segment(segment_id: int) -> dict[str, Any]:
    """Fetch full detail for a Strava segment."""
    return get(endpoints.segment(segment_id))

def get_segment_efforts(
    segment_id: int,
    start_date_local: str | None = None,
    end_date_local: str | None = None,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """Fetch the authenticated athlete's efforts on a specific segment."""
    return get(
        endpoints.segment_efforts(),
        params={
            "segment_id": segment_id,
            "start_date_local": start_date_local,
            "end_date_local": end_date_local,
            "per_page": per_page,
        }
    )

def explore_segments(
    bounds: list[float],
    activity_type: SegmentActivityType,
    min_cat: int | None = None,
    max_cat: int | None = None,
) -> dict[str, Any]:
    """Discover Strava segments within a geographic bounding box."""
    bounds_str = ",".join(str(b) for b in bounds)
    return get(
        endpoints.explore_segments(),
        params={
            "bounds": bounds_str,
            "activity_type": activity_type.value,
            "min_cat": min_cat,
            "max_cat": max_cat,
        }
    )

def star_segment(segment_id: int, starred: bool) -> dict[str, Any]:
    """Star or unstar a segment for the authenticated athlete."""
    # The API expects form data for this PUT request
    return put(
        endpoints.star_segment(segment_id),
        data={"starred": "true" if starred else "false"}
    )
