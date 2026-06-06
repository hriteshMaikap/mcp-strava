"""API layer for Strava MCP."""

from __future__ import annotations

import os
from typing import Any

import httpx

from strava_mcp.auth import token_store

def _get_headers() -> dict[str, str]:
    cid = os.environ.get("STRAVA_CLIENT_ID", "")
    sec = os.environ.get("STRAVA_CLIENT_SECRET", "")
    if not cid or not sec:
        raise RuntimeError("Missing STRAVA_CLIENT_ID or STRAVA_CLIENT_SECRET environment variables")
    
    token = token_store.get_valid_token(cid, sec)
    access_token = token.get("access_token")
    if not access_token:
        raise RuntimeError("Valid token found but missing access_token field")
        
    return {"Authorization": f"Bearer {access_token}"}

def get(url: str, params: dict[str, Any] | None = None) -> Any:
    """Perform an authenticated GET request."""
    # Filter out None values from params
    cleaned_params = {k: v for k, v in (params or {}).items() if v is not None}
    
    with httpx.Client(timeout=30.0) as client:
        response = client.get(url, headers=_get_headers(), params=cleaned_params)
        response.raise_for_status()
        return response.json()

def post(url: str, data: dict[str, Any] | None = None) -> Any:
    """Perform an authenticated POST request."""
    with httpx.Client(timeout=30.0) as client:
        response = client.post(url, headers=_get_headers(), data=data)
        response.raise_for_status()
        return response.json()

def put(url: str, data: dict[str, Any] | None = None) -> Any:
    """Perform an authenticated PUT request."""
    with httpx.Client(timeout=30.0) as client:
        response = client.put(url, headers=_get_headers(), data=data)
        response.raise_for_status()
        return response.json()
