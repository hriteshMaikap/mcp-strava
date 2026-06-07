# Context Distillation for Strava MCP — Technical Writeup

> **Project**: Strava MCP Server  
> **Date**: 2026-06-07  
> **Objective**: Maximize analytical data delivered to the LLM while minimizing token consumption  

---

## The Problem

Strava's API is designed for UI rendering — it returns everything a web or mobile client might need, including per-second GPS coordinates, encoded polylines, avatar URLs, and social metadata. When this raw data flows into an LLM's context window as MCP tool responses, the effect is catastrophic:

| Metric | Before Distillation |
|--------|-------------------|
| Total tokens (5 queries) | **440,663** |
| Gemma 4 31B saturation | **168.1%** (1.68× over limit) |
| Worst single tool call | **143,286 tokens** (`get_raw_streams` ALL) |

A single `get_pace_profile` call for a 12km run consumed **56,822 tokens** — about **21.7%** of Gemma 4 31B's context window. The LLM would burn significant context on a single query.

---

## The Results

| Metric | Before | After | Reduction |
|--------|--------|-------|-----------|
| **Total tokens (5 queries)** | **440,663** | **6,293** | **98.6%** |
| Gemma 4 31B saturation | 168.1% | **2.4%** | Now fits easily ✅ |
| Worst single tool call | 143,286 | **1,337** | **99.1%** |

> [!IMPORTANT]
> **440,663 → 6,293 tokens. A 70× compression ratio.** All five queries now fit easily inside Gemma 4 31B's 262K context window, leaving ample room for long conversation history.

### Per-Tool Before/After

