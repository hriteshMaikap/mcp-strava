"""Token store — single responsibility: persist and refresh OAuth tokens.

All file I/O and refresh logic lives here.  The rest of the codebase calls
`get_valid_token()` and never touches the JSON file directly.
"""

import json
import time
from pathlib import Path
from typing import Any

import httpx

# Find the project root rather than relying on CWD
# We place .strava_token.json next to pyproject.toml
_DIR = Path(__file__).parent.parent.parent
TOKEN_PATH = _DIR / ".strava_token.json"

TOKEN_URL = "https://www.strava.com/oauth/token"
# Refresh if token expires within this many seconds
_EXPIRY_BUFFER_SECS = 120


class TokenNotFoundError(RuntimeError):
    """Raised when no saved token file exists — login required."""


class TokenRefreshError(RuntimeError):
    """Raised when the refresh token call fails."""


def token_exists() -> bool:
    """Return True if a saved token file is present on disk."""
    return TOKEN_PATH.exists()


def load_raw() -> dict[str, Any]:
    """Load the raw token payload from disk.  Raises TokenNotFoundError if absent."""
    if not TOKEN_PATH.exists():
        raise TokenNotFoundError(
            f"No saved token at {TOKEN_PATH.resolve()}. Run the `login` tool first."
        )
    return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))


def save(payload: dict[str, Any]) -> Path:
    """Persist token payload to disk and return the resolved path."""
    TOKEN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return TOKEN_PATH.resolve()


def _is_expired(payload: dict[str, Any]) -> bool:
    expires_at = payload.get("expires_at")
    if expires_at is None:
        return True
    return int(expires_at) <= int(time.time()) + _EXPIRY_BUFFER_SECS


def _refresh(payload: dict[str, Any], client_id: str, client_secret: str) -> dict[str, Any]:
    """Exchange a refresh token for a new access token payload."""
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise TokenRefreshError("Saved token has no refresh_token field; re-login required.")

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )

    if response.is_error:
        raise TokenRefreshError(
            f"Token refresh failed (HTTP {response.status_code}): {response.text}"
        )

    refreshed = response.json()
    save(refreshed)
    return refreshed


def get_valid_token(client_id: str, client_secret: str) -> dict[str, Any]:
    """
    Return a guaranteed-fresh token payload.

    Sequence:
      1. Load from disk  →  raises TokenNotFoundError if absent.
      2. Check expiry    →  refresh transparently if within buffer.
      3. Return payload  →  caller extracts access_token.
    """
    payload = load_raw()
    if _is_expired(payload):
        payload = _refresh(payload, client_id, client_secret)
    return payload


def public_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Return non-sensitive token metadata safe to surface to the LLM."""
    return {
        "token_type": payload.get("token_type"),
        "expires_at": payload.get("expires_at"),
        "athlete": payload.get("athlete"),
    }
