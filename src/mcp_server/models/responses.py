"""Pydantic response models for all Strava v3 API objects.

These validate and type the raw JSON returned by the API.
Derived properties (pace, distance_km) are computed here so service
and tool layers never do arithmetic.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

class PolylineMap(BaseModel):
    id: str
    summary_polyline: str | None = None
    resource_state: int


class SummaryGear(BaseModel):
    id: str
    primary: bool
    name: str
    resource_state: int
    distance: float  # total metres logged on this gear


class ZoneBucket(BaseModel):
    """One time-in-zone bucket from /activities/{id}/zones."""
    min: int
    max: int
    time: int  # seconds in this zone


class ActivityZone(BaseModel):
    type: str                          # "heartrate" | "power"
    score: int | None = None
    distribution_buckets: list[ZoneBucket] = Field(default_factory=list)
    sensor_based: bool = False
    custom_zones: bool = False
    points: int | None = None
    max: int | None = None


# ---------------------------------------------------------------------------
# Activity models
# ---------------------------------------------------------------------------

class SplitMetric(BaseModel):
    """One km split inside a DetailedActivity."""
    distance: float
    elapsed_time: int
    elevation_difference: float
    moving_time: int
    split: int
    average_speed: float   # m/s
    pace_zone: int

    @property
    def pace_min_per_km(self) -> float | None:
        if self.average_speed and self.average_speed > 0:
            return 1000.0 / (self.average_speed * 60.0)
        return None

    @property
    def pace_formatted(self) -> str | None:
        p = self.pace_min_per_km
        if p is None:
            return None
        mins = int(p)
        secs = int((p - mins) * 60)
        return f"{mins}:{secs:02d} /km"


class Lap(BaseModel):
    id: int
    resource_state: int
    name: str
    elapsed_time: int
    moving_time: int
    start_date: datetime
    start_date_local: datetime
    distance: float           # metres
    total_elevation_gain: float
    average_speed: float      # m/s
    max_speed: float
    average_cadence: float | None = None
    average_watts: float | None = None
    device_watts: bool | None = None
    average_heartrate: float | None = None
    max_heartrate: float | None = None
    lap_index: int
    split: int

    @property
    def pace_min_per_km(self) -> float | None:
        if self.average_speed and self.average_speed > 0:
            return 1000.0 / (self.average_speed * 60.0)
        return None

    @property
    def pace_formatted(self) -> str | None:
        p = self.pace_min_per_km
        if p is None:
            return None
        mins = int(p)
        secs = int((p - mins) * 60)
        return f"{mins}:{secs:02d} /km"


class SummaryActivity(BaseModel):
    """Lightweight model — returned by GET /athlete/activities."""
    id: int
    name: str
    distance: float           # metres
    moving_time: int          # seconds
    elapsed_time: int
    total_elevation_gain: float
    sport_type: str
    start_date: datetime
    start_date_local: datetime
    timezone: str
    average_speed: float | None = None      # m/s
    max_speed: float | None = None
    average_cadence: float | None = None
    average_watts: float | None = None
    weighted_average_watts: int | None = None
    kilojoules: float | None = None
    device_watts: bool | None = None
    has_heartrate: bool = False
    average_heartrate: float | None = None
    max_heartrate: float | None = None
    suffer_score: float | None = None
    kudos_count: int = 0
    comment_count: int = 0
    achievement_count: int = 0
    trainer: bool = False
    commute: bool = False
    manual: bool = False
    private: bool = False
    gear_id: str | None = None
    device_name: str | None = None
    elev_high: float | None = None
    elev_low: float | None = None
    map: PolylineMap | None = None
    pr_count: int = 0

    # ---- derived ----

    @property
    def distance_km(self) -> float:
        return self.distance / 1000.0

    @property
    def pace_min_per_km(self) -> float | None:
        if self.average_speed and self.average_speed > 0:
            return 1000.0 / (self.average_speed * 60.0)
        return None

    @property
    def pace_formatted(self) -> str | None:
        p = self.pace_min_per_km
        if p is None:
            return None
        mins = int(p)
        secs = int((p - mins) * 60)
        return f"{mins}:{secs:02d} /km"

    @property
    def moving_time_formatted(self) -> str:
        h = self.moving_time // 3600
        m = (self.moving_time % 3600) // 60
        s = self.moving_time % 60
        return f"{h}:{m:02d}:{s:02d}"


class DetailedActivity(SummaryActivity):
    """Full model — returned by GET /activities/{id}."""
    description: str | None = None
    calories: float | None = None
    gear: SummaryGear | None = None
    splits_metric: list[SplitMetric] = Field(default_factory=list)
    laps: list[Lap] = Field(default_factory=list)
    # segment_efforts excluded by default — only fetched when requested


# ---------------------------------------------------------------------------
# Athlete models
# ---------------------------------------------------------------------------

class SummaryGearAthlete(BaseModel):
    id: str
    primary: bool
    name: str
    resource_state: int
    distance: float


class DetailedAthlete(BaseModel):
    id: int
    username: str | None = None
    firstname: str
    lastname: str
    city: str | None = None
    state: str | None = None
    country: str | None = None
    sex: str | None = None
    premium: bool = False
    summit: bool = False
    follower_count: int = 0
    friend_count: int = 0
    measurement_preference: str = "meters"
    ftp: int | None = None
    weight: float | None = None
    bikes: list[SummaryGearAthlete] = Field(default_factory=list)
    shoes: list[SummaryGearAthlete] = Field(default_factory=list)


class ActivityTotal(BaseModel):
    """Rolled-up totals inside ActivityStats."""
    count: int = 0
    distance: float = 0.0       # metres
    moving_time: int = 0        # seconds
    elapsed_time: int = 0
    elevation_gain: float = 0.0
    achievement_count: int = 0


class ActivityStats(BaseModel):
    biggest_ride_distance: float | None = None
    biggest_climb_elevation_gain: float | None = None
    recent_ride_totals: dict[str, Any] | None = None
    recent_run_totals: dict[str, Any] | None = None
    recent_swim_totals: dict[str, Any] | None = None
    ytd_ride_totals: dict[str, Any] | None = None
    ytd_run_totals: dict[str, Any] | None = None
    ytd_swim_totals: dict[str, Any] | None = None
    all_ride_totals: dict[str, Any] | None = None
    all_run_totals: dict[str, Any] | None = None
    all_swim_totals: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Stream models
# ---------------------------------------------------------------------------

class BaseStream(BaseModel):
    original_size: int
    resolution: str   # "low" | "medium" | "high"
    series_type: str  # "distance" | "time"


class TimeStream(BaseStream):
    data: list[int]          # seconds from activity start


class DistanceStream(BaseStream):
    data: list[float]        # cumulative metres


class AltitudeStream(BaseStream):
    data: list[float]        # metres ASL


class VelocityStream(BaseStream):
    data: list[float]        # smoothed m/s


class HeartrateStream(BaseStream):
    data: list[int]          # bpm


class CadenceStream(BaseStream):
    data: list[int]          # rpm


class PowerStream(BaseStream):
    data: list[int]          # watts


class LatLngStream(BaseStream):
    data: list[list[float]]  # [[lat, lng], ...]


class MovingStream(BaseStream):
    data: list[bool]


class GradeStream(BaseStream):
    data: list[float]        # percent


class TemperatureStream(BaseStream):
    data: list[int]          # celsius


# ---------------------------------------------------------------------------
# Segment models
# ---------------------------------------------------------------------------

class SegmentPREffort(BaseModel):
    pr_activity_id: int
    pr_elapsed_time: int
    pr_date: str
    effort_count: int


class DetailedSegment(BaseModel):
    id: int
    name: str
    activity_type: str
    distance: float
    average_grade: float
    maximum_grade: float
    elevation_high: float
    elevation_low: float
    climb_category: int       # 0=uncat, 1=4, 2=3, 3=2, 4=1, 5=HC
    city: str | None = None
    state: str | None = None
    country: str | None = None
    effort_count: int = 0
    athlete_count: int = 0
    star_count: int = 0
    athlete_pr_effort: SegmentPREffort | None = None


class SegmentEffort(BaseModel):
    id: int
    name: str
    elapsed_time: int
    moving_time: int
    start_date: str
    start_date_local: str
    distance: float
    start_index: int
    end_index: int
    average_watts: float | None = None
    average_heartrate: float | None = None
    kom_rank: int | None = None
    pr_rank: int | None = None

    @property
    def pace_min_per_km(self) -> float | None:
        if self.elapsed_time > 0 and self.distance > 0:
            speed_ms = self.distance / self.elapsed_time
            return 1000.0 / (speed_ms * 60.0)
        return None