"""Stream response distillation — the critical piece.

Replaces raw per-second time-series arrays (thousands of data points)
with pre-computed per-km statistical summaries that an LLM can actually
reason about.

Compression ratio: ~99% (e.g. 57,000 tokens → ~500 tokens).

Design principle:
    The LLM almost never needs per-second resolution. For pace analysis,
    it needs "km 3 was 6:14/km with +6.7m elevation". For HR drift, it
    needs "avg HR rose from 148 bpm in km 1 to 160 bpm in km 7". These
    are statistical summaries, not raw arrays.
"""

from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _find_km_boundaries(distance_data: list[float]) -> list[int]:
    """Return indices where each km starts: [0, idx_at_1km, idx_at_2km, ..., last_idx]."""
    if not distance_data:
        return []
    boundaries = [0]
    next_km = 1000.0
    for i, d in enumerate(distance_data):
        if d >= next_km:
            boundaries.append(i)
            next_km += 1000.0
    # Always include the final index
    last_idx = len(distance_data) - 1
    if boundaries[-1] != last_idx:
        boundaries.append(last_idx)
    return boundaries


def _velocity_to_pace(velocity_ms: float) -> str | None:
    """Convert m/s velocity to 'M:SS/km' pace string."""
    if not velocity_ms or velocity_ms <= 0:
        return None
    pace = 1000.0 / (velocity_ms * 60.0)
    mins = int(pace)
    secs = int((pace - mins) * 60)
    return f"{mins}:{secs:02d}/km"


def _elevation_change(alt_slice: list[float]) -> tuple[float, float]:
    """Compute (gain, loss) in metres from an altitude slice."""
    gain = loss = 0.0
    for i in range(1, len(alt_slice)):
        diff = alt_slice[i] - alt_slice[i - 1]
        if diff > 0:
            gain += diff
        elif diff < 0:
            loss -= diff  # make positive
    return round(gain, 1), round(loss, 1)


def _safe_avg(data: list, decimals: int = 2) -> float | None:
    """Average of a numeric list, or None if empty."""
    if not data:
        return None
    return round(sum(data) / len(data), decimals)


def _safe_max(data: list) -> float | int | None:
    """Max of a list, or None if empty."""
    return max(data) if data else None


def _safe_min(data: list) -> float | int | None:
    """Min of a list, or None if empty."""
    return min(data) if data else None


# ---------------------------------------------------------------------------
# Per-km aggregation engine
# ---------------------------------------------------------------------------

