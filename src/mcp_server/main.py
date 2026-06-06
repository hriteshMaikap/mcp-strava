"""Strava MCP Server — entry point and orchestrator.

Responsibilities:
  1. Load environment config.
  2. Create the FastMCP instance.
  3. Register all tool modules.
  4. Start the server.

No business logic here. This file stays thin by design.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from mcp_server.tools import (
    activity_tools,
    athlete_tools,
    auth_tools,
    segment_tools,
    stream_tools,
)

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
_log = logging.getLogger("strava_mcp.server")

_HOST = os.getenv("MCP_HOST", "127.0.0.1")
_PORT = int(os.getenv("MCP_PORT", "5001"))

# ---------------------------------------------------------------------------
# MCP instance
# ---------------------------------------------------------------------------

mcp = FastMCP("Strava", host=_HOST, port=_PORT)

# ---------------------------------------------------------------------------
# Tool registration — one call per module, alphabetical
# ---------------------------------------------------------------------------

activity_tools.register(mcp)
athlete_tools.register(mcp)
auth_tools.register(mcp)
segment_tools.register(mcp)
stream_tools.register(mcp)

_log.info(
    "Registered tools: activity (%d), athlete, auth, segment, stream",
    5,  # activity tool count
)

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    _log.info("Strava MCP server starting on %s:%d", _HOST, _PORT)
    try:
        mcp.run(transport='sse')
    except Exception:
        _log.exception("Server terminated with error")
        raise


if __name__ == "__main__":
    main()