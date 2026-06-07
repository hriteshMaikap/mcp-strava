"""Athlete response distillation.

Strips social/UI metadata, avatar URLs, and zero-count sport blocks
from athlete profile, stats, zones, gear, and club responses.
"""

from __future__ import annotations

from typing import Any

from mcp_server.distillation.core import compact, strip_zero_blocks


# ---------------------------------------------------------------------------
# Field sets
# ---------------------------------------------------------------------------

# Fields the LLM never needs from GET /athlete
_PROFILE_STRIP: set[str] = {
    "resource_state",
    "badge_type_id",
    "profile_medium",       # avatar URL — LLM can't render images
    "profile",              # full-size avatar URL
    "friend",               # social relation to viewer (always null for self)
    "follower",             # same
    "blocked",
    "can_follow",
    "mutual_friend_count",
    "athlete_type",         # internal Strava enum (0=cyclist, 1=runner)
    "date_preference",      # UI formatting preference
    "created_at",           # account creation date
    "updated_at",           # last profile update
    "postable_clubs_count",
}


# ---------------------------------------------------------------------------
# Distillation functions — one per tool
# ---------------------------------------------------------------------------

def distill_profile(raw: dict[str, Any]) -> dict[str, Any]:
    """Distill GET /athlete — strip social/UI noise.

    Keeps: id, username, firstname, lastname, city, country, sex,
    measurement_preference, weight, ftp, premium, summit, bikes, shoes,
    follower_count, friend_count.
    """
    result = compact(raw, remove_fields=_PROFILE_STRIP)

    # Strip empty bio (athlete hasn't set one)
    if not result.get("bio"):
        result.pop("bio", None)

    # Strip empty clubs list (separate tool exists for this)
    if not result.get("clubs"):
        result.pop("clubs", None)

    return result


def distill_stats(raw: dict[str, Any]) -> dict[str, Any]:
    """Distill GET /athletes/{id}/stats — drop zero-count sport blocks.

    A runner-only athlete returns zeros for ride and swim totals across
    all 3 time windows (recent/ytd/all) — that's 6 empty blocks × 6 fields
    = 36 wasted key-value pairs. This strips them entirely.
    """
    result = strip_zero_blocks(raw)
    return compact(result)


def distill_zones(raw: dict[str, Any]) -> dict[str, Any]:
    """Distill GET /athlete/zones — minimal, pass through after null strip."""
    return compact(raw)


def distill_gear(raw: dict[str, Any]) -> dict[str, Any]:
    """Distill GET /gear/{id} — strip resource_state."""
    return compact(raw, remove_fields={"resource_state"})


def distill_clubs(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Distill GET /athlete/clubs — strip resource_state from each club."""
    return compact(raw, remove_fields={"resource_state"})
