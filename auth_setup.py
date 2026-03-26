#!/usr/bin/env python3
"""
Snapchat Ads MCP — One-time Auth Setup

Single user:
    python auth_setup.py

Agency (one run per client):
    python auth_setup.py --client skyline
    python auth_setup.py --client fantastic

Each client gets its own config saved to clients/{name}/config.json,
with the org ID auto-detected and locked in at setup time.
"""

import argparse
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
API_BASE      = "https://adsapi.snapchat.com/v1"


def extract_code(raw: str) -> str | None:
    raw = raw.strip()
    if raw.startswith("http"):
        parsed = urlparse(raw)
        params = parse_qs(parsed.query)
        return params.get("code", [None])[0]
    return raw if raw else None


def discover_org(access_token: str) -> str | None:
    """
    Auto-discover the org ID from the account.
    If multiple orgs exist, prompts user to pick one.
    Returns the selected org_id, or None if discovery fails.
    """
    try:
        resp = httpx.get(
            f"{API_BASE}/me/organizations",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        resp.raise_for_status()
        orgs = resp.json().get("organizations", [])

        if not orgs:
            print("⚠️  No organizations found for this account.")
            return None

        if len(orgs) == 1:
            org = orgs[0].get("organization", orgs[0])
            org_id = org.get("id")
            org_name = org.get("name", "Unknown")
            print(f"✅ Organization auto-detected: {org_name} ({org_id})")
            return org_id

        # Multiple orgs — let user choose
        print("\nMultiple organizations found:")
        for i, o in enumerate(orgs):
            org = o.get("organization", o)
            print(f"  [{i + 1}] {org.get('name', 'Unknown')} — {org.get('id')}")

        while True:
            choice = input("\nWhich org to lock this config to? (enter number): ").strip()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(orgs):
                    org = orgs[idx].get("organization", orgs[idx])
                    return org.get("id")
            except ValueError:
                pass
            print("Invalid choice. Please enter a number from the list.")

    except Exception as ex:
        print(f"⚠️  Could not auto-detect org: {ex}")
        print("   You can set it manually later via SNAPCHAT_CONFIG_FILE env var.")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Snapchat Ads MCP — Authorization Setup"
    )
    parser.add_argument(
        "--client",
        type=str,
        default=None,
        metavar="NAME",
        help="Client name for agency use (e.g. --client skyline). "
             "Saves config to clients/skyline/config.json.",
    )
    args = parser.parse_args()

    if not CLIENT_ID or not CLIENT_SECRET:
        print("ERROR: SNAPCHAT_CLIENT_ID and SNAPCHAT_CLIENT_SECRET are not set.")
        print("\nSet them first:")
        print("  export SNAPCHAT_CLIENT_ID=your_client_id")
        print("  export SNAPCHAT_CLIENT_SECRET=your_client_secret")
        sys.exit(1)

    # Determine where to save config
    base_dir = os.path.dirname(os.path.abspath(__file__))
    if args.client:
        client_dir = os.path.join(base_dir, "clients", args.client)
        os.makedirs(client_dir, exist_ok=True)
        config_file = os.path.join(client_dir, "config.json")
        label = f"client: {args.client}"
    else:
        config_file = os.path.join(base_dir, "config.json")
        label = "single user"

    print("=" * 60)
    print(f"  Snapchat Ads MCP — Authorization Setup ({label})")
    print("=" * 60)
    print()

    # Build auth URL
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
    print("✅ Tokens received.\n")

    # Auto-discover and lock org ID
    print("Detecting your organization...")
    org_id = discover_org(tokens["access_token"])

    config = {
        "access_token":  tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at":    time.time() + tokens.get("expires_in", 1800),
    }
    if org_id:
        config["org_id"] = org_id

    with open(config_file, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\n✅ Config saved to: {config_file}")
    if org_id:
        print(f"✅ Org ID locked: {org_id}")
    print("✅ Authorization complete!\n")

    if args.client:
        print("─" * 60)
        print(f"Add this to your claude_desktop_config.json:\n")
        print(f'  "snapchat-{args.client}": {{')
        print(f'    "command": "python3",')
        print(f'    "args": ["{base_dir}/server.py"],')
        print(f'    "env": {{')
        print(f'      "SNAPCHAT_CLIENT_ID": "{CLIENT_ID}",')
        print(f'      "SNAPCHAT_CLIENT_SECRET": "your_secret",')
        print(f'      "SNAPCHAT_CONFIG_FILE": "{config_file}"')
        print(f'    }}')
        print(f'  }}')
        print("─" * 60)
    else:
        print("Next step: Follow SETUP.md to connect this to Claude.")


if __name__ == "__main__":
    main()
