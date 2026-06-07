"""MCP tools: activity stream analytics.

Stream tools expose PURPOSE-named functions rather than raw API keys.
The LLM calls get_pace_profile, get_hr_profile, etc. — not "give me
velocity_smooth and heartrate streams".

IMPORTANT — Output format:
  All stream tools return DISTILLED summaries, NOT raw per-second arrays.
  A 12km run that would produce ~57,000 tokens of raw data is distilled
  into ~500 tokens of per-km aggregates before reaching the LLM.
  Never expect raw {data: [...]} arrays from these tools.

The one exception is get_raw_streams, which exposes the key list explicitly
for advanced / composite use cases.

All params annotated as [API] or [abstract] in docstrings.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.auth import require_auth
from mcp_server.models.enums import StreamKey
from mcp_server.services import stream_service


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    @require_auth
    def get_pace_profile(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Analyse pace, elevation, and pacing strategy for an activity.

        Returns pre-computed per-km splits and a pacing summary — NOT
        raw per-second arrays. This is the primary tool for pace analysis,
        split detection, and pacing strategy review.

        Use this when the user asks about:
          · Negative or positive splits ("did I run faster in the second half?")
          · Pace per km / mile breakdown
          · Fastest or slowest kilometre in an activity
          · Pacing consistency or fade (pace variability)
          · How elevation affected pace on a specific run

        Prefer get_activity_detail instead when:
          · You only need basic per-km splits without elevation correlation
          · The user's question can be answered from splits_metric alone
          · You are comparing splits across multiple activities (use batch)

        Args:
            activity_id  [API] Strava activity ID (integer from list_activities).
                               Internally fetches time, distance, velocity_smooth,
                               altitude streams from GET /activities/{id}/streams.

        Returns:
            data_points_raw: int — raw GPS data points captured (reference only)

            per_km: list of dicts, one per kilometre:
              · km            — kilometre number (1-indexed)
              · distance_m    — actual metres covered in this km segment
              · elapsed_s     — seconds to cover this km segment
              · pace          — pace string e.g. "6:27/km"
              · speed_ms      — average speed in m/s
              · smooth_speed_ms — smoothed average speed in m/s
              · elev_gain_m   — elevation gained in this km (metres)
              · elev_loss_m   — elevation lost in this km (metres)

            summary:
              · total_km, total_time_s, avg_pace
              · fastest_km: {km, pace} — the fastest kilometre
              · slowest_km: {km, pace} — the slowest kilometre
              · first_half_pace, second_half_pace — for split analysis
              · split_type: "negative" (second half faster) | "positive" (second half slower)
              · total_elev_gain_m, total_elev_loss_m
              · pace_variability_pct — coefficient of variation across km splits
        """
        return stream_service.get_pace_profile(activity_id)

    @mcp.tool()
    @require_auth
    def get_hr_profile(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Analyse heart rate trends, drift, and aerobic efficiency for an activity.

        Returns pre-computed per-km HR averages, overall HR statistics, and
        aerobic efficiency metrics — NOT raw per-second HR arrays.

        Use this when the user asks about:
          · Heart rate drift (HR rising over the activity at same pace = aerobic decoupling)
          · Average or max heart rate
          · Aerobic efficiency (how far per heartbeat)
          · HR-to-pace relationship across kilometres
          · Whether an effort was aerobic or anaerobic

        Prefer get_activity_detail instead when:
          · You only need the overall average_heartrate (already in the summary)
          · You are comparing average HR across multiple activities

        Requires: activity must have been recorded with a heart rate sensor.
        Check has_heartrate == true in list_activities before calling.
        If no HR sensor, the hr_summary block will be absent.

        Args:
            activity_id  [API] Strava activity ID (integer from list_activities).
                               Internally fetches time, distance, heartrate,
                               velocity_smooth streams from GET /activities/{id}/streams.

        Returns:
            data_points_raw: int — raw GPS data points captured (reference only)

            per_km: list of dicts, one per kilometre:
              · km, distance_m, elapsed_s, pace, speed_ms
              · avg_hr  — average bpm in this km segment
              · max_hr  — peak bpm in this km segment

            hr_summary (present only when HR sensor data exists):
              · avg_hr, max_hr, min_hr — overall activity HR stats
              · hr_drift_pct — % rise in avg HR from first half to second half
                               Positive = cardiac drift (harder to maintain pace)
                               Negative = cardiac improvement (warm-up effect)
              · first_half_avg_hr, second_half_avg_hr
              · metres_per_heartbeat — aerobic efficiency metric
                                       Higher = more distance per heartbeat = better fitness
        """
        return stream_service.get_hr_profile(activity_id)

    @mcp.tool()
    @require_auth
    def get_power_profile(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Analyse power output, cadence, and normalised power for an activity.

        Returns pre-computed per-km power and cadence averages, plus overall
        power metrics including Normalised Power — NOT raw per-second arrays.

        Use this when the user asks about:
          · Normalised Power (NP) or weighted average power
          · Average or peak power output
          · Cadence distribution or average cadence
          · Power-to-speed efficiency
          · Power analysis for a cycling or running-with-power activity

        Only returns meaningful data for activities recorded with a power meter.
        Check activity.device_watts == true in get_activity_detail before calling.

        Args:
            activity_id  [API] Strava activity ID (integer from list_activities).
                               Internally fetches time, distance, watts, cadence,
                               velocity_smooth streams from GET /activities/{id}/streams.

        Returns:
            data_points_raw: int — raw GPS data points captured (reference only)

            per_km: list of dicts, one per kilometre:
              · km, distance_m, elapsed_s, pace, speed_ms
              · avg_watts  — average power in this km segment (W)
              · max_watts  — peak power in this km segment (W)
              · avg_cadence — average cadence in this km segment (rpm)

            power_summary (present when power meter data exists):
              · avg_power_w    — activity average power (W)
              · max_power_w    — peak power (W)
              · normalised_power_w — Normalised Power (NP): 30s rolling average
                                     raised to 4th power, averaged, 4th root taken.
                                     Better than avg_power for variable-intensity efforts.

            cadence_summary (present when cadence data exists):
              · avg_cadence_rpm — average cadence excluding zeros (moving only)
              · max_cadence_rpm — peak cadence
        """
        return stream_service.get_power_profile(activity_id)

    @mcp.tool()
    @require_auth
    def get_gps_track(
        activity_id: int,
    ) -> dict[str, Any]:
        """
        Fetch the geographic footprint and elevation profile of an activity.

        Returns a distilled geographic summary — bounding box, start/end
        coordinates, and elevation stats — NOT the raw array of thousands
        of lat/lng pairs. The encoded polyline for route display already
        exists in the activity summary from list_activities/get_activity_detail.

        Use this when the user asks about:
          · Where an activity took place (city, region, general area)
          · Start and end location of a run or ride
          · Elevation gain or loss (total, min, max altitude)
          · Whether an activity was a loop (start ≈ end coordinates)

        Prefer get_activity_detail instead when:
          · You only need total_elevation_gain (already in the activity summary)
          · You need the encoded polyline for a map (use summary_polyline if available)

        Args:
            activity_id  [API] Strava activity ID (integer from list_activities).
                               Internally fetches latlng, distance, altitude
                               streams from GET /activities/{id}/streams.

        Returns:
            data_points_raw: int — original GPS data points (reference only)

            bounding_box:
              · sw: [lat, lng] — south-west corner of the route bounding box
              · ne: [lat, lng] — north-east corner of the route bounding box

            start_latlng: [lat, lng] — GPS coordinates where the activity started
            end_latlng:   [lat, lng] — GPS coordinates where the activity ended
            total_distance_m: float — total distance in metres

            elevation:
              · min_m   — lowest altitude reached (metres above sea level)
              · max_m   — highest altitude reached (metres above sea level)
              · gain_m  — total elevation gained (metres)
              · loss_m  — total elevation lost (metres)
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
        Use this for precise sub-activity analysis at any distance boundary.

        Use this when the user asks about:
          · Pace for a specific segment: "first km", "last 2km", "km 3 to 7"
          · Comparing first-km pace across multiple runs (call once per activity)
          · Analysing performance in a specific race segment

        Common distance ranges:
          First km:     start_m=0,    end_m=1000   (default)
          5–10 km:      start_m=5000, end_m=10000
          Last 2 km:    start_m=total_distance-2000, end_m=total_distance
          Middle third: compute from total_distance in activity detail

        For first-km pace trend across multiple runs:
          → Call list_activities to get run IDs
          → Call this once per ID with start_m=0, end_m=1000
          → Compare pace_formatted across dates

        Args:
            activity_id  [API]      Strava activity ID.
            start_m      [abstract] Distance in metres where the segment starts.
                                    Default 0 (activity start).
            end_m        [abstract] Distance in metres where the segment ends.
                                    Default 1000 (first km). If the activity is
                                    shorter than end_m, the last point is used.

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
        Fetch and aggregate specific stream types for advanced or composite analysis.

        Prefer the named analysis tools (get_pace_profile, get_hr_profile, etc.)
        over this function. Use get_raw_streams only when you need a stream
        combination not covered by the named tools (e.g. temp + cadence together).

        IMPORTANT — Output format:
          Returns DISTILLED per-km aggregates, NOT raw per-second arrays.
          If distance + time are both requested, a full per-km breakdown is
          computed for all other streams. Without distance/time, returns
          summary stats (min, max, avg) for each stream.

        Args:
            activity_id   [API] Strava activity ID.
            stream_keys   [API] List of stream type names to fetch. Valid values:
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
            streams_requested: list of keys actually fetched
            data_points_raw: int — original data resolution

            per_km (when distance + time included): list of per-km dicts
              containing aggregates for each requested stream

            summary (when distance + time included): overall pacing summary
              (same structure as get_pace_profile summary)

            {key}_stats (fallback without distance/time):
              {count, avg, min, max} for each numeric stream

            geo (when latlng included):
              bounding_box_sw, bounding_box_ne, start, end coordinates

            moving_pct (when moving included):
              percentage of time the athlete was moving
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
        Fetch distilled stream analytics for a specific segment effort.

        Use after get_segment_efforts to drill into the time-series data for
        one particular segment effort (e.g. a PR attempt on a climb or sprint).
        Returns the same distilled per-km format as get_raw_streams.

        Use this when the user asks about:
          · Pace, power, or HR during a specific segment attempt
          · How pacing varied across a segment (e.g. did they go out too hard?)
          · Comparing stream data between two efforts on the same segment

        Args:
            effort_id    [API]      Strava segment effort ID (from get_segment_efforts).
                                    Sent to GET /segment_efforts/{id}/streams.
            stream_keys  [API]      Stream types to fetch. Defaults to pace preset
                                    (time, distance, velocity_smooth, altitude).
                                    Same valid values as get_raw_streams.

        Returns:
            Same distilled structure as get_raw_streams:
            per_km splits + summary when distance/time included,
            or summary stats per stream otherwise.
        """
        keys: list[StreamKey] | None = None
        if stream_keys:
            keys = [StreamKey(k) for k in stream_keys]
        return stream_service.analyse_segment_effort_streams(effort_id, keys)