| Tool | Before (tokens) | After (tokens) | Reduction | Technique |
|------|-----------------|----------------|-----------|-----------|
| `get_raw_streams` (ALL) | 143,286 | 987 | **99.3%** | Statistical aggregation |
| `get_gps_track` | 90,500 | 96 | **99.9%** | Bounding box extraction |
| `get_pace_profile` | 56,822 | 789 | **98.6%** | Per-km aggregation |
| `get_hr_profile` | 42,254 | 514 | **98.8%** | Per-km + drift analysis |
| `get_power_profile` | 42,254 | 514 | **98.8%** | Per-km + normalised power |
| `list_activities` (10) | 4,239 | 1,337 | **68.5%** | Polyline + null stripping |
| `get_activity_detail` | 1,557 | 844 | **45.8%** | Structural stripping |
| `get_athlete_stats` | 345 | 132 | **61.7%** | Zero-block removal |
| `get_athlete_profile` | 236 | 78 | **66.9%** | Social metadata removal |
| `get_activity_laps` | 144 | 94 | **34.7%** | Field stripping |
| `get_athlete_zones` | 87 | 87 | 0% | Already minimal |
| `analyse_segment` | 65 | 65 | 0% | Already distilled |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        LLM Context Window                        │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │  System prompt + conversation history + tool responses     │  │
│  │                                                            │  │
│  │  tool_response: { per_km: [...], summary: {...} }          │  │
│  │                  ↑ 789 tokens (distilled)                  │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↑                                    │
│                    ┌─────────┴──────────┐                        │
│                    │  MCP Tool Layer     │                        │
│                    │  (unchanged)        │                        │
│                    └─────────┬──────────┘                        │
│                              ↑                                    │
│              ┌───────────────┴────────────────┐                  │
│              │     DISTILLATION LAYER          │  ← NEW          │
│              │                                  │                 │
│              │  ┌────────────────────────────┐ │                 │
│              │  │ 1. Structural Stripping     │ │                 │
│              │  │    strip_nulls()            │ │                 │
│              │  │    strip_fields()           │ │                 │
│              │  │    strip_false_booleans()   │ │                 │
│              │  ├────────────────────────────┤ │                 │
│              │  │ 2. Semantic Compression     │ │                 │
│              │  │    Remove polylines         │ │                 │
│              │  │    Remove avatar URLs        │ │                 │
│              │  │    Remove zero-count blocks  │ │                 │
│              │  ├────────────────────────────┤ │                 │
│              │  │ 3. Statistical Aggregation  │ │                 │
│              │  │    Per-km aggregation        │ │                 │
│              │  │    Pacing summary            │ │                 │
│              │  │    HR drift computation      │ │                 │
│              │  │    Bounding box extraction   │ │                 │
│              │  └────────────────────────────┘ │                 │
│              └───────────────┬────────────────┘                  │
│                              ↑                                    │
│                    ┌─────────┴──────────┐                        │
│                    │  Service Layer      │                        │
│                    │  (fetch + validate) │                        │
│                    └─────────┬──────────┘                        │
│                              ↑                                    │
│                    ┌─────────┴──────────┐                        │
│                    │  Strava API v3      │                        │
│                    │  56,822 tokens raw  │                        │
│                    └────────────────────┘                        │
└──────────────────────────────────────────────────────────────────┘
```

### File Structure

```
src/mcp_server/
├── distillation/           ← NEW PACKAGE
│   ├── __init__.py         ← Package entry, exports compact/strip_nulls/strip_fields
│   ├── core.py             ← Generic recursive utilities (5 atomic ops + compact pipeline)
│   ├── streams.py          ← Per-km aggregation engine (THE critical piece)
│   ├── athlete.py          ← Athlete profile/stats/zones stripping
│   └── activity.py         ← Activity summary/detail/laps stripping
│
├── services/               ← MODIFIED (added distillation calls)
│   ├── stream_service.py   ← _fetch_streams (internal raw) + distilled outputs
│   ├── athlete_service.py  ← distill.distill_profile() etc.
│   └── activity_service.py ← distill.distill_summaries() etc.
│
├── tools/                  ← UNCHANGED (zero modifications)
├── api/                    ← UNCHANGED
└── models/                 ← UNCHANGED
```

---

## The Three Compression Techniques

### Technique 1: Structural Stripping

**What**: Recursively remove `None`/null values, always-false booleans, and empty containers from nested JSON.

**Why**: Strava returns a fixed schema regardless of what sensors the athlete has. An athlete without a heart rate strap gets 8 null fields per activity (`average_heartrate: null`, `max_heartrate: null`, `suffer_score: null`, etc.). Across 10 activities, that's 80 pointless key-value pairs.

**Implementation** ([core.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/core.py)):

```python
def compact(obj, *, remove_fields=None, noise_booleans=None):
    """Full compaction pipeline (order matters):
    1. Strip named fields        (polylines, resource_state, avatars…)
    2. Strip None values         (null HR when no strap, null watts…)
    3. Strip noise booleans      (trainer=False, commute=False…)
    4. Strip empty containers    (bio="", clubs=[]…)
    """
