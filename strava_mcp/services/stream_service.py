"""Stream service.

Bridges abstract analytics requests to the Strava streams API.

Parameter routing:
  NATIVE TO API   : activity_id, keys (the stream type list), key_by_type
  ABSTRACT (ours) : distance_marker_m (segment start), analysis presets

The LLM never needs to know internal stream key names for common use cases —
it calls named analysis functions (get_pace_profile, get_hr_profile, etc.)
and the service chooses the right keys internally.  For advanced use, the
raw get_streams function accepts explicit key names.
"""

from __future__ import annotations

from typing import Any

from strava_mcp.api import endpoints, get
from strava_mcp.models.enums import StreamKey


# ---------------------------------------------------------------------------
# Stream key presets  (internal — not exposed to tools)
# ---------------------------------------------------------------------------

_KEYS_PACE  = [StreamKey.TIME, StreamKey.DISTANCE,
               StreamKey.VELOCITY_SMOOTH, StreamKey.ALTITUDE]

_KEYS_HR    = [StreamKey.TIME, StreamKey.DISTANCE,
               StreamKey.HEARTRATE, StreamKey.VELOCITY_SMOOTH]

_KEYS_POWER = [StreamKey.TIME, StreamKey.DISTANCE,
               StreamKey.WATTS, StreamKey.CADENCE,
               StreamKey.VELOCITY_SMOOTH]

_KEYS_GPS   = [StreamKey.LATLNG, StreamKey.DISTANCE, StreamKey.ALTITUDE]

_KEYS_ALL   = list(StreamKey)


# ---------------------------------------------------------------------------
# Core fetch (native API params fully exposed)
# ---------------------------------------------------------------------------

def get_streams(
    activity_id: int,
    keys: list[StreamKey],
) -> dict[str, Any]:
    """
    Fetch the requested stream types for an activity.

    Native params forwarded:
      activity_id — Strava activity ID
      keys        — comma-joined stream keys sent as the `keys` query param
      key_by_type — always True; response is keyed by stream type

    Returns a dict keyed by stream type name, each value being:
      {data: [...], original_size: N, resolution: "high", series_type: "distance"}
    """
    key_str = ",".join(k.value for k in keys)
    raw = get(
        endpoints.activity_streams(activity_id),
        params={"keys": key_str, "key_by_type": "true"},
    )
    # Strava may return a list; normalise to dict keyed by type
    if isinstance(raw, list):
        return {item["type"]: item for item in raw}
    return raw


# ---------------------------------------------------------------------------
# Named analysis functions (abstract — tools call these)
# ---------------------------------------------------------------------------

def get_pace_profile(activity_id: int) -> dict[str, Any]:
    """
    Fetch time, distance, smoothed velocity, and altitude streams.
    Sufficient for: per-km pace analysis, pace charts, elevation-pace correlation.
    """
    return get_streams(activity_id, keys=_KEYS_PACE)


def get_hr_profile(activity_id: int) -> dict[str, Any]:
    """
    Fetch time, distance, heart rate, and velocity streams.
    Sufficient for: HR-zone breakdowns, aerobic drift detection, HR-pace scatter.
    """
    return get_streams(activity_id, keys=_KEYS_HR)


def get_power_profile(activity_id: int) -> dict[str, Any]:
    """
    Fetch time, distance, watts, cadence, and velocity streams.
    Sufficient for: power curves, normalised power, cadence-power charts.
    """
    return get_streams(activity_id, keys=_KEYS_POWER)


def get_gps_track(activity_id: int) -> dict[str, Any]:
    """
    Fetch lat/lng, distance, and altitude streams.
    Sufficient for: map rendering, route replay, elevation profiles.
    """
    return get_streams(activity_id, keys=_KEYS_GPS)


# ---------------------------------------------------------------------------
# Derived analytics (abstract computation over streams)
# ---------------------------------------------------------------------------

