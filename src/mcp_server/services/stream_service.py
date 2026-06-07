"""Stream service.

Bridges abstract analytics requests to the Strava streams API,
with distillation applied to compress per-second arrays into
per-km statistical summaries.

Architecture:
    _fetch_streams()     — raw API call (internal only)
    get_pace_profile()   — distilled per-km pace analysis
    get_hr_profile()     — distilled per-km HR + drift analysis
    get_power_profile()  — distilled per-km power + normalised power
    get_gps_track()      — distilled bounding box + elevation
    get_streams()        — distilled generic aggregation (for get_raw_streams tool)
    analyse_*            — derived analytics (uses raw streams internally)
"""

from __future__ import annotations

from typing import Any

from mcp_server.api import endpoints, get
from mcp_server.distillation import streams as distill
from mcp_server.models.enums import StreamKey


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
# Internal raw fetch (NOT exposed to tools — used by analyse_* functions)
# ---------------------------------------------------------------------------

def _fetch_streams(
    activity_id: int,
    keys: list[StreamKey],
) -> dict[str, Any]:
    """Fetch raw stream data from Strava API.

    Returns a dict keyed by stream type name, each value being:
      {data: [...], original_size: N, resolution: "high", series_type: "distance"}

    This is the ONLY function that touches the API. All other functions
    in this module either distill or compute derived analytics from this output.
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
# Distilled analysis functions (tools call these)
# ---------------------------------------------------------------------------

def get_pace_profile(activity_id: int) -> dict[str, Any]:
    """Fetch and distill pace streams into per-km analysis.

    Raw: ~57,000 tokens (4 streams × 4,473 per-second data points)
    Distilled: ~500 tokens (per-km splits + pacing summary)
    """
    raw = _fetch_streams(activity_id, keys=_KEYS_PACE)
    return distill.distill_pace_profile(raw)


def get_hr_profile(activity_id: int) -> dict[str, Any]:
    """Fetch and distill HR streams into per-km + drift analysis.

    Raw: ~42,000 tokens
    Distilled: ~300 tokens (per-km HR + drift + efficiency)
    """
    raw = _fetch_streams(activity_id, keys=_KEYS_HR)
    return distill.distill_hr_profile(raw)


def get_power_profile(activity_id: int) -> dict[str, Any]:
    """Fetch and distill power streams into per-km + normalised power.

    Raw: ~42,000 tokens
    Distilled: ~300 tokens (per-km power + cadence + NP)
    """
    raw = _fetch_streams(activity_id, keys=_KEYS_POWER)
    return distill.distill_power_profile(raw)


def get_gps_track(activity_id: int) -> dict[str, Any]:
    """Fetch and distill GPS streams into bounding box + elevation.

    Raw: ~90,000 tokens (4,473 lat/lng pairs + distance + altitude)
    Distilled: ~150 tokens (bounding box, start/end, elevation summary)
    """
    raw = _fetch_streams(activity_id, keys=_KEYS_GPS)
    return distill.distill_gps_track(raw)


def get_streams(
    activity_id: int,
    keys: list[StreamKey],
) -> dict[str, Any]:
    """Fetch and distill arbitrary streams (for get_raw_streams tool).

    Applies per-km aggregation for all requested stream types.

    Raw: up to ~143,000 tokens for all keys
    Distilled: ~800 tokens (per-km aggregates for all streams)
    """
    raw = _fetch_streams(activity_id, keys=keys)
    return distill.distill_raw_streams(raw)


# ---------------------------------------------------------------------------
# Derived analytics (abstract computation over raw streams)
# These use _fetch_streams internally because they need per-second
# resolution to compute precise segment slices.
# ---------------------------------------------------------------------------

def analyse_distance_segment(
    activity_id: int,
    start_m: float = 0.0,
    end_m: float = 1000.0,
) -> dict[str, Any]:
    """Compute pace, HR, and elevation stats for an arbitrary distance segment.

    This function needs raw per-second data for precise slicing — it
    calls _fetch_streams directly and returns an already-compact result
    (~65 tokens). No further distillation needed.
    """
    # Fetch both pace and HR keys in one call to avoid two round-trips
    all_keys = list(dict.fromkeys(_KEYS_PACE + _KEYS_HR))  # deduplicated, order-preserving
    streams = _fetch_streams(activity_id, keys=all_keys)

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
    """Fetch and distill streams for a specific segment effort.

    Uses the distilled raw streams pipeline since segment efforts
    can contain significant data.
    """
    requested = keys or _KEYS_PACE
    key_str = ",".join(k.value for k in requested)
    raw = get(
        endpoints.segment_effort_streams(effort_id),
        params={"keys": key_str, "key_by_type": "true"},
    )
    if isinstance(raw, list):
        raw = {item["type"]: item for item in raw}
    return distill.distill_raw_streams(raw)