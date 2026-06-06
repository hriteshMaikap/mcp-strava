"""MCP tools: segment discovery and effort tracking.

All params annotated as [API] or [abstract] in docstrings.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from strava_mcp.auth import require_auth
from strava_mcp.models.enums import SegmentActivityType
from strava_mcp.services import segment_service


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @require_auth
    def get_starred_segments(
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """
        List the authenticated athlete's starred segments.

        Args:
            page      [API] Page number (1-indexed). Default 1.
                            Sent to GET /segments/starred ?page=
            per_page  [API] Results per page (1–200). Default 30.
                            Sent to GET /segments/starred ?per_page=

        Returns:
            List of segment summary dicts. Each includes:
            id, name, activity_type, distance (m), average_grade (%),
            maximum_grade (%), elevation_high (m), elevation_low (m),
            climb_category (0=uncat … 5=HC), city, country,
            effort_count, athlete_count, star_count,
            athlete_pr_effort (pr_elapsed_time, pr_date, effort_count).
        """
        return segment_service.get_starred_segments(page, per_page)

    @mcp.tool()
    @require_auth
    def get_segment(
        segment_id: int,
    ) -> dict[str, Any]:
        """
        Fetch full detail for a Strava segment.

        Args:
            segment_id  [API] Strava segment ID (integer).
                              Sent to GET /segments/{id}.
                              Find IDs from get_starred_segments,
                              get_activity_detail segment_efforts, or
                              explore_segments.

        Returns:
            Full segment dict including:
            name, distance (m), average_grade (%), maximum_grade (%),
            elevation_high/low (m), climb_category, city, state, country,
            effort_count (all athletes), athlete_count (unique athletes),
            star_count, athlete_pr_effort (your best time + date).
        """
        return segment_service.get_segment(segment_id)

    @mcp.tool()
    @require_auth
    def get_segment_efforts(
        segment_id: int,
        start_date_local: str | None = None,
        end_date_local: str | None = None,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """
        Fetch the authenticated athlete's efforts on a specific segment.

        Use to track personal progression on a favourite climb or sprint
        over time, or to check current PR rank.

        Args:
            segment_id        [API] Strava segment ID (required).
                                    Sent to GET /segment_efforts ?segment_id=
            start_date_local  [API] ISO 8601 lower bound for effort date,
                                    e.g. "2025-01-01T00:00:00Z".
                                    Sent as ?start_date_local= to filter efforts.
                                    Omit to include all history.
            end_date_local    [API] ISO 8601 upper bound.
                                    Sent as ?end_date_local=.
                                    Omit to include up to today.
            per_page          [API] Max results to return (1–200). Default 30.
                                    Sent as ?per_page=.

        Returns:
            List of effort dicts, ordered newest first. Each includes:
            id, name, elapsed_time (s), moving_time (s),
            start_date_local (ISO string), distance (m),
            pace_min_per_km (derived — not from API),
            average_watts, average_heartrate,
            kom_rank (null if outside top 10), pr_rank (1–3 or null).
        """
        return segment_service.get_segment_efforts(
            segment_id, start_date_local, end_date_local, per_page
        )

    @mcp.tool()
    @require_auth
    def explore_segments(
        sw_lat: float,
        sw_lng: float,
        ne_lat: float,
        ne_lng: float,
        activity_type: str = "running",
        min_climb_category: int | None = None,
        max_climb_category: int | None = None,
    ) -> dict[str, Any]:
        """
        Discover Strava segments within a geographic bounding box.

        Returns the top 10 segments matching the query.

        Args:
            sw_lat              [API] South-west corner latitude of bounding box.
                                      Combined into ?bounds=sw_lat,sw_lng,ne_lat,ne_lng
                                      for GET /segments/explore.
            sw_lng              [API] South-west corner longitude.
            ne_lat              [API] North-east corner latitude.
            ne_lng              [API] North-east corner longitude.
            activity_type       [API] "running" or "riding". Default "running".
                                      Sent as ?activity_type=.
            min_climb_category  [API] Minimum climb category filter (0–5).
                                      0 = uncategorised, 5 = Hors catégorie.
                                      Sent as ?min_cat=. Omit for no lower bound.
            max_climb_category  [API] Maximum climb category filter (0–5).
                                      Sent as ?max_cat=. Omit for no upper bound.

        Returns:
            Dict with "segments" list. Each segment includes:
            id, name, climb_category, climb_category_desc (NC/4/3/2/1/HC),
            avg_grade (%), distance (m), elev_difference (m),
            start_latlng, end_latlng, points (encoded polyline).

        Example — find HC climbs near a location:
            explore_segments(sw_lat=45.8, sw_lng=6.8, ne_lat=46.0, ne_lng=7.1,
                             activity_type="riding", min_climb_category=5)
        """
        return segment_service.explore_segments(
            bounds=[sw_lat, sw_lng, ne_lat, ne_lng],
            activity_type=SegmentActivityType(activity_type),
            min_cat=min_climb_category,
            max_cat=max_climb_category,
        )

    @mcp.tool()
    @require_auth
    def star_segment(
        segment_id: int,
        starred: bool,
    ) -> dict[str, Any]:
        """
        Star or unstar a segment for the authenticated athlete.

        Requires profile scope.

        Args:
            segment_id  [API] Strava segment ID.
                              Sent to PUT /segments/{id}/starred.
            starred     [API] True to star the segment, False to unstar.
                              Sent as form data `starred=true|false`.

        Returns:
            Updated segment detail dict (same as get_segment).
        """
        return segment_service.star_segment(segment_id, starred)