def _aggregate_per_km(
    distance_data: list[float],
    time_data: list[int],
    *,
    velocity_data: list[float] | None = None,
    altitude_data: list[float] | None = None,
    heartrate_data: list[int] | None = None,
    watts_data: list[int] | None = None,
    cadence_data: list[int] | None = None,
    grade_data: list[float] | None = None,
    temp_data: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Core aggregation: slice all streams into per-km segments and compute stats.

    Returns a list of dicts, one per km:
      [{"km": 1, "elapsed_s": 394, "pace": "6:27/km", ...}, ...]
    """
    boundaries = _find_km_boundaries(distance_data)
    if len(boundaries) < 2:
        return []

    km_splits: list[dict[str, Any]] = []

    for i in range(len(boundaries) - 1):
        start_idx = boundaries[i]
        end_idx = boundaries[i + 1]

        segment_dist = distance_data[end_idx] - distance_data[start_idx]
        segment_time = time_data[end_idx] - time_data[start_idx]

        km_entry: dict[str, Any] = {"km": i + 1}

        # Distance & time
        km_entry["distance_m"] = round(segment_dist, 1)
        km_entry["elapsed_s"] = segment_time

        # Pace (from actual distance / time, not from velocity stream)
        if segment_time > 0 and segment_dist > 0:
            avg_vel = segment_dist / segment_time
            km_entry["pace"] = _velocity_to_pace(avg_vel)
            km_entry["speed_ms"] = round(avg_vel, 2)

        # Velocity (smoothed)
        if velocity_data:
            vel_slice = velocity_data[start_idx:end_idx + 1]
            km_entry["smooth_speed_ms"] = _safe_avg(vel_slice)

        # Altitude / elevation
        if altitude_data:
            alt_slice = altitude_data[start_idx:end_idx + 1]
            gain, loss = _elevation_change(alt_slice)
            km_entry["elev_gain_m"] = gain
            km_entry["elev_loss_m"] = loss

        # Heart rate
        if heartrate_data:
            hr_slice = heartrate_data[start_idx:end_idx + 1]
            if hr_slice:
                km_entry["avg_hr"] = round(_safe_avg(hr_slice, 0))
                km_entry["max_hr"] = _safe_max(hr_slice)

        # Power
        if watts_data:
            watts_slice = watts_data[start_idx:end_idx + 1]
            if watts_slice:
                km_entry["avg_watts"] = round(_safe_avg(watts_slice, 0))
                km_entry["max_watts"] = _safe_max(watts_slice)

        # Cadence
        if cadence_data:
            cad_slice = cadence_data[start_idx:end_idx + 1]
            if cad_slice:
                km_entry["avg_cadence"] = round(_safe_avg(cad_slice, 0))

        # Grade
        if grade_data:
            grade_slice = grade_data[start_idx:end_idx + 1]
            if grade_slice:
                km_entry["avg_grade_pct"] = _safe_avg(grade_slice)

        # Temperature
        if temp_data:
            temp_slice = temp_data[start_idx:end_idx + 1]
            if temp_slice:
                km_entry["avg_temp_c"] = round(_safe_avg(temp_slice, 0))

        km_splits.append(km_entry)

    return km_splits


def _pacing_summary(
    km_splits: list[dict[str, Any]],
    altitude_data: list[float] | None = None,
) -> dict[str, Any]:
    """Compute overall pacing summary from per-km splits."""
    if not km_splits:
        return {}

    # Find fastest / slowest by speed_ms
    speeds = [(s["km"], s.get("speed_ms", 0)) for s in km_splits if s.get("speed_ms")]
    if not speeds:
        return {}

    total_dist = sum(s.get("distance_m", 0) for s in km_splits)
    total_time = sum(s.get("elapsed_s", 0) for s in km_splits)

    summary: dict[str, Any] = {
        "total_km": round(total_dist / 1000, 2),
        "total_time_s": total_time,
    }

    # Overall pace
    if total_time > 0 and total_dist > 0:
        overall_vel = total_dist / total_time
        summary["avg_pace"] = _velocity_to_pace(overall_vel)

    # Fastest / slowest km
    fastest = max(speeds, key=lambda x: x[1])
    slowest = min(speeds, key=lambda x: x[1])
    summary["fastest_km"] = {"km": fastest[0], "pace": _velocity_to_pace(fastest[1])}
    summary["slowest_km"] = {"km": slowest[0], "pace": _velocity_to_pace(slowest[1])}

    # Split analysis (first half vs second half)
    mid = len(km_splits) // 2
    if mid > 0:
        first_half_dist = sum(s.get("distance_m", 0) for s in km_splits[:mid])
        first_half_time = sum(s.get("elapsed_s", 0) for s in km_splits[:mid])
        second_half_dist = sum(s.get("distance_m", 0) for s in km_splits[mid:])
        second_half_time = sum(s.get("elapsed_s", 0) for s in km_splits[mid:])

        if first_half_time > 0 and second_half_time > 0:
            fh_vel = first_half_dist / first_half_time
            sh_vel = second_half_dist / second_half_time
            summary["first_half_pace"] = _velocity_to_pace(fh_vel)
            summary["second_half_pace"] = _velocity_to_pace(sh_vel)
            summary["split_type"] = "negative" if sh_vel > fh_vel else "positive"

    # Overall elevation
    if altitude_data:
        gain, loss = _elevation_change(altitude_data)
        summary["total_elev_gain_m"] = gain
        summary["total_elev_loss_m"] = loss

    # Pace variability
    if len(speeds) > 1:
        avg_speed = sum(s for _, s in speeds) / len(speeds)
        if avg_speed > 0:
            variance = sum((s - avg_speed) ** 2 for _, s in speeds) / len(speeds)
            cv = (variance ** 0.5) / avg_speed * 100
            summary["pace_variability_pct"] = round(cv, 1)

    return summary


# ---------------------------------------------------------------------------
# Tool-specific distillation functions
# ---------------------------------------------------------------------------

def distill_pace_profile(streams: dict[str, Any]) -> dict[str, Any]:
    """Distill raw pace streams into per-km analysis.

    Input streams: time, distance, velocity_smooth, altitude
    Output: ~500 tokens instead of ~57,000.
    """
    distance_data = _extract_data(streams, "distance")
    time_data = _extract_data(streams, "time")
    velocity_data = _extract_data(streams, "velocity_smooth")
    altitude_data = _extract_data(streams, "altitude")

    if not distance_data or not time_data:
        return {"error": "Missing distance or time stream data."}

    km_splits = _aggregate_per_km(
        distance_data, time_data,
        velocity_data=velocity_data,
        altitude_data=altitude_data,
    )

    return {
        "data_points_raw": len(distance_data),
        "per_km": km_splits,
        "summary": _pacing_summary(km_splits, altitude_data),
    }


def distill_hr_profile(streams: dict[str, Any]) -> dict[str, Any]:
    """Distill raw HR streams into per-km analysis + zone/drift stats.

    Input streams: time, distance, heartrate, velocity_smooth
    Output: ~300 tokens instead of ~42,000.
    """
    distance_data = _extract_data(streams, "distance")
    time_data = _extract_data(streams, "time")
    hr_data = _extract_data(streams, "heartrate")
    velocity_data = _extract_data(streams, "velocity_smooth")

    if not distance_data or not time_data:
        return {"error": "Missing distance or time stream data."}

    km_splits = _aggregate_per_km(
        distance_data, time_data,
        velocity_data=velocity_data,
        heartrate_data=hr_data,
    )

    result: dict[str, Any] = {
        "data_points_raw": len(distance_data),
        "per_km": km_splits,
    }

    # HR summary stats
    if hr_data:
        hr_summary: dict[str, Any] = {
            "avg_hr": round(sum(hr_data) / len(hr_data)),
            "max_hr": max(hr_data),
            "min_hr": min(hr_data),
        }

        # HR drift: compare first half avg to second half avg
        mid = len(hr_data) // 2
        if mid > 0:
            first_avg = sum(hr_data[:mid]) / mid
            second_avg = sum(hr_data[mid:]) / (len(hr_data) - mid)
            hr_summary["hr_drift_pct"] = round(
                (second_avg - first_avg) / first_avg * 100, 1
            )
            hr_summary["first_half_avg_hr"] = round(first_avg)
            hr_summary["second_half_avg_hr"] = round(second_avg)

        # Aerobic efficiency: distance per heartbeat
        if time_data and distance_data:
            total_dist = distance_data[-1] - distance_data[0]
            total_time = time_data[-1] - time_data[0]
            avg_hr = hr_summary["avg_hr"]
            if avg_hr > 0 and total_time > 0:
                total_beats = avg_hr * (total_time / 60.0)
                hr_summary["metres_per_heartbeat"] = round(total_dist / total_beats, 2)

        result["hr_summary"] = hr_summary

    return result


def distill_power_profile(streams: dict[str, Any]) -> dict[str, Any]:
    """Distill raw power streams into per-km analysis + normalised power.

    Input streams: time, distance, watts, cadence, velocity_smooth
    Output: ~300 tokens instead of ~42,000.
    """
    distance_data = _extract_data(streams, "distance")
    time_data = _extract_data(streams, "time")
    watts_data = _extract_data(streams, "watts")
    cadence_data = _extract_data(streams, "cadence")
    velocity_data = _extract_data(streams, "velocity_smooth")

    if not distance_data or not time_data:
        return {"error": "Missing distance or time stream data."}

    km_splits = _aggregate_per_km(
        distance_data, time_data,
        velocity_data=velocity_data,
        watts_data=watts_data,
        cadence_data=cadence_data,
    )

    result: dict[str, Any] = {
        "data_points_raw": len(distance_data),
        "per_km": km_splits,
    }

    # Power summary
    if watts_data:
        power_summary: dict[str, Any] = {
            "avg_power_w": round(sum(watts_data) / len(watts_data)),
            "max_power_w": max(watts_data),
        }

        # Normalised power: 30-second rolling average → raise to 4th → avg → 4th root
        if len(watts_data) >= 30:
            rolling_30s: list[float] = []
            window_sum = sum(watts_data[:30])
            for i in range(30, len(watts_data)):
                rolling_30s.append(window_sum / 30.0)
                window_sum += watts_data[i] - watts_data[i - 30]
            rolling_30s.append(window_sum / 30.0)

            avg_4th = sum(v ** 4 for v in rolling_30s) / len(rolling_30s)
            power_summary["normalised_power_w"] = round(avg_4th ** 0.25)

        result["power_summary"] = power_summary

    # Cadence summary
    if cadence_data:
        non_zero_cadence = [c for c in cadence_data if c > 0]
        if non_zero_cadence:
            result["cadence_summary"] = {
                "avg_cadence_rpm": round(sum(non_zero_cadence) / len(non_zero_cadence)),
                "max_cadence_rpm": max(non_zero_cadence),
            }

    return result


def distill_gps_track(streams: dict[str, Any]) -> dict[str, Any]:
    """Distill raw GPS streams into bounding box + elevation summary.

    Input streams: latlng, distance, altitude
    Output: ~150 tokens instead of ~90,000.

    The encoded polyline already exists in the activity summary —
    no need to pass 4,000+ raw lat/lng pairs to the LLM.
    """
    latlng_data = _extract_data(streams, "latlng")
    distance_data = _extract_data(streams, "distance")
    altitude_data = _extract_data(streams, "altitude")

    result: dict[str, Any] = {
        "data_points_raw": len(latlng_data) if latlng_data else 0,
    }

    if latlng_data:
        lats = [p[0] for p in latlng_data]
        lngs = [p[1] for p in latlng_data]
        result["bounding_box"] = {
            "sw": [round(min(lats), 5), round(min(lngs), 5)],
            "ne": [round(max(lats), 5), round(max(lngs), 5)],
        }
        result["start_latlng"] = [round(latlng_data[0][0], 5), round(latlng_data[0][1], 5)]
        result["end_latlng"] = [round(latlng_data[-1][0], 5), round(latlng_data[-1][1], 5)]

    if distance_data:
        result["total_distance_m"] = round(distance_data[-1], 1)

    if altitude_data:
        gain, loss = _elevation_change(altitude_data)
        result["elevation"] = {
            "min_m": round(min(altitude_data), 1),
            "max_m": round(max(altitude_data), 1),
            "gain_m": gain,
            "loss_m": loss,
        }

    return result


def distill_raw_streams(streams: dict[str, Any]) -> dict[str, Any]:
    """Generic distillation for get_raw_streams (arbitrary key combinations).

    Applies per-km aggregation for all available numeric streams.
    Falls back to summary stats if distance/time are not present.
    """
    distance_data = _extract_data(streams, "distance")
    time_data = _extract_data(streams, "time")

    # Identify which streams are present
    available_keys = list(streams.keys())
    data_points = max(
        (len(s.get("data", [])) for s in streams.values() if isinstance(s, dict)),
        default=0,
    )

    result: dict[str, Any] = {
        "streams_requested": available_keys,
        "data_points_raw": data_points,
    }

    # If we have distance + time, do full per-km aggregation
    if distance_data and time_data:
        km_splits = _aggregate_per_km(
            distance_data, time_data,
            velocity_data=_extract_data(streams, "velocity_smooth"),
            altitude_data=_extract_data(streams, "altitude"),
            heartrate_data=_extract_data(streams, "heartrate"),
            watts_data=_extract_data(streams, "watts"),
            cadence_data=_extract_data(streams, "cadence"),
            grade_data=_extract_data(streams, "grade_smooth"),
            temp_data=_extract_data(streams, "temp"),
        )
        result["per_km"] = km_splits
        result["summary"] = _pacing_summary(
            km_splits,
            altitude_data=_extract_data(streams, "altitude"),
        )
    else:
        # Fallback: provide summary stats for each stream
        for key, stream_obj in streams.items():
            if isinstance(stream_obj, dict) and "data" in stream_obj:
                data = stream_obj["data"]
                if data and isinstance(data[0], (int, float)):
                    result[f"{key}_stats"] = {
                        "count": len(data),
                        "avg": _safe_avg(data),
                        "min": _safe_min(data),
                        "max": _safe_max(data),
                    }

    # Handle latlng separately (bounding box)
    latlng_data = _extract_data(streams, "latlng")
    if latlng_data:
        lats = [p[0] for p in latlng_data]
        lngs = [p[1] for p in latlng_data]
        result["geo"] = {
            "bounding_box_sw": [round(min(lats), 5), round(min(lngs), 5)],
            "bounding_box_ne": [round(max(lats), 5), round(max(lngs), 5)],
            "start": [round(latlng_data[0][0], 5), round(latlng_data[0][1], 5)],
            "end": [round(latlng_data[-1][0], 5), round(latlng_data[-1][1], 5)],
        }

    # Handle moving stream (% time moving)
    moving_data = _extract_data(streams, "moving")
    if moving_data:
        moving_count = sum(1 for m in moving_data if m)
        result["moving_pct"] = round(moving_count / len(moving_data) * 100, 1)

    return result


# ---------------------------------------------------------------------------
# Data extraction helper
# ---------------------------------------------------------------------------

def _extract_data(streams: dict[str, Any], key: str) -> list | None:
    """Safely extract the data array from a stream dict.

    Handles both keyed-by-type format:  {"heartrate": {"data": [...]}}
    and list format that _fetch_streams normalises away.
    """
    stream_obj = streams.get(key)
    if isinstance(stream_obj, dict):
        data = stream_obj.get("data")
        if isinstance(data, list) and len(data) > 0:
            return data
    return None
