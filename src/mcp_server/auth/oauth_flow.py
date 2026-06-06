"""OAuth 2.0 flow for Strava."""

from __future__ import annotations

import os
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import httpx

from mcp_server.auth import token_store

AUTHORIZE_URL = "https://www.strava.com/oauth/authorize"
TOKEN_URL = "https://www.strava.com/oauth/token"
PORT = 8000
REDIRECT_URI = f"http://localhost:{PORT}"


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the redirect callback from Strava."""
    
    # Class-level state used to communicate with the main thread
    auth_code: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        
        if "error" in params:
            OAuthCallbackHandler.error = params["error"][0]
            self.wfile.write(b"<html><body><h1>Authentication Error</h1><p>You can close this tab.</p></body></html>")
        elif "code" in params:
            OAuthCallbackHandler.auth_code = params["code"][0]
            self.wfile.write(b"<html><body><h1>Authentication Successful!</h1><p>You can close this tab and return to the application.</p></body></html>")
        else:
            OAuthCallbackHandler.error = "No code or error in callback"
            self.wfile.write(b"<html><body><h1>Unknown Error</h1><p>You can close this tab.</p></body></html>")
            
        # Stop the server after responding
        threading.Thread(target=self.server.shutdown).start()

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default HTTP logging."""
        pass


def run_oauth_flow(
    client_id: str,
    client_secret: str,
    open_browser: bool = True,
    timeout_seconds: int = 180,
) -> dict[str, Any]:
    """Execute the full OAuth flow."""
    # Reset state
    OAuthCallbackHandler.auth_code = None
    OAuthCallbackHandler.error = None
    
    # 1. Prepare the authorize URL
    # Required scope is activity:read_all,profile:read_all
    scope = "activity:read_all,profile:read_all"
    auth_params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "approval_prompt": "force",
        "scope": scope,
    }
    url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(auth_params)}"
    
    # 2. Start the local server
    server = HTTPServer(("localhost", PORT), OAuthCallbackHandler)
    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()
    
    # 3. Open browser
    if open_browser:
        webbrowser.open(url)
        
    # 4. Wait for callback
    start_time = time.time()
    while server_thread.is_alive():
        if time.time() - start_time > timeout_seconds:
            server.shutdown()
            return {"success": False, "message": "Timed out waiting for authentication callback."}
        time.sleep(0.5)
        
    # 5. Handle response
    if OAuthCallbackHandler.error:
        return {"success": False, "message": f"Authentication error: {OAuthCallbackHandler.error}"}
        
    code = OAuthCallbackHandler.auth_code
    if not code:
        return {"success": False, "message": "Authentication failed: No code received."}
        
    # 6. Exchange code for token
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                },
            )
            response.raise_for_status()
            token_payload = response.json()
            
        token_store.save(token_payload)
        
        return {
            "success": True,
            "message": "Authentication successful.",
            "token_metadata": token_store.public_metadata(token_payload),
            "granted_scope": scope,
        }
    except Exception as e:
        return {"success": False, "message": f"Failed to exchange token: {str(e)}"}
