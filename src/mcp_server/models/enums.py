"""Strava API v3 enumeration types.

Every string-literal field accepted by the API is represented here as a
Python Enum so that:
  - Tools can declare precise Literal constraints in their signatures.
  - Pydantic validates values at the boundary, not inside service logic.
  - IDE and type-checker can surface invalid values before runtime.
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Activity / Sport types
# ---------------------------------------------------------------------------

class SportType(str, Enum):
    """
    Strava v3 sport_type — the canonical activity classification.

    Superset of the legacy ActivityType; use this for all new code.
    Passed directly to the Strava API as-is (e.g. sport_type='Run').
    """
    ALPINE_SKI            = "AlpineSki"
    BACKCOUNTRY_SKI       = "BackcountrySki"
    BADMINTON             = "Badminton"
    BASKETBALL            = "Basketball"
    CANOEING              = "Canoeing"
    CRICKET               = "Cricket"
    CROSSFIT              = "Crossfit"
    DANCE                 = "Dance"
    E_BIKE_RIDE           = "EBikeRide"
    ELLIPTICAL            = "Elliptical"
    E_MOUNTAIN_BIKE_RIDE  = "EMountainBikeRide"
    GOLF                  = "Golf"
    GRAVEL_RIDE           = "GravelRide"
    HANDCYCLE             = "Handcycle"
    HIIT                  = "HighIntensityIntervalTraining"
    HIKE                  = "Hike"
    ICE_SKATE             = "IceSkate"
    INLINE_SKATE          = "InlineSkate"
    KAYAKING              = "Kayaking"
    KITESURF              = "Kitesurf"
    MOUNTAIN_BIKE_RIDE    = "MountainBikeRide"
    NORDIC_SKI            = "NordicSki"
    PADEL                 = "Padel"
    PHYSICAL_THERAPY      = "PhysicalTherapy"
    PICKLEBALL            = "Pickleball"
    PILATES               = "Pilates"
    RACQUETBALL           = "Racquetball"
    RIDE                  = "Ride"
    ROCK_CLIMBING         = "RockClimbing"
    ROLLER_SKI            = "RollerSki"
    ROWING                = "Rowing"
    RUN                   = "Run"
    SAIL                  = "Sail"
    SKATEBOARD            = "Skateboard"
    SNOWBOARD             = "Snowboard"
    SNOWSHOE              = "Snowshoe"
    SOCCER                = "Soccer"
    SQUASH                = "Squash"
    STAIR_STEPPER         = "StairStepper"
    STAND_UP_PADDLING     = "StandUpPaddling"
    SURFING               = "Surfing"
    SWIM                  = "Swim"
    TABLE_TENNIS          = "TableTennis"
    TENNIS                = "Tennis"
    TRAIL_RUN             = "TrailRun"
    VELOMOBILE            = "Velomobile"
    VIRTUAL_RIDE          = "VirtualRide"
    VIRTUAL_ROW           = "VirtualRow"
    VIRTUAL_RUN           = "VirtualRun"
    VOLLEYBALL            = "Volleyball"
    WALK                  = "Walk"
    WEIGHT_TRAINING       = "WeightTraining"
    WHEELCHAIR            = "Wheelchair"
    WINDSURF              = "Windsurf"
    WORKOUT               = "Workout"
    YOGA                  = "Yoga"


# ---------------------------------------------------------------------------
# Stream keys
# ---------------------------------------------------------------------------

class StreamKey(str, Enum):
    """
    Valid stream type keys for GET /activities/{id}/streams.

    Each key maps to one time-series array in the response.
    Only request the keys needed — every extra key adds payload.

    Presets (used by services internally):
      Pace analysis  : TIME, DISTANCE, VELOCITY_SMOOTH, ALTITUDE
      HR analysis    : TIME, DISTANCE, HEARTRATE, VELOCITY_SMOOTH
      Power analysis : TIME, DISTANCE, WATTS, CADENCE, VELOCITY_SMOOTH
      GPS / map      : LATLNG, DISTANCE, ALTITUDE
    """
    TIME             = "time"           # seconds elapsed since activity start
    DISTANCE         = "distance"       # cumulative metres
    LATLNG           = "latlng"         # [lat, lng] pairs
    ALTITUDE         = "altitude"       # metres above sea level
    VELOCITY_SMOOTH  = "velocity_smooth"  # smoothed m/s
    HEARTRATE        = "heartrate"      # bpm
    CADENCE          = "cadence"        # rpm (run: steps/min ÷ 2)
    WATTS            = "watts"          # power output
    TEMP             = "temp"           # celsius
    MOVING           = "moving"         # boolean — whether athlete was moving
    GRADE_SMOOTH     = "grade_smooth"   # smoothed gradient %


# ---------------------------------------------------------------------------
# Segment activity type (explore endpoint)
# ---------------------------------------------------------------------------

class SegmentActivityType(str, Enum):
    """Activity type filter for GET /segments/explore."""
    RUNNING = "running"
    RIDING  = "riding"


# ---------------------------------------------------------------------------
# Client-side sort controls (not native to Strava API)
# ---------------------------------------------------------------------------

class SortField(str, Enum):
    """
    Fields on which the client-side activity list sort is applied.

    These map to attributes on the SummaryActivity model, not to API params.
    """
    DATE      = "start_date"
    DISTANCE  = "distance"
    MOVING_TIME    = "moving_time"
    ELEVATION = "total_elevation_gain"
    NAME      = "name"
    PACE      = "average_speed"   # sort ascending = slowest first


class SortOrder(str, Enum):
    ASC  = "asc"
    DESC = "desc"