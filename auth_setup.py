#!/usr/bin/env python3
"""
Snapchat Ads MCP — One-time Auth Setup
Run this ONCE to connect your Snapchat account.
After this, the MCP server handles token refresh automatically.

Spins up a local web server on http://localhost:8080 so you never
have to copy-paste a redirect URL — just click Allow in Snapchat
and the script captures the code and saves your tokens automatically.
"""

import json
import os
import sys
import time
import threading
import webbrowser
import httpx
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

CLIENT_ID     = os.environ.get("SNAPCHAT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SNAPCHAT_CLIENT_SECRET", "")
REDIRECT_URI  = "http://localhost:8080"
TOKEN_URL     = "https://accounts.snapchat.com/login/oauth2/access_token"
AUTH_URL      = "https://accounts.snapchat.com/login/oauth2/authorize"
CONFIG_FILE   = os.path.join(os.path.dirname(__file__), "config.json")

# Shared state between the HTTP handler and main thread
_auth_code = None
_auth_error = None
_server_done = threading.Event()


class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth redirect from Snapchat."""

    def do_GET(self):
        global _auth_code, _auth_error

        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)

        if "error" in params:
            _auth_error = params["error"][0]
            self._respond("Authorization failed: " + _auth_error, success=False)
        elif "code" in params:
            _auth_code = params["code"][0]
            self._respond("Authorization successful! You can close this tab.", success=True)
        else:
            self._respond("Unexpected callback. Please try again.", success=False)

        _server_done.set()

    def _respond(self, message: str, success: bool):
        color = "#22c55e" if success else "#ef4444"
        icon  = "✅" if success else "❌"
        body  = f"""<!DOCTYPE html>
<html>
<head><title>Snapchat Ads MCP</title></head>
<body style="font-family:sans-serif;text-align:center;padding:80px;background:#0f0f0f;color:#fff;">
  <h1 style="color:{color};font-size:48px;">{icon}</h1>
  <h2>{message}</h2>
  <p style="color:#aaa;">Return to your terminal — setup is completing automatically.</p>
</body>
</html>"""
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, format, *args):
        pass  # Silence default HTTP request logs


def start_local_server() -> HTTPServer:
    server = HTTPServer(("localhost", 8080), OAuthCallbackHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: SNAPCHAT_CLIENT_ID and SNAPCHAT_CLIENT_SECRET environment variables are not set.")
        print("\nSet them first:")
        print("  export SNAPCHAT_CLIENT_ID=your_client_id")
        print("  export SNAPCHAT_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    print("=" * 60)
    print("  Snapchat Ads MCP — Authorization Setup")
    print("=" * 60)
    print()

    # Step 1: Start local callback server
    print("Starting local callback server on http://localhost:8080 ...")
    server = start_local_server()

    # Step 2: Build auth URL
    auth_link = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=snapchat-marketing-api"
        f"&state=sigma_digital_mcp"
    )

    print("Opening Snapchat authorization page in your browser...")
    print()
    print("  If it doesn't open automatically, visit:")
    print(f"  {auth_link}")
    print()
    print("Waiting for you to authorize in the browser...")
    webbrowser.open(auth_link)

    # Step 3: Wait for callback (timeout after 3 minutes)
    received = _server_done.wait(timeout=180)
    server.shutdown()

    if not received:
        print("\nERROR: Timed out waiting for authorization. Please try again.")
        sys.exit(1)

    if _auth_error:
        print(f"\nERROR: Snapchat returned an error: {_auth_error}")
        sys.exit(1)

    print(f"\n✅ Authorization code received.")

    # Step 4: Exchange code for tokens
    print("Exchanging code for access tokens...")
    resp = httpx.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          _auth_code,
        "redirect_uri":  REDIRECT_URI,
    })

    if resp.status_code != 200:
        print(f"\nERROR: Token exchange failed ({resp.status_code})")
        print(resp.text)
        sys.exit(1)

    tokens = resp.json()
    config = {
        "access_token":  tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at":    time.time() + tokens.get("expires_in", 1800),
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print("✅ Tokens saved to config.json")
    print("✅ Authorization complete!\n")
    print("You can now start the MCP server — it will auto-refresh tokens from here on.")
    print("Next step: Follow SETUP.md to connect this to Claude.")


if __name__ == "__main__":
    main()