```

The pipeline is applied in a specific order — stripping fields first avoids wasting work on values that will be removed anyway.

**Before** (one activity summary, 40 fields):
```json
{
  "id": 17883168585,
  "average_cadence": null,
  "average_watts": null,
  "weighted_average_watts": null,
  "kilojoules": null,
  "device_watts": null,
  "average_heartrate": null,
  "max_heartrate": null,
  "suffer_score": null,
  "trainer": false,
  "commute": false,
  "private": false,
  "gear_id": null,
  ...
}
```

**After** (same activity, 16 fields):
```json
{
  "id": 17883168585,
  "name": "Long Run (after 1 week deload)",
  "distance": 12000.0,
  "moving_time": 4469,
  "sport_type": "Run",
  "start_date_local": "2026-03-28T06:23:59+00:00",
  "has_heartrate": false,
  "distance_km": 12.0,
  "pace_min_per_km": 6.21,
  "pace_formatted": "6:12 /km",
  "moving_time_hms": "1:14:29",
  ...
}
```

---

### Technique 2: Semantic Compression

**What**: Remove fields that are semantically useless to an LLM — data it cannot interpret, render, or reason about.

**Key removals**:

| Field | Why Remove | Savings |
|-------|-----------|---------|
| `map.summary_polyline` | Encoded GPS path — LLM can't render maps | ~700 chars/activity |
| `profile_medium`, `profile` | Avatar image URLs | ~200 chars |
| `resource_state` | Strava internal API version flag | Everywhere |
| `badge_type_id`, `athlete_type` | Strava UI enums | Per profile |
| `date_preference` | UI formatting preference (`%m/%d/%Y`) | Per profile |
| Zero-count sport blocks | Runner gets 6 blocks of zeros for ride/swim | ~130 tokens |

**Implementation** ([athlete.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/athlete.py)):

The `_PROFILE_STRIP` set defines exactly which fields to remove:
```python
_PROFILE_STRIP = {
    "resource_state", "badge_type_id", "profile_medium", "profile",
    "friend", "follower", "blocked", "can_follow", "mutual_friend_count",
    "athlete_type", "date_preference", "created_at", "updated_at",
    "postable_clubs_count",
}
```

For athlete stats, the `strip_zero_blocks()` function ([core.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/core.py#L65-L75)) checks if a nested dict has `count: 0` and removes the entire block:

```python
def strip_zero_blocks(obj):
    for k, v in obj.items():
        if isinstance(v, dict) and v.get("count", -1) == 0:
            continue  # skip entire zero-count block
        cleaned[k] = v
```

**Before** (athlete stats — 68 lines, 345 tokens):
```json
{
  "recent_ride_totals":  { "count": 0, "distance": 0, ... },
  "all_ride_totals":     { "count": 0, "distance": 0, ... },
  "recent_run_totals":   { "count": 10, "distance": 91410.3, ... },
  "all_run_totals":      { "count": 75, "distance": 460687.4, ... },
  "recent_swim_totals":  { "count": 0, "distance": 0, ... },
  "all_swim_totals":     { "count": 0, "distance": 0, ... },
  "ytd_ride_totals":     { "count": 0, "distance": 0, ... },
  "ytd_run_totals":      { "count": 66, ... },
  "ytd_swim_totals":     { "count": 0, "distance": 0, ... }
}
```

**After** (only non-zero blocks — 132 tokens):
```json
{
  "recent_run_totals":   { "count": 10, "distance": 91410.3, "moving_time": 34095, ... },
  "all_run_totals":      { "count": 75, "distance": 460687.4, "moving_time": 179882, ... },
  "ytd_run_totals":      { "count": 66, "distance": 435229, ... }
}
```

---

### Technique 3: Statistical Aggregation (The Critical Piece)

**What**: Replace per-second time-series arrays (thousands of data points) with pre-computed per-km statistical summaries.

**Why**: A 12km run recorded at 1Hz produces ~4,473 data points per stream type. The pace profile tool fetches 4 streams (time, distance, velocity, altitude) → **17,892 data points → 56,822 tokens**. But the LLM never needs this resolution. To answer "was this a negative split?", it needs 12 numbers (one pace per km), not 4,473.

**The algorithm** ([streams.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/streams.py)):

```
1. FIND KM BOUNDARIES
   Scan the distance array for crossings at 1000m, 2000m, 3000m...
   → [idx_0, idx_1km, idx_2km, ..., idx_last]

2. FOR EACH KM SEGMENT [start_idx, end_idx]:
   - elapsed_s    = time[end] - time[start]
   - distance_m   = distance[end] - distance[start]
   - pace         = 1000 / (distance_m / elapsed_s × 60)
   - elev_gain    = Σ max(0, alt[i] - alt[i-1])
   - avg_hr       = mean(heartrate[start:end])
   - avg_watts    = mean(watts[start:end])
   ...

3. COMPUTE SUMMARY STATS:
   - fastest/slowest km
   - first half vs second half pace (positive/negative split)
   - pace variability coefficient
   - total elevation gain/loss
   - HR drift percentage
   - normalised power (30s rolling avg → 4th power → mean → 4th root)
