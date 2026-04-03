import json
import os
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from mcp.server.fastmcp import FastMCP
from dotenv import load_dotenv

load_dotenv()

MCP_HOST = "127.0.0.1"
MCP_PORT = 5001

mcp = FastMCP("Strava", host=MCP_HOST, port=MCP_PORT)

REDIRECT_URI = "http://localhost:8000"
TOKEN_PATH = Path(".strava_token.json")
AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
API_BASE_URL = "https://www.strava.com/api/v3"


def _public_token_metadata(token_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "token_type": token_payload.get("token_type"),
        "expires_at": token_payload.get("expires_at"),
        "expires_in": token_payload.get("expires_in"),
        "athlete": token_payload.get("athlete"),
    }


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    server_version = "StravaOAuth/1.0"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        self.server.auth_result = {
            "state": params.get("state", [None])[0],
            "code": params.get("code", [None])[0],
            "scope": params.get("scope", [None])[0],
            "error": params.get("error", [None])[0],
        }

        if self.server.auth_result["code"]:
            message = "Strava authorization complete. You can close this window."
            status_code = 200
        else:
            message = "Strava authorization failed. You can close this window."
            status_code = 400

        body = message.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def _require_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"Missing required environment variable: {name}")
    return value


def _save_token(payload: dict[str, Any]) -> str:
    TOKEN_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return str(TOKEN_PATH.resolve())


def _load_token() -> dict[str, Any]:
    if not TOKEN_PATH.exists():
        raise FileNotFoundError(
            f"Missing token file at {TOKEN_PATH.resolve()}. Run the login tool first."
        )
    return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))


def _refresh_token(token_payload: dict[str, Any]) -> dict[str, Any]:
    refresh_token = token_payload.get("refresh_token")
    if not refresh_token:
        raise ValueError("Saved token does not include a refresh_token.")

    client_id = _require_env("STRAVA_CLIENT_ID")
    client_secret = _require_env("STRAVA_CLIENT_SECRET")

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
        response.raise_for_status()
        refreshed_payload = response.json()

    _save_token(refreshed_payload)
    return refreshed_payload


def _get_valid_token() -> dict[str, Any]:
    token_payload = _load_token()
    expires_at = token_payload.get("expires_at")
    if expires_at and int(expires_at) <= int(time.time()) + 60:
        token_payload = _refresh_token(token_payload)
    return token_payload


def _strava_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> Any:
    token_payload = _get_valid_token()
    access_token = token_payload.get("access_token")
    if not access_token:
        raise ValueError("Saved token does not include an access_token.")

    cleaned_params = {key: value for key, value in (params or {}).items() if value is not None}

    with httpx.Client(timeout=30.0) as client:
        response = client.request(
            method,
            f"{API_BASE_URL}{path}",
            params=cleaned_params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if response.is_error:
        try:
            detail = response.json()
        except ValueError:
            detail = {"message": response.text}
        raise RuntimeError(
            f"Strava API request failed with HTTP {response.status_code}: {detail}"
        )

    return response.json()


def _build_authorize_url(client_id: str, state: str) -> str:
    query = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "response_type": "code",
            "approval_prompt": "force",
            "scope": "activity:read_all,profile:read_all",
            "state": state,
        }
    )
    return f"{AUTHORIZE_URL}?{query}"


def _start_callback_server() -> HTTPServer:
    server = HTTPServer(("127.0.0.1", 8000), _OAuthCallbackHandler)
    server.auth_result = None
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()
    return server


