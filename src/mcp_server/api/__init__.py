"""API layer for Strava MCP.

Uses a module-level persistent httpx.Client to reuse TCP connections
and avoid Strava rate-limit connection resets (WinError 10054).
Includes automatic retry with exponential backoff for transient errors.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx

from mcp_server.auth import token_store

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Persistent HTTP client — reuses connections across requests
# ---------------------------------------------------------------------------

_client = httpx.Client(
    timeout=30.0,
    limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
)

_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1.0  # seconds; doubles each retry


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


def _request_with_retry(
    method: str,
    url: str,
    **kwargs: Any,
) -> httpx.Response:
    """Execute an HTTP request with retry + exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            response = _client.request(method, url, **kwargs)
            response.raise_for_status()
            return response
        except (httpx.ConnectError, httpx.RemoteProtocolError, ConnectionError, OSError) as exc:
            last_exc = exc
            wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
            _log.warning(
                "Transient error on %s %s (attempt %d/%d): %s — retrying in %.1fs",
                method, url, attempt + 1, _MAX_RETRIES, exc, wait,
            )
            time.sleep(wait)
    raise last_exc  # type: ignore[misc]


def get(url: str, params: dict[str, Any] | None = None) -> Any:
    """Perform an authenticated GET request with retry."""
    # Filter out None values from params
    cleaned_params = {k: v for k, v in (params or {}).items() if v is not None}
    response = _request_with_retry("GET", url, headers=_get_headers(), params=cleaned_params)
    return response.json()


def post(url: str, data: dict[str, Any] | None = None) -> Any:
    """Perform an authenticated POST request with retry."""
    response = _request_with_retry("POST", url, headers=_get_headers(), data=data)
    return response.json()


def put(url: str, data: dict[str, Any] | None = None) -> Any:
    """Perform an authenticated PUT request with retry."""
    response = _request_with_retry("PUT", url, headers=_get_headers(), data=data)
    return response.json()

