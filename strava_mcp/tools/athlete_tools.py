"""MCP tools: athlete profile, stats, zones, and gear.

All params annotated as [API] or [abstract] in docstrings.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from strava_mcp.auth import require_auth
from strava_mcp.services import athlete_service


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @require_auth
    def get_athlete_profile() -> dict[str, Any]:
        """
        Fetch the authenticated athlete's profile.

        No parameters — fetches the currently authenticated user.
        GET /athlete requires read or profile:read_all scope.

        Returns:
            id, username, firstname, lastname, city, country, sex,
            measurement_preference (feet | meters), weight (kg),
            ftp (functional threshold power), premium/summit status,
            bikes (list with id, name, distance), shoes (same structure),
            follower_count, friend_count.

        Typical use: check athlete weight, FTP, preferred gear, or
        measurement system before processing data.
        """
        return athlete_service.get_profile()

    @mcp.tool()
    @require_auth
    def get_athlete_stats(
        athlete_id: int | None = None,
    ) -> dict[str, Any]:
        """
        Fetch rolled-up activity statistics for the authenticated athlete.

        Args:
            athlete_id  [API]      Strava athlete ID. Sent to
                                   GET /athletes/{id}/stats.
                        [abstract] When None (default), the ID is read from
                                   the saved token — no extra API call needed.
                                   Only provide if fetching another athlete's
                                   public stats.

        Returns:
            Dict with three time windows × three sport types = 9 total groups,
            plus two all-time records:

            Time windows:
              recent_*_totals  — last 4 weeks
              ytd_*_totals     — year to date
              all_*_totals     — all time

            Sport types per window:
              *_ride_totals, *_run_totals, *_swim_totals

            Each totals object:
              count, distance (m), moving_time (s), elapsed_time (s),
              elevation_gain (m), achievement_count

            All-time records:
              biggest_ride_distance (m)
              biggest_climb_elevation_gain (m)

        Note: only includes activities with visibility set to "Everyone".
        """
        return athlete_service.get_stats(athlete_id)

    @mcp.tool()
    @require_auth
    def get_athlete_zones() -> dict[str, Any]:
        """
        Fetch the authenticated athlete's configured training zones.

        GET /athlete/zones — requires profile:read_all scope.

        Returns:
            Dict with two zone types:

            heart_rate:
              custom_zones (bool) — whether athlete set custom HR zones
              zones: list of {min, max} bpm boundaries

            power:
              zones: list of {min, max} watt boundaries

        Use before processing stream data so zone-time computations use
        the athlete's actual thresholds, not generic defaults.
        """
        return athlete_service.get_zones()

    @mcp.tool()
    @require_auth
    def get_gear_detail(
        gear_id: str,
    ) -> dict[str, Any]:
        """
        Fetch detail for a specific piece of gear (bike or shoe).

        Args:
            gear_id  [API] Strava gear ID string. Examples:
                           "b12345678" — bike IDs start with "b"
                           "g12345678" — shoe IDs start with "g"
                           Find IDs in activity.gear_id or athlete profile
                           bikes/shoes lists.
                           Sent to GET /gear/{id}.

        Returns:
            id, name, primary (bool), distance (total metres logged),
            brand_name, model_name, frame_type (bikes only), description.

        Typical use: enrich activity data with gear name, brand, and
        total mileage when gear_id appears on an activity.
        """
        return athlete_service.get_gear(gear_id)

    @mcp.tool()
    @require_auth
    def get_athlete_clubs(
        page: int = 1,
        per_page: int = 30,
    ) -> list[dict[str, Any]]:
        """
        List clubs the authenticated athlete belongs to.

        Args:
            page      [API] Page number (1-indexed). Default 1.
                            Sent to GET /athlete/clubs ?page=
            per_page  [API] Results per page (1–200). Default 30.
                            Sent to GET /athlete/clubs ?per_page=

        Returns:
            List of club summary dicts. Each includes:
            id, name, sport_type, city, country, member_count,
            private (bool), featured (bool), verified (bool), url.
        """
        return athlete_service.get_clubs(page, per_page)