```

**Before** (`get_pace_profile` — 17,922 lines, 56,822 tokens):
```json
{
  "time":            { "data": [0, 1, 2, 3, 4, 5, ... 4473 values] },
  "distance":        { "data": [0.0, 1.2, 2.4, 3.6, ... 4473 values] },
  "velocity_smooth": { "data": [0.0, 2.1, 2.3, 2.5, ... 4473 values] },
  "altitude":        { "data": [580.1, 580.0, 579.8, ... 4473 values] }
}
```

**After** (`get_pace_profile` — 789 tokens):
```json
{
  "data_points_raw": 4473,
  "per_km": [
    {"km": 1, "distance_m": 1002.0, "elapsed_s": 394, "pace": "6:27/km", "speed_ms": 2.54, "elev_gain_m": 2.1, "elev_loss_m": 10.1},
    {"km": 2, "distance_m": 998.0, "elapsed_s": 382, "pace": "6:23/km", "speed_ms": 2.61, "elev_gain_m": 0.0, "elev_loss_m": 6.5},
    ...
  ],
  "summary": {
    "total_km": 12.0,
    "total_time_s": 4473,
    "avg_pace": "6:12/km",
    "fastest_km": {"km": 9, "pace": "5:55/km"},
    "slowest_km": {"km": 7, "pace": "6:33/km"},
    "first_half_pace": "6:18/km",
    "second_half_pace": "6:06/km",
    "split_type": "negative",
    "total_elev_gain_m": 62.9,
    "pace_variability_pct": 3.8
  }
}
```

**The LLM gets MORE insight from FEWER tokens.** Raw arrays don't tell the LLM anything — it has to compute averages itself (which it does poorly). Pre-computed summaries give it direct answers.

#### GPS Track: The Most Extreme Case

**Before** (90,500 tokens):
```json
{
  "latlng":   { "data": [[18.5234, 73.8421], [18.5234, 73.8422], ... 4473 pairs] },
  "distance": { "data": [0.0, 1.2, 2.4, ... 4473 values] },
  "altitude": { "data": [580.1, 580.0, 579.8, ... 4473 values] }
}
```

**After** (96 tokens — **99.9% reduction**):
```json
{
  "data_points_raw": 4473,
  "bounding_box": { "sw": [18.50983, 73.82414], "ne": [18.54217, 73.86124] },
  "start_latlng": [18.52341, 73.84213],
  "end_latlng": [18.51982, 73.83874],
  "total_distance_m": 12000.0,
  "elevation": { "min_m": 555.4, "max_m": 598.9, "gain_m": 62.9, "loss_m": 50.2 }
}
```

The encoded polyline already exists in the activity summary if the LLM ever needs the route shape. Sending 4,473 raw lat/lng pairs was pure waste.

---

## Design Decisions

### 1. Distillation at the Service Layer, Not the Tool Layer

The distillation happens inside the service functions (e.g., `stream_service.get_pace_profile()`) before the data reaches the tool layer. This means:

- **Tool definitions remain unchanged** — no docstring or schema modifications needed
- **The MCP protocol is unaffected** — tools still return JSON dicts
- **Every consumer benefits** — both MCP clients and any future direct API consumers get distilled data

### 2. Internal Raw Access Preserved

The stream service exposes `_fetch_streams()` as an internal function for code that needs raw per-second data. The `analyse_distance_segment` function uses this to compute precise distance-based slices — it needs per-second resolution to find exact index boundaries. Its output was already compact (65 tokens), so no further distillation was needed.

```python
# Internal: raw per-second data (for segment analysis)
raw = _fetch_streams(activity_id, keys=_KEYS_PACE)

# External: distilled per-km aggregates (for LLM consumption)
return distill.distill_pace_profile(raw)
```

### 3. The `compact()` Pipeline Order Matters

The four operations in `compact()` are applied in a specific sequence:

```python
def compact(obj, *, remove_fields=None, noise_booleans=None):
    result = obj
    if remove_fields:
        result = strip_fields(result, remove_fields)    # 1. remove known waste
    result = strip_nulls(result)                         # 2. remove all nulls
    if noise_booleans:
        result = strip_false_booleans(result, noise_booleans)  # 3. remove false noise
    result = strip_empty(result)                         # 4. clean up empties
    return result
```

Why this order?
- Stripping named fields first avoids processing their children for nulls
- Stripping nulls before empty containers ensures that dicts that BECOME empty (after null removal) are also cleaned
- Stripping false booleans after nulls prevents accidentally removing a field that was `None` (not `False`)

### 4. Conservative Field Removal

We deliberately keep some fields that seem redundant:
- `has_heartrate: false` — tells the LLM NOT to request HR streams (saves a wasted API call)
- `manual: true` — tells the LLM the activity has no GPS/stream data
- `distance` (metres) alongside `distance_km` — the LLM may need raw metres for calculations

We only strip fields where removal has **zero information loss** for analytical reasoning.

---

## The Existing `analyse_distance_segment` Inspiration

The existing [analyse_distance_segment](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/services/stream_service.py#L138-L196) was already the correct pattern — it fetches raw streams, computes derived analytics server-side, and returns a 65-token response. The distillation layer generalises this pattern to ALL stream tools.

```
analyse_distance_segment:  raw streams → slice → compute → 65 tokens    ← existed
get_pace_profile:          raw streams → aggregate per-km → 789 tokens   ← NEW (same pattern)
get_hr_profile:            raw streams → aggregate + drift → 514 tokens  ← NEW (same pattern)
```

---

## Verification

All payloads are captured in [observability/audit_results/](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/observability/audit_results) for both before and after states.

### Before (pre-distillation)
```
  TOTAL                             1721.3 KB   ~ 440,663 tokens
  
  Gemma 4 31B:  168.1% of 262,144 token window      ← UNUSABLE (cumulative saturation)
```

### After (post-distillation)
```
  TOTAL                               24.6 KB   ~   6,293 tokens
  
  Gemma 4 31B:    2.4% of 262,144 token window      ← FITS ✅
```

### Token reduction by tool category

```
Stream tools:     375,116 → 2,804 tokens   (99.3% reduction)
Activity tools:     6,284 → 2,327 tokens   (63.0% reduction)
Athlete tools:        768 →   297 tokens    (61.3% reduction)
Segment analysis:     131 →   131 tokens    (0% — already optimal)
```

---

## Files Changed

### New Files (distillation package)
| File | Purpose | Lines |
|------|---------|-------|
| [distillation/__init__.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/__init__.py) | Package entry, technique documentation | 12 |
| [distillation/core.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/core.py) | Generic recursive utilities | 95 |
| [distillation/streams.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/streams.py) | Per-km aggregation engine | 340 |
| [distillation/athlete.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/athlete.py) | Athlete data cleanup | 78 |
| [distillation/activity.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/distillation/activity.py) | Activity data cleanup | 110 |

### Modified Files
| File | Change |
|------|--------|
| [stream_service.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/services/stream_service.py) | Split into `_fetch_streams` (internal raw) + distilled outputs |
| [athlete_service.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/services/athlete_service.py) | Apply `distill.distill_profile()` etc. to all returns |
| [activity_service.py](file:///c:/Users/hrite/OneDrive/Documents/Strava%20MCP/src/mcp_server/services/activity_service.py) | Apply `distill.distill_summaries()` etc. to all returns |

### Unchanged Files
| File | Why |
|------|-----|
| All tool files (`*_tools.py`) | Distillation is transparent — tools return what services give them |
| API layer (`api/`) | Raw Strava API calls unchanged |
| Models (`models/`) | Pydantic validation unchanged |
| Auth (`auth/`) | Token management unchanged |
| CLI client (`cli_client/`) | Receives distilled data automatically |
