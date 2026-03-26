#!/usr/bin/env python3
"""
Snapchat Ads MCP — One-time Auth Setup
Run this ONCE to connect your Snapchat account.
After this, the MCP server handles token refresh automatically.
"""

import json
import os
import sys
import time
import webbrowser
import httpx
from urllib.parse import urlparse, parse_qs

CLIENT_ID     = os.environ.get("SNAPCHAT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SNAPCHAT_CLIENT_SECRET", "")
REDIRECT_URI  = "https://example.com"
TOKEN_URL     = "https://accounts.snapchat.com/login/oauth2/access_token"
AUTH_URL      = "https://accounts.snapchat.com/login/oauth2/authorize"
CONFIG_FILE   = os.path.join(os.path.dirname(__file__), "config.json")


def extract_code(raw: str) -> str | None:
    """Extract auth code from a full redirect URL or a bare code string."""
    raw = raw.strip()
    if raw.startswith("http"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        return params.get("code", [None])[0]
    # Assume they pasted the code directly
    return raw if raw else None


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: SNAPCHAT_CLIENT_ID and SNAPCHAT_CLIENT_SECRET are not set.")
        print("\nSet them first:")
        print("  export SNAPCHAT_CLIENT_ID=your_client_id")
        print("  export SNAPCHAT_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    print("=" * 60)
    print("  Snapchat Ads MCP — Authorization Setup")
    print("=" * 60)
    print()

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
    webbrowser.open(auth_link)

    print("Steps:")
    print("  1. Log in and click 'Allow' in the browser")
    print("  2. You'll be redirected to a page that looks broken (that's fine)")
    print("  3. Copy the full URL from your browser address bar")
    print("  4. Paste it below\n")

    raw = input("Paste the redirect URL here: ").strip()
    code = extract_code(raw)

    if not code:
        print("\nERROR: Could not find an auth code in what you pasted.")
        print("Make sure you copy the full URL from the browser address bar.")
        sys.exit(1)

    print("\nExchanging code for access tokens...")

    resp = httpx.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
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
    print("You can now start the MCP server — tokens auto-refresh from here on.")
    print("Next step: Follow SETUP.md to connect this to Claude.")


if __name__ == "__main__":
    main()
