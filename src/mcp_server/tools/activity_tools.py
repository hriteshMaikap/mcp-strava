"""MCP tools: activity data retrieval.

Recommended call sequence for any analysis task:
  1. list_activities   — narrow to relevant IDs (cheap, summary data only)
  2. get_activity_detail / get_activity_details_batch — fetch full data for
     only the IDs you need
  3. get_activity_laps / get_activity_zones — lap or zone breakdowns

Every parameter is annotated in the docstring as:
  [API]      → forwarded directly to the Strava HTTP request
  [abstract] → applied client-side after the API response
"""

from __future__ import annotations

import time
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.auth import require_auth
from mcp_server.models.enums import SortField, SortOrder, SportType
from mcp_server.services import activity_service


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @require_auth
    def list_activities(
        # --- time window ---
        days_back: int | None = None,
        after_date: str | None = None,
        before_date: str | None = None,
        after_epoch: int | None = None,
        before_epoch: int | None = None,
        # --- native API pagination ---
        page: int = 1,
        per_page: int = 30,
        # --- client-side filters ---
        sport_types: list[str] | None = None,
        name_contains: str | None = None,
        min_distance_km: float | None = None,
        max_distance_km: float | None = None,
        min_elevation_gain: float | None = None,
        has_heartrate: bool | None = None,
        # --- client-side sort ---
        sort_by: str = "start_date",
        sort_order: str = "desc",
    ) -> list[dict[str, Any]]:
        """
        List Strava activities with combined API and client-side filtering.

        Use this tool FIRST to get a filtered list of activity IDs before
        calling detail endpoints. Returns lightweight summaries — not full data.

        TIME WINDOW (use one approach):
          days_back    [abstract] Convenience: last N days, e.g. 90 for 3 months.
                                  Computed to an epoch before the API call.
          after_date   [abstract] ISO 8601 date string, e.g. "2025-01-01" or
                                  "2025-01-01T00:00:00". Converted to epoch internally.
          before_date  [abstract] ISO 8601 upper bound date string.
          after_epoch  [API]      Unix timestamp lower bound. Sent directly to
                                  GET /athlete/activities ?after=
          before_epoch [API]      Unix timestamp upper bound. Sent directly to
                                  GET /athlete/activities ?before=

        PAGINATION (native API params):
          page         [API]      Page number (1-indexed). Default 1.
          per_page     [API]      Activities per page (1–200). Default 30.
                                  Set to 200 for broad scans, lower for quick checks.

        FILTERS (applied client-side after API response):
          sport_types  [abstract] Filter to specific sport types. Examples:
                                  ["Run"], ["Run","TrailRun"], ["Ride","GravelRide"].
                                  Valid values: Run, TrailRun, Ride, MountainBikeRide,
                                  GravelRide, VirtualRide, Walk, Hike, Swim,
                                  WeightTraining, Yoga, Workout, EBikeRide,
                                  EMountainBikeRide, Rowing, Kayaking, Tennis,
                                  Padel, Pickleball, and 40+ others.
          name_contains [abstract] Case-insensitive keyword match on activity name.
                                   E.g. "morning" finds "Morning Run", "early morning ride".
          min_distance_km [abstract] Minimum distance in kilometres.
          max_distance_km [abstract] Maximum distance in kilometres.
          min_elevation_gain [abstract] Minimum total elevation gain in metres.
          has_heartrate [abstract] True = only activities with HR data.
                                   False = only activities without HR data.
                                   None = no filter (default).

        SORT (client-side):
          sort_by      [abstract] Field to sort by. Options:
                                  start_date | distance | moving_time |
                                  total_elevation_gain | name | average_speed
          sort_order   [abstract] "asc" or "desc" (default "desc").

        Returns:
            List of activity summaries. Each dict includes:
            id, name, sport_type, start_date_local, distance_km,
            moving_time, moving_time_hms, total_elevation_gain,
            pace_min_per_km, pace_formatted, average_heartrate,
            average_watts, kudos_count, gear_id, device_name, pr_count.

        Example — last 3 months of runs sorted by pace:
            list_activities(days_back=90, sport_types=["Run"],
                            sort_by="average_speed", sort_order="asc")
        """
        # --- resolve time window to epoch ints ---
        resolved_after  = after_epoch
        resolved_before = before_epoch

        if days_back is not None:
            resolved_after = int(time.time()) - (days_back * 86400)

        if after_date is not None and resolved_after is None:
            resolved_after = activity_service.iso_to_epoch(after_date)

        if before_date is not None and resolved_before is None:
            resolved_before = activity_service.iso_to_epoch(before_date)

        # --- resolve sport types ---
        resolved_sport_types: list[SportType] | None = None
        if sport_types:
            resolved_sport_types = [SportType(st) for st in sport_types]

        return activity_service.list_activities(
            before=resolved_before,
            after=resolved_after,
            page=page,
            per_page=per_page,
            sport_types=resolved_sport_types,
            name_contains=name_contains,
            min_distance_m=(min_distance_km * 1000.0) if min_distance_km is not None else None,
            max_distance_m=(max_distance_km * 1000.0) if max_distance_km is not None else None,
            min_elevation_gain=min_elevation_gain,
            has_heartrate=has_heartrate,
            sort_by=SortField(sort_by),
            sort_order=SortOrder(sort_order),
        )

    @mcp.tool()
    @require_auth
    def get_activity_detail(
        activity_id: int,
        include_all_efforts: bool = False,
    ) -> dict[str, Any]:
        """
        Fetch full detail for a single activity.

        Use AFTER list_activities to identify the relevant ID.
        Heavier payload than list_activities — includes splits, laps,
        gear, calories, and description.

        Args:
            activity_id          [API] Strava activity ID (integer from list_activities).
            include_all_efforts  [API] When True, includes all segment efforts in the
                                       response. Sent as ?include_all_efforts=true to
                                       GET /activities/{id}.
                                       Only set True when you need segment-level data —
                                       it significantly increases response size.

        Returns:
            Full activity dict. Key fields beyond list_activities:
            - splits_metric: list of per-km splits, each with pace_min_per_km,
              pace_formatted, elevation_difference, pace_zone
            - laps: list of laps with pace_min_per_km, pace_formatted,
              average_cadence, average_watts, average_heartrate
            - description, calories, gear (name, brand, distance logged)
        """
        return activity_service.get_detail(activity_id, include_all_efforts)

    @mcp.tool()
    @require_auth
    def get_activity_details_batch(
        activity_ids: list[int],
        include_all_efforts: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Fetch full detail for a list of activity IDs.

        Use for cross-activity analysis (e.g. pace progression, training load
        comparisons). Always narrow the ID list first with list_activities —
        never call this with unfiltered IDs.

        Args:
            activity_ids         [API] List of Strava activity IDs. Processed
                                       sequentially to respect Strava rate limits.
                                       Recommended max: 50 per call.
            include_all_efforts  [API] Include segment efforts for each activity.
                                       See get_activity_detail for guidance.

        Returns:
            List of full activity dicts, same structure as get_activity_detail,
            in the same order as activity_ids.

        Example — first-km pace for last 10 runs:
            ids = [a["id"] for a in list_activities(days_back=60,
                   sport_types=["Run"], per_page=10)]
            get_activity_details_batch(ids)
        """
        return activity_service.get_multiple_details(activity_ids, include_all_efforts)

    @mcp.tool()
    @require_auth
    def get_activity_laps(
        activity_id: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch lap-by-lap breakdown for an activity.

        Lap data is richer than splits_metric in get_activity_detail:
        includes heartrate, cadence, watts per lap.

        Args:
            activity_id  [API] Strava activity ID. Sent to GET /activities/{id}/laps.

        Returns:
            List of lap dicts. Each includes:
            - lap_index, name, distance (m), moving_time (s), elapsed_time (s)
            - pace_min_per_km, pace_formatted (derived — not from API)
            - average_speed (m/s), max_speed (m/s)
            - total_elevation_gain (m)
            - average_cadence, average_watts, device_watts
            - average_heartrate, max_heartrate
            - start_date_local (ISO string)

        Best for: interval analysis, negative/positive split detection,
        comparing specific laps across sessions.
        """
        return activity_service.get_laps(activity_id)

    @mcp.tool()
    @require_auth
    def get_activity_zones(
        activity_id: int,
    ) -> list[dict[str, Any]]:
        """
        Fetch heart rate and power zone distribution for an activity.

        Note: This is a Strava Summit (subscription) feature. Non-Summit
        accounts will receive an error response from the API.

        Args:
            activity_id  [API] Strava activity ID. Sent to GET /activities/{id}/zones.

        Returns:
            List of zone objects. Each includes:
            - type: "heartrate" or "power"
            - distribution_buckets: list of {min, max, time} — seconds per zone
            - sensor_based: whether zones use actual sensor data
            - custom_zones: whether athlete has set custom thresholds
            - score, points (Strava suffer score components)
        """
        return activity_service.get_zones(activity_id)