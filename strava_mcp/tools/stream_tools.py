"""MCP tools: activity stream analytics.

Stream tools expose PURPOSE-named functions rather than raw API keys.
The LLM calls get_pace_profile, get_hr_profile, etc. — not "give me
velocity_smooth and heartrate streams".

The one exception is get_raw_streams, which exposes the key list explicitly
for advanced / composite use cases.

All params annotated as [API] or [abstract] in docstrings.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from strava_mcp.auth import require_auth
from strava_mcp.models.enums import StreamKey
from strava_mcp.services import stream_service


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @require_auth
    def get_pace_profile(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Fetch the pace, distance, and elevation streams for an activity.

        Internally requests: time, distance, velocity_smooth, altitude.
        Use this for: per-km pace charts, elevation-pace correlation,
        pacing strategy analysis, identifying fade or negative splits.

        Args:
            activity_id  [API] Strava activity ID.
                               Sent to GET /activities/{id}/streams
                               with keys=time,distance,velocity_smooth,altitude.

        Returns:
            Dict keyed by stream type. Each stream has:
            - data: list of values at each GPS second
            - original_size: total data points
            - resolution: "low" | "medium" | "high"
            - series_type: "distance" | "time"

            velocity_smooth.data is in m/s. Convert: pace_min_km = 1000/(v*60)
        """
        return stream_service.get_pace_profile(activity_id)

    @mcp.tool()
    @require_auth
    def get_hr_profile(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Fetch heart rate, distance, time, and velocity streams for an activity.

        Internally requests: time, distance, heartrate, velocity_smooth.
        Use this for: HR drift analysis, aerobic decoupling (HR vs pace over time),
        HR-zone time-in-zone computation, cardiac efficiency tracking.

        Args:
            activity_id  [API] Strava activity ID.
                               Sent to GET /activities/{id}/streams
                               with keys=time,distance,heartrate,velocity_smooth.

        Returns:
            Dict keyed by stream type. heartrate.data is in bpm.
            If the activity has no HR sensor, heartrate stream will be absent.
        """
        return stream_service.get_hr_profile(activity_id)

    @mcp.tool()
    @require_auth
    def get_power_profile(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Fetch power, cadence, distance, time, and velocity streams.

        Internally requests: time, distance, watts, cadence, velocity_smooth.
        Use this for: power curve (MMP) analysis, normalised power computation,
        cadence distribution, power-to-speed efficiency.

        Only returns meaningful data for activities with a power meter.
        Check activity.device_watts == True before calling.

        Args:
            activity_id  [API] Strava activity ID.
                               Sent to GET /activities/{id}/streams
                               with keys=time,distance,watts,cadence,velocity_smooth.

        Returns:
            Dict keyed by stream type. watts.data is in W, cadence.data in rpm.
        """
        return stream_service.get_power_profile(activity_id)

    @mcp.tool()
    @require_auth
    def get_gps_track(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Fetch GPS coordinates, distance, and altitude streams.

        Internally requests: latlng, distance, altitude.
        Use this for: map rendering, route display, GPS-based elevation profiling.

        Args:
            activity_id  [API] Strava activity ID.
                               Sent to GET /activities/{id}/streams
                               with keys=latlng,distance,altitude.

        Returns:
            Dict with:
            - latlng.data: list of [latitude, longitude] pairs
            - distance.data: cumulative metres at each GPS point
            - altitude.data: metres above sea level at each GPS point
        """
        return stream_service.get_gps_track(activity_id)

    @mcp.tool()
    @require_auth
    def analyse_distance_segment(
        activity_id: int,
        start_m: float = 0.0,
        end_m: float = 1000.0,
    ) -> dict[str, Any]:
        """
        Compute pace, HR, and elevation stats for any distance segment of an activity.

        This is a pure abstract tool — it has no direct Strava API equivalent.
        Internally fetches pace + HR streams and slices the requested window.

        Common use cases:
          First km:     start_m=0,    end_m=1000   (default)
          5–10 km:      start_m=5000, end_m=10000
          Last 2 km:    start_m=total_distance-2000, end_m=total_distance
          Middle third: compute from total distance

        For first-km progression across multiple runs:
          → Call list_activities to get run IDs
          → Call this function for each ID with start_m=0, end_m=1000
          → Compare pace_min_per_km across dates

        Args:
            activity_id  [API]      Strava activity ID. Used to fetch streams from
                                    GET /activities/{id}/streams.
            start_m      [abstract] Distance marker where the segment starts (metres
                                    into the activity). Default 0 (activity start).
            end_m        [abstract] Distance marker where the segment ends (metres
                                    into the activity). Default 1000 (first km).
                                    If the activity is shorter than end_m, the last
                                    available data point is used.

        Returns:
            start_m, end_m, covered_m — actual distances from stream data
            elapsed_time_s            — seconds to cover the segment
            pace_min_per_km           — float (e.g. 5.32)
            pace_formatted            — string (e.g. "5:19 /km")
            avg_velocity_ms           — raw average m/s
            avg_smooth_velocity_ms    — smoothed average m/s
            avg_heartrate             — bpm if HR sensor present, else null
            elevation_gain_m          — metres gained within the segment
        """
        return stream_service.analyse_distance_segment(activity_id, start_m, end_m)

    @mcp.tool()
    @require_auth
    def get_raw_streams(
        activity_id: int,
        stream_keys: list[str],
    ) -> dict[str, Any]:
        """
        Fetch specific stream types by name — for advanced or composite use cases.

        Prefer the named analysis tools (get_pace_profile, get_hr_profile, etc.)
        over this function. Use get_raw_streams only when you need a combination
        of streams not covered by the named tools.

        Args:
            activity_id   [API] Strava activity ID.
            stream_keys   [API] List of stream type names to fetch. These map
                                directly to the Strava API `keys` query param.
                                Valid values:
                                  time            — seconds from activity start
                                  distance        — cumulative metres
                                  latlng          — [[lat, lng], ...] pairs
                                  altitude        — metres above sea level
                                  velocity_smooth — smoothed m/s
                                  heartrate       — bpm (requires HR sensor)
                                  cadence         — rpm (run: steps/min ÷ 2)
                                  watts           — power (requires power meter)
                                  temp            — celsius (requires temp sensor)
                                  moving          — boolean, true when moving
                                  grade_smooth    — smoothed gradient percent

        Returns:
            Dict keyed by stream type. Only requested + available keys appear.
        """
        keys = [StreamKey(k) for k in stream_keys]
        return stream_service.get_streams(activity_id, keys)

    @mcp.tool()
    @require_auth
    def get_segment_effort_streams(
        effort_id: int,
        stream_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Fetch streams for a specific segment effort.

        Use after get_segment_efforts to drill into the raw time-series
        for one particular segment effort (e.g. a PR attempt on a climb).

        Args:
            effort_id    [API]      Strava segment effort ID (from get_segment_efforts).
                                    Sent to GET /segment_efforts/{id}/streams.
            stream_keys  [API]      Stream types to fetch. Defaults to pace preset
                                    (time, distance, velocity_smooth, altitude).
                                    Same valid values as get_raw_streams.

        Returns:
            Dict keyed by stream type, same structure as other stream tools.
        """
        keys: list[StreamKey] | None = None
        if stream_keys:
            keys = [StreamKey(k) for k in stream_keys]
        return stream_service.analyse_segment_effort_streams(effort_id, keys)