"""Athlete service.

Bridges tool layer to Strava API with distillation applied.
"""

from __future__ import annotations

from typing import Any

from mcp_server.api import endpoints, get
from mcp_server.distillation import athlete as distill


def get_profile() -> dict[str, Any]:
    """Fetch the authenticated athlete's profile (distilled)."""
    return distill.distill_profile(get(endpoints.athlete()))


def get_stats(athlete_id: int | None = None) -> dict[str, Any]:
    """Fetch rolled-up activity statistics (distilled — zero-count blocks removed)."""
    if athlete_id is None:
        # Need raw profile just for the ID — don't distill this intermediate call
        profile = get(endpoints.athlete())
        athlete_id = profile["id"]

    return distill.distill_stats(get(endpoints.athlete_stats(athlete_id)))


def get_zones() -> dict[str, Any]:
    """Fetch the authenticated athlete's configured training zones (distilled)."""
    return distill.distill_zones(get(endpoints.athlete_zones()))


def get_gear(gear_id: str) -> dict[str, Any]:
    """Fetch detail for a specific piece of gear (distilled)."""
    return distill.distill_gear(get(endpoints.gear(gear_id)))


def get_clubs(page: int = 1, per_page: int = 30) -> list[dict[str, Any]]:
    """List clubs the authenticated athlete belongs to (distilled)."""
    return distill.distill_clubs(get(
        endpoints.athlete_clubs(),
        params={"page": page, "per_page": per_page}
    ))