def analyse_distance_segment(
    activity_id: int,
    start_m: float = 0.0,
    end_m: float = 1000.0,
) -> dict[str, Any]:
    """
    Compute pace, HR, and elevation stats for an arbitrary distance segment.

    Abstract params (not native to Strava):
      start_m — distance into activity where the segment begins (metres)
      end_m   — distance into activity where the segment ends (metres)

    Examples:
      First km:   start_m=0,    end_m=1000
      5–10 km:    start_m=5000, end_m=10000
      Last 2 km:  pass end_m=activity total distance, start_m=total-2000

    Returns:
      elapsed_time_s, pace_min_per_km, avg_hr (if available),
      elevation_gain, avg_velocity_ms, start_m, end_m
    """
    # Fetch both pace and HR keys in one call to avoid two round-trips
    all_keys = list(dict.fromkeys(_KEYS_PACE + _KEYS_HR))  # deduplicated, order-preserving
    streams = get_streams(activity_id, keys=all_keys)

    distance_data: list[float] = streams.get("distance", {}).get("data", [])
    time_data:     list[int]   = streams.get("time",     {}).get("data", [])
    vel_data:      list[float] = streams.get("velocity_smooth", {}).get("data", [])
    hr_data:       list[int]   = streams.get("heartrate", {}).get("data", [])
    alt_data:      list[float] = streams.get("altitude",  {}).get("data", [])

    if not distance_data or not time_data:
        return {"error": "Stream data unavailable for this activity."}

    # Find index range for [start_m, end_m]
    start_idx = next((i for i, d in enumerate(distance_data) if d >= start_m), 0)
    end_idx   = next(
        (i for i, d in enumerate(distance_data) if d >= end_m),
        len(distance_data) - 1,
    )

    if start_idx >= end_idx:
        return {"error": f"Segment [{start_m}m – {end_m}m] not found in stream data."}

    covered_m  = distance_data[end_idx] - distance_data[start_idx]
    elapsed_s  = time_data[end_idx] - time_data[start_idx]

    if elapsed_s <= 0 or covered_m <= 0:
        return {"error": "Zero distance or time in selected segment."}

    avg_vel_ms      = covered_m / elapsed_s
    pace_min_per_km = 1000.0 / (avg_vel_ms * 60.0)

    # HR
    hr_segment = hr_data[start_idx:end_idx + 1] if hr_data else []
    avg_hr = round(sum(hr_segment) / len(hr_segment), 1) if hr_segment else None

    # Elevation
    alt_segment = alt_data[start_idx:end_idx + 1]
    elev_gain = 0.0
    if alt_segment:
        for i in range(1, len(alt_segment)):
            diff = alt_segment[i] - alt_segment[i - 1]
            if diff > 0:
                elev_gain += diff

    # Smoothed velocity average
    vel_segment = vel_data[start_idx:end_idx + 1] if vel_data else []
    avg_smooth_vel = sum(vel_segment) / len(vel_segment) if vel_segment else avg_vel_ms

    mins = int(pace_min_per_km)
    secs = int((pace_min_per_km - mins) * 60)

    return {
        "start_m":          distance_data[start_idx],
        "end_m":            distance_data[end_idx],
        "covered_m":        round(covered_m, 1),
        "elapsed_time_s":   elapsed_s,
        "pace_min_per_km":  round(pace_min_per_km, 2),
        "pace_formatted":   f"{mins}:{secs:02d} /km",
        "avg_velocity_ms":  round(avg_vel_ms, 3),
        "avg_smooth_velocity_ms": round(avg_smooth_vel, 3),
        "avg_heartrate":    avg_hr,
        "elevation_gain_m": round(elev_gain, 1),
    }


def analyse_segment_effort_streams(
    effort_id: int,
    keys: list[StreamKey] | None = None,
) -> dict[str, Any]:
    """
    Fetch streams for a specific segment effort.

    Native param: effort_id (Strava segment effort ID)
    Abstract:     keys defaults to pace preset if omitted
    """
    requested = keys or _KEYS_PACE
    key_str = ",".join(k.value for k in requested)
    raw = get(
        endpoints.segment_effort_streams(effort_id),
        params={"keys": key_str, "key_by_type": "true"},
    )
    if isinstance(raw, list):
        return {item["type"]: item for item in raw}
    return raw