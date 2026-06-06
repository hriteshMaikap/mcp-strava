"""Strava API endpoints."""

from __future__ import annotations

BASE_URL = "https://www.strava.com/api/v3"

def activities_list() -> str:
    return f"{BASE_URL}/athlete/activities"

def activity_detail(activity_id: int) -> str:
    return f"{BASE_URL}/activities/{activity_id}"

def activity_laps(activity_id: int) -> str:
    return f"{BASE_URL}/activities/{activity_id}/laps"

def activity_zones(activity_id: int) -> str:
    return f"{BASE_URL}/activities/{activity_id}/zones"

def activity_streams(activity_id: int) -> str:
    return f"{BASE_URL}/activities/{activity_id}/streams"

def athlete() -> str:
    return f"{BASE_URL}/athlete"

def athlete_stats(athlete_id: int) -> str:
    return f"{BASE_URL}/athletes/{athlete_id}/stats"

def athlete_zones() -> str:
    return f"{BASE_URL}/athlete/zones"

def gear(gear_id: str) -> str:
    return f"{BASE_URL}/gear/{gear_id}"

def athlete_clubs() -> str:
    return f"{BASE_URL}/athlete/clubs"

def starred_segments() -> str:
    return f"{BASE_URL}/segments/starred"

def segment(segment_id: int) -> str:
    return f"{BASE_URL}/segments/{segment_id}"

def segment_efforts() -> str:
    return f"{BASE_URL}/segment_efforts"

def explore_segments() -> str:
    return f"{BASE_URL}/segments/explore"

def star_segment(segment_id: int) -> str:
    return f"{BASE_URL}/segments/{segment_id}/starred"

def segment_effort_streams(effort_id: int) -> str:
    return f"{BASE_URL}/segment_efforts/{effort_id}/streams"
