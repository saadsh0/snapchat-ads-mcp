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

CLIENT_ID     = os.environ.get("SNAPCHAT_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("SNAPCHAT_CLIENT_SECRET", "")
REDIRECT_URI  = "https://example.com"
TOKEN_URL     = "https://accounts.snapchat.com/login/oauth2/access_token"
AUTH_URL      = "https://accounts.snapchat.com/login/oauth2/authorize"
CONFIG_FILE   = os.path.join(os.path.dirname(__file__), "config.json")


def main():
    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: SNAPCHAT_CLIENT_ID and SNAPCHAT_CLIENT_SECRET environment variables are not set.")
        print("Set them first:\n  export SNAPCHAT_CLIENT_ID=your_client_id")
        print("  export SNAPCHAT_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    print("=" * 60)
    print("  Snapchat Ads MCP — Authorization Setup")
    print("=" * 60)
    print()

    # Step 1: Build auth URL
    auth_link = (
        f"{AUTH_URL}"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope=snapchat-marketing-api"
        f"&state=sigma_digital_mcp"
    )

    print("Step 1: Opening Snapchat authorization page in your browser...")
    print()
    print("  If it doesn't open automatically, copy this URL:")
    print(f"  {auth_link}")
    print()
    webbrowser.open(auth_link)

    print("Step 2: Log in with your Snapchat Business account and click 'Allow'.")
    print()
    print("Step 3: You'll be redirected to example.com — the page won't load,")
    print("        but the URL in your browser will look like:")
    print("        https://example.com/?code=XXXXXXXX&state=sigma_digital_mcp")
    print()

    # Step 2: Get code from user
    redirected = input("Paste the FULL redirect URL here: ").strip()

    if "code=" not in redirected:
        print("ERROR: Could not find 'code=' in the URL. Please try again.")
        return

    code = redirected.split("code=")[1].split("&")[0]
    print(f"\n✅ Got auth code: {code[:10]}...")

    # Step 3: Exchange code for tokens
    print("\nExchanging code for access tokens...")
    resp = httpx.post(TOKEN_URL, data={
        "grant_type":    "authorization_code",
        "client_id":     CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code":          code,
        "redirect_uri":  REDIRECT_URI,
    })

    if resp.status_code != 200:
        print(f"ERROR: Token exchange failed ({resp.status_code})")
        print(resp.text)
        return

    tokens = resp.json()
    config = {
        "access_token":  tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at":    time.time() + tokens.get("expires_in", 1800),
    }

    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)

    print("\n✅ Tokens saved to config.json")
    print("✅ Authorization complete!")
    print()
    print("You can now start the MCP server. It will auto-refresh tokens.")
    print("Next step: Follow SETUP.md to connect this to Claude.")


if __name__ == "__main__":
    main()
