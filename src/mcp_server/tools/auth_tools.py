"""MCP tool: login — Strava OAuth 2.0 authorization."""

from __future__ import annotations

import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from mcp_server.auth import oauth_flow, token_store

def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def login(
        open_browser: bool = True,
        timeout_seconds: int = 180,
    ) -> dict[str, Any]:
        """
        Authenticate with Strava via OAuth 2.0.

        ALWAYS call this tool first — before any other Strava tool.
        If a valid, unexpired token already exists on disk, this returns
        immediately without opening the browser.

        Flow:
          1. Checks disk for an existing valid token  →  returns early if found.
          2. Opens the Strava consent page in the browser.
          3. Waits for the OAuth callback on localhost:8000.
          4. Exchanges the authorization code for access + refresh tokens.
          5. Saves tokens to .strava_token.json for future calls.

        Requires in environment:
          STRAVA_CLIENT_ID     — from https://www.strava.com/settings/api
          STRAVA_CLIENT_SECRET — from the same settings page

        Args:
            open_browser:    (abstract) Auto-launch the Strava consent URL.
                             Set False to receive the URL and open it manually
                             (useful in headless environments).
            timeout_seconds: (abstract) Seconds to wait for the browser callback
                             before giving up. Default 180 (3 minutes).

        Returns:
            success (bool), message, token_metadata (athlete info + expiry),
            and (on first auth) the scope granted by the user.
        """
        # Fast path: reuse existing valid token
        if token_store.token_exists():
            cid = os.getenv("STRAVA_CLIENT_ID", "")
            sec = os.getenv("STRAVA_CLIENT_SECRET", "")
            if cid and sec:
                try:
                    payload = token_store.get_valid_token(cid, sec)
                    return {
                        "success":        True,
                        "message":        "Already authenticated — valid token found.",
                        "token_metadata": token_store.public_metadata(payload),
                    }
                except Exception:
                    pass  # token is broken; fall through to re-auth

        cid = os.environ.get("STRAVA_CLIENT_ID")
        sec = os.environ.get("STRAVA_CLIENT_SECRET")
        if not cid or not sec:
            return {
                "success": False,
                "message": (
                    "STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET must be set "
                    "as environment variables before calling login."
                ),
            }

        return oauth_flow.run_oauth_flow(
            client_id=cid,
            client_secret=sec,
            open_browser=open_browser,
            timeout_seconds=timeout_seconds,
        )