@mcp.tool()
def login(state: str = "test123", open_browser: bool = True, timeout_seconds: int = 180) -> dict[str, Any]:
    """
    Complete the Strava OAuth login flow for this MCP server.

    Use this when no saved token exists yet, when the saved token is invalid, or when the
    user wants to reconnect Strava. The tool starts a temporary callback listener on
    http://localhost:8000, opens the Strava authorization page, waits for the user to approve
    access, exchanges the returned authorization code for tokens, and saves the token payload
    to a local JSON file for future API calls.

    Args:
        state: OAuth state value used to validate the callback and reduce accidental mismatches.
        open_browser: If true, attempts to open the Strava authorization URL automatically.
            If false, the returned authorize_url can be opened manually.
        timeout_seconds: How long to wait for the browser callback before returning a timeout
            response.

    Returns:
        A dictionary describing whether authorization succeeded, where the token was saved,
        the granted scope, and non-sensitive token metadata such as expiry and athlete details.
    """

    client_id = _require_env("STRAVA_CLIENT_ID")
    client_secret = _require_env("STRAVA_CLIENT_SECRET")
    authorize_url = _build_authorize_url(client_id, state)

    server = _start_callback_server()

    if open_browser:
        webbrowser.open(authorize_url)

    start_time = time.time()
    while server.auth_result is None and (time.time() - start_time) < timeout_seconds:
        time.sleep(0.25)

    if server.auth_result is None:
        server.server_close()
        return {
            "success": False,
            "authorize_url": authorize_url,
            "message": f"Timed out waiting for the callback on {REDIRECT_URI}.",
        }

    auth_result = server.auth_result
    server.server_close()

    if auth_result["error"]:
        return {
            "success": False,
            "authorize_url": authorize_url,
            "message": f"Strava returned an error: {auth_result['error']}",
            "state": auth_result["state"],
        }

    if auth_result["state"] != state:
        return {
            "success": False,
            "authorize_url": authorize_url,
            "message": "State mismatch in OAuth callback.",
            "expected_state": state,
            "received_state": auth_result["state"],
        }

    if not auth_result["code"]:
        return {
            "success": False,
            "authorize_url": authorize_url,
            "message": "No authorization code was returned by Strava.",
            "state": auth_result["state"],
        }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": client_id,
                "client_secret": client_secret,
                "code": auth_result["code"],
                "grant_type": "authorization_code",
            },
        )
        response.raise_for_status()
        token_payload = response.json()

    saved_to = _save_token(token_payload)
    return {
        "success": True,
        "message": "Strava authorization succeeded and the token was saved.",
        "saved_to": saved_to,
        "authorize_url": authorize_url,
        "scope": auth_result["scope"],
        "token_metadata": _public_token_metadata(token_payload),
    }


@mcp.tool()
def list_athlete_activities(
    before: int | None = None,
    after: int | None = None,
    page: int = 1,
    per_page: int = 30,
) -> list[dict[str, Any]]:
    """
    List activities for the authenticated athlete.

    Use this tool when the user asks about recent workouts, activity history, counts, dates,
    names, distance, moving time, elevation, sport type, or when you need to find a relevant
    activity id before calling `get_activity_by_id`.

    The result is a paginated list of Strava SummaryActivity objects. Private "Only Me"
    activities are returned only if the connected token has the `activity:read_all` scope.

    Args:
        before: Optional Unix timestamp. Only activities before this moment are returned.
        after: Optional Unix timestamp. Only activities after this moment are returned.
        page: Page number for pagination. Defaults to 1.
        per_page: Number of activities to return per page. Defaults to 30.

    Returns:
        A list of summary activity dictionaries. Each item can include fields such as `id`,
        `name`, `distance`, `moving_time`, `elapsed_time`, `sport_type`, `start_date`,
        `total_elevation_gain`, `average_speed`, `device_name`, and visibility flags.
    """

    return _strava_request(
        "GET",
        "/athlete/activities",
        params={
            "before": before,
            "after": after,
            "page": page,
            "per_page": per_page,
        },
    )


@mcp.tool()
def get_activity_by_id(id: int, include_all_efforts: bool = False) -> dict[str, Any]:
    """
    Fetch the full detailed representation of a single activity owned by the authenticated athlete.

    Use this when the user asks about one specific workout and you already know its Strava
    activity id, or after using `list_athlete_activities` to identify the most relevant
    activity. This tool is appropriate for detailed questions about splits, laps, map data,
    description, calories, photos, gear, heart rate, power, elevation, or segment efforts.

    Args:
        id: The Strava activity id.
        include_all_efforts: If true, requests all segment efforts for the activity.

    Returns:
        A DetailedActivity dictionary from Strava containing activity metadata and detailed
        metrics such as map polylines, laps, splits, gear, photos, device information, and
        optional segment effort data.
    """

    return _strava_request(
        "GET",
        f"/activities/{id}",
        params={"include_all_efforts": str(include_all_efforts).lower()},
    )


@mcp.tool()
def get_athlete_stats(id: int | None = None) -> dict[str, Any]:
    """
    Return rolled-up statistics for the authenticated athlete.

    Use this when the user asks for aggregate summaries rather than individual activities,
    such as recent totals, year-to-date totals, all-time ride/run/swim totals, biggest ride
    distance, or biggest climb elevation gain.

    This endpoint only includes data from activities with visibility set to Everyone, as
    defined by the Strava API.

    Args:
        id: Optional athlete id. If omitted, the athlete id stored in the saved token is used.

    Returns:
        An ActivityStats dictionary with fields like `recent_ride_totals`, `recent_run_totals`,
        `ytd_ride_totals`, `all_ride_totals`, `biggest_ride_distance`, and
        `biggest_climb_elevation_gain`.
    """

    token_payload = _get_valid_token()
    athlete = token_payload.get("athlete") or {}
    athlete_id = id or athlete.get("id")
    if not athlete_id:
        raise ValueError("Athlete id is required. Re-run login or provide the id explicitly.")

    return _strava_request("GET", f"/athletes/{athlete_id}/stats")

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
