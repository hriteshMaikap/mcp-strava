"""Athlete service."""

from __future__ import annotations

from typing import Any

from mcp_server.api import endpoints, get

def get_profile() -> dict[str, Any]:
    """Fetch the authenticated athlete's profile."""
    return get(endpoints.athlete())

def get_stats(athlete_id: int | None = None) -> dict[str, Any]:
    """Fetch rolled-up activity statistics for an athlete."""
    if athlete_id is None:
        profile = get_profile()
        athlete_id = profile["id"]
        
    return get(endpoints.athlete_stats(athlete_id))

def get_zones() -> dict[str, Any]:
    """Fetch the authenticated athlete's configured training zones."""
    return get(endpoints.athlete_zones())

def get_gear(gear_id: str) -> dict[str, Any]:
    """Fetch detail for a specific piece of gear."""
    return get(endpoints.gear(gear_id))

def get_clubs(page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
    """List clubs the authenticated athlete belongs to."""
    return get(
        endpoints.athlete_clubs(),
        params={"page": page, "per_page": per_page}
    )
