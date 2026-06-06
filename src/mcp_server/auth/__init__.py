"""Auth package."""

from __future__ import annotations

import functools
import os
from typing import Any, Callable

from mcp_server.auth import token_store

def require_auth(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to require authentication before executing a tool."""
    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        if not token_store.token_exists():
            return {
                "error": "Not authenticated. Please run the `login` tool first."
            }
            
        cid = os.environ.get("STRAVA_CLIENT_ID", "")
        sec = os.environ.get("STRAVA_CLIENT_SECRET", "")
        
        if not cid or not sec:
            return {
                "error": "Missing STRAVA_CLIENT_ID or STRAVA_CLIENT_SECRET in environment variables."
            }
            
        try:
            # This will refresh the token if necessary
            token_store.get_valid_token(cid, sec)
        except Exception as e:
            return {
                "error": f"Authentication failed: {str(e)}. Please run the `login` tool again."
            }
            
        return func(*args, **kwargs)
    return wrapper
