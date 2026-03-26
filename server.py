#!/usr/bin/env python3
"""
Snapchat Ads MCP Server
Analyze campaign performance and take actions on Snapchat Ads via Claude.
"""

import asyncio
import json
import os
import time
import httpx
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict
from mcp.server.fastmcp import FastMCP

# ── Server Init ──────────────────────────────────────────────────────────────
mcp = FastMCP("snapchat_ads_mcp")

# ── Constants ────────────────────────────────────────────────────────────────
CLIENT_ID     = os.environ.get("SNAPCHAT_CLIENT_ID",     "")
CLIENT_SECRET = os.environ.get("SNAPCHAT_CLIENT_SECRET", "")
API_BASE      = "https://adsapi.snapchat.com/v1"
TOKEN_URL     = "https://accounts.snapchat.com/login/oauth2/access_token"
CONFIG_FILE   = os.path.join(os.path.dirname(__file__), "config.json")

# ── Token Management ─────────────────────────────────────────────────────────
# Bug 2 fix: asyncio.Lock prevents race condition when multiple tools
# are called concurrently and the token has expired simultaneously.
_token_lock = asyncio.Lock()

def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(cfg: dict) -> None:
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

async def get_access_token() -> str:
    async with _token_lock:
        cfg = load_config()
        # Token still valid?
        if cfg.get("access_token") and cfg.get("expires_at", 0) > time.time() + 60:
            return cfg["access_token"]
        # Refresh
        if cfg.get("refresh_token"):
            async with httpx.AsyncClient() as c:
                r = await c.post(TOKEN_URL, data={
                    "grant_type":    "refresh_token",
                    "refresh_token": cfg["refresh_token"],
                    "client_id":     CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                })
                r.raise_for_status()
                d = r.json()
                cfg["access_token"]  = d["access_token"]
                cfg["refresh_token"] = d.get("refresh_token", cfg["refresh_token"])
                cfg["expires_at"]    = time.time() + d.get("expires_in", 1800)
                save_config(cfg)
                return cfg["access_token"]
        raise RuntimeError(
            "No tokens found. Run auth_setup.py first to authorise your Snapchat account."
        )

# ── API Helpers ───────────────────────────────────────────────────────────────
async def snap_request(endpoint: str, method: str = "GET", **kwargs) -> dict:
    token = await get_access_token()
    async with httpx.AsyncClient() as c:
        r = await c.request(
            method,
            f"{API_BASE}/{endpoint}",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=30.0,
            **kwargs,
        )
        r.raise_for_status()
        return r.json()

async def snap_request_all(endpoint: str, list_key: str) -> list:
    """
    Bug 3 fix: Paginated fetch — follows paging.next_link until all
    pages are retrieved. Works for campaigns, adsquads, ads, creatives.
    """
    results = []
    url = f"{API_BASE}/{endpoint}"
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as c:
        while url:
            r = await c.get(url, headers=headers, timeout=30.0)
            r.raise_for_status()
            data = r.json()
            results.extend(data.get(list_key, []))
            # Follow next page if present
            url = data.get("paging", {}).get("next_link")

    return results

# ── Error Handler ─────────────────────────────────────────────────────────────
def err(e: Exception) -> str:
    """
    Bug 4 fix: Parse JSON error body and extract nested human-readable
    message before falling back to raw text truncation.
    """
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return "Error 401: Auth expired. Run auth_setup.py again."
        if code == 403:
            return "Error 403: Permission denied. Check API scopes."
        if code == 404:
            return "Error 404: Not found. Verify the ID is correct."
        if code == 429:
            return "Error 429: Rate limit hit. Wait a moment and retry."
        # Try to extract nested Snapchat error message
        try:
            body = e.response.json()
            # Snapchat nests errors at: body -> errors -> [0] -> message
            errors = body.get("errors") or body.get("debug_message") or body.get("display_message")
            if isinstance(errors, list) and errors:
                msg = errors[0].get("message", str(errors[0]))
            elif isinstance(errors, str):
                msg = errors
            else:
                msg = e.response.text[:300]
        except Exception:
            msg = e.response.text[:300]
        return f"Error {code}: {msg}"
    return f"Error: {e}"

def fmt_money(v) -> str:
    try:
        return f"${float(v)/1_000_000:.2f}"
    except Exception:
        return str(v)

# ── Collection endpoint map ───────────────────────────────────────────────────
# Bug 1 fix: Snapchat requires PUT to the collection endpoint
# (e.g. adaccounts/{id}/campaigns) not the individual resource endpoint.
COLLECTION_ENDPOINTS = {
    "campaigns": "adaccounts/{ad_account_id}/campaigns",
    "adsquads":  "adaccounts/{ad_account_id}/adsquads",
    "ads":       "adaccounts/{ad_account_id}/ads",
}
ENTITY_KEYS = {
    "campaigns": "campaign",
    "adsquads":  "adsquad",
    "ads":       "ad",
}

# ── Input Models ─────────────────────────────────────────────────────────────
class AdAccountInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID (UUID)")

class AdSquadInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID (UUID)")
    campaign_id: Optional[str] = Field(None, description="Filter by Campaign ID (optional)")

class StatsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID (UUID)")
    entity_type: str = Field(..., description="'campaigns', 'adsquads', or 'ads'")
    entity_id: str = Field(..., description="ID of the campaign / ad squad / ad")
    start_date: str = Field(..., description="Start date YYYY-MM-DD")
    end_date: str = Field(..., description="End date YYYY-MM-DD")
    granularity: str = Field(default="DAY", description="TOTAL, DAY, or HOUR")

class UpdateStatusInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID (UUID) — required for correct API endpoint")
    entity_type: str = Field(..., description="'campaigns', 'adsquads', or 'ads'")
    entity_id: str = Field(..., description="ID of the entity to update")
    status: str = Field(..., description="'ACTIVE' or 'PAUSED'")

class UpdateBudgetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID (UUID)")
    campaign_id: str = Field(..., description="Campaign ID to update")
    daily_budget_micro: Optional[int] = Field(None, description="New daily budget in micro-dollars (e.g. 50000000 = $50)")
    lifetime_spend_cap_micro: Optional[int] = Field(None, description="Lifetime spend cap in micro-dollars (optional)")

# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool(name="snapchat_get_ad_accounts", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_ad_accounts() -> str:
    """List all Snapchat Ad Accounts linked to your credentials. Use this first to get your Ad Account ID."""
    try:
        org_data = await snap_request("me/organizations")
        orgs = org_data.get("organizations", [])
        if not orgs:
            return "No organizations found for this account."

        all_accounts = []
        for org in orgs:
            org_obj = org.get("organization", org)
            org_id  = org_obj.get("id")
            acc_data = await snap_request(f"organizations/{org_id}/adaccounts")
            accounts = acc_data.get("adaccounts", [])
            for a in accounts:
                ac = a.get("adaccount", a)
                ac["_org_id"] = org_id
                all_accounts.append(ac)

        if not all_accounts:
            return "No ad accounts found."

        lines = ["## Your Snapchat Ad Accounts\n"]
        for ac in all_accounts:
            lines.append(f"- **{ac.get('name', 'Unnamed')}**")
            lines.append(f"  - Ad Account ID: `{ac.get('id')}`")
            lines.append(f"  - Organization ID: `{ac.get('_org_id')}`")
            lines.append(f"  - Currency: {ac.get('currency', 'N/A')}")
            lines.append(f"  - Status: {ac.get('status', 'N/A')}\n")
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_campaigns", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_campaigns(params: AdAccountInput) -> str:
    """List ALL campaigns for a Snapchat Ad Account with status and budget info. Fully paginated."""
    try:
        # Bug 3 fix: paginated fetch
        campaigns = await snap_request_all(
            f"adaccounts/{params.ad_account_id}/campaigns", "campaigns"
        )
        if not campaigns:
            return "No campaigns found for this account."
        lines = [f"## Campaigns — Account {params.ad_account_id}\n"]
        lines.append(f"Total: {len(campaigns)} campaigns\n")
        for c in campaigns:
            cp = c.get("campaign", c)
            lines.append(f"### {cp.get('name', 'Unnamed')}")
            lines.append(f"- **ID**: `{cp.get('id')}`")
            lines.append(f"- **Status**: {cp.get('status')}")
            lines.append(f"- **Objective**: {cp.get('objective', 'N/A')}")
            if cp.get("daily_budget_micro"):
                lines.append(f"- **Daily Budget**: {fmt_money(cp['daily_budget_micro'])}")
            if cp.get("lifetime_spend_cap_micro"):
                lines.append(f"- **Lifetime Cap**: {fmt_money(cp['lifetime_spend_cap_micro'])}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_ad_squads", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_ad_squads(params: AdSquadInput) -> str:
    """List ALL Ad Squads (ad sets) for an account or specific campaign. Fully paginated."""
    try:
        # Bug 3 fix: paginated fetch
        if params.campaign_id:
            squads = await snap_request_all(
                f"campaigns/{params.campaign_id}/adsquads", "adsquads"
            )
        else:
            squads = await snap_request_all(
                f"adaccounts/{params.ad_account_id}/adsquads", "adsquads"
            )
        if not squads:
            return "No ad squads found."
        lines = [f"## Ad Squads ({len(squads)} total)\n"]
        for s in squads:
            sq = s.get("adsquad", s)
            lines.append(f"### {sq.get('name', 'Unnamed')}")
            lines.append(f"- **ID**: `{sq.get('id')}`")
            lines.append(f"- **Status**: {sq.get('status')}")
            lines.append(f"- **Bid Strategy**: {sq.get('bid_strategy', 'N/A')}")
            if sq.get("bid_micro"):
                lines.append(f"- **Bid**: {fmt_money(sq['bid_micro'])}")
            if sq.get("daily_budget_micro"):
                lines.append(f"- **Daily Budget**: {fmt_money(sq['daily_budget_micro'])}")
            lines.append(f"- **Optimization Goal**: {sq.get('optimization_goal', 'N/A')}")
            lines.append(f"- **Placement**: {sq.get('placement_v2', {}).get('config', 'N/A')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_ads", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_ads(params: AdAccountInput) -> str:
    """List ALL Ads in an account with creative and status details. Fully paginated."""
    try:
        # Bug 3 fix: paginated fetch
        ads = await snap_request_all(
            f"adaccounts/{params.ad_account_id}/ads", "ads"
        )
        if not ads:
            return "No ads found."
        lines = [f"## Ads ({len(ads)} total)\n"]
        for a in ads:
            ad = a.get("ad", a)
            lines.append(f"### {ad.get('name', 'Unnamed')}")
            lines.append(f"- **ID**: `{ad.get('id')}`")
            lines.append(f"- **Status**: {ad.get('status')}")
            lines.append(f"- **Type**: {ad.get('type', 'N/A')}")
            lines.append(f"- **Ad Squad ID**: `{ad.get('ad_squad_id')}`")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_performance_stats", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_performance_stats(params: StatsInput) -> str:
    """
    Get performance statistics for a campaign, ad squad, or ad.
    Returns: impressions, swipe-ups, spend, CTR, eCPM, video views, conversions, ROAS.

    Args:
        params.entity_type: 'campaigns', 'adsquads', or 'ads'
        params.entity_id: the UUID of the entity
        params.start_date / end_date: date range YYYY-MM-DD
        params.granularity: DAY (default), TOTAL, or HOUR
    """
    try:
        endpoint = f"{params.entity_type}/{params.entity_id}/stats"
        query = {
            "fields": (
                "impressions,swipes,spend,swipe_up_percent,video_views,"
                "screen_time_millis,conversion_purchases,conversion_purchases_value"
            ),
            "granularity": params.granularity,
            "start_time":  params.start_date,
            "end_time":    params.end_date,
        }
        data = await snap_request(endpoint, params=query)
        timeseries = data.get("timeseries_stats", [{}])
        if not timeseries:
            return "No stats returned for this period."

        stats = timeseries[0].get("timeseries_stat", {})
        total = {}
        for row in stats.get("timeseries", [stats]):
            for k, v in row.get("stats", row).items():
                if isinstance(v, (int, float)):
                    total[k] = total.get(k, 0) + v

        spend     = total.get("spend", 0)
        imps      = total.get("impressions", 0)
        swipes    = total.get("swipes", 0)
        views     = total.get("video_views", 0)
        purchases = total.get("conversion_purchases", 0)
        rev       = total.get("conversion_purchases_value", 0)
        screen    = total.get("screen_time_millis", 0)

        ctr        = (swipes / imps * 100) if imps else 0
        ecpm       = (spend / imps * 1000 / 1_000_000) if imps else 0
        roas       = (rev / (spend / 1_000_000)) if spend else 0
        cpa        = ((spend / 1_000_000) / purchases) if purchases else 0
        avg_screen = (screen / views / 1000) if views else 0

        lines = [
            f"## Performance Stats — {params.start_date} to {params.end_date}\n",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| 💰 Spend | {fmt_money(spend)} |",
            f"| 👁 Impressions | {imps:,} |",
            f"| 👆 Swipe-Ups | {swipes:,} |",
            f"| 📊 CTR (Swipe Rate) | {ctr:.2f}% |",
            f"| 📺 Video Views | {views:,} |",
            f"| ⏱ Avg Screen Time | {avg_screen:.1f}s |",
            f"| 🛒 Conversions (Purchases) | {purchases:,} |",
            f"| 💵 Conversion Revenue | {fmt_money(rev * 1_000_000)} |",
            f"| 📈 ROAS | {roas:.2f}x |",
            f"| 🎯 CPA | ${cpa:.2f} |",
            f"| 📡 eCPM | ${ecpm:.2f} |",
        ]
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_account_report", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_account_report(params: StatsInput) -> str:
    """
    Full account-level performance report across all campaigns for a date range.
    Use this for a top-level health check of the whole Snapchat account.
    """
    try:
        endpoint = f"adaccounts/{params.ad_account_id}/stats"
        query = {
            "fields": (
                "impressions,swipes,spend,swipe_up_percent,video_views,"
                "conversion_purchases,conversion_purchases_value,frequency"
            ),
            "granularity": params.granularity,
            "start_time":  params.start_date,
            "end_time":    params.end_date,
        }
        data = await snap_request(endpoint, params=query)
        timeseries = data.get("timeseries_stats", [{}])
        stats = timeseries[0].get("timeseries_stat", {}) if timeseries else {}
        rows  = stats.get("timeseries", [stats])

        total = {}
        for row in rows:
            for k, v in row.get("stats", row).items():
                if isinstance(v, (int, float)):
                    total[k] = total.get(k, 0) + v

        spend     = total.get("spend", 0)
        imps      = total.get("impressions", 0)
        swipes    = total.get("swipes", 0)
        views     = total.get("video_views", 0)
        purchases = total.get("conversion_purchases", 0)
        rev       = total.get("conversion_purchases_value", 0)
        freq      = total.get("frequency", 0)

        ctr  = (swipes / imps * 100) if imps else 0
        ecpm = (spend / imps * 1000 / 1_000_000) if imps else 0
        roas = (rev / (spend / 1_000_000)) if spend else 0
        cpa  = ((spend / 1_000_000) / purchases) if purchases else 0

        lines = [
            f"# 📊 Snapchat Account Report",
            f"**Period**: {params.start_date} → {params.end_date}\n",
            f"## Summary",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| 💰 Total Spend | {fmt_money(spend)} |",
            f"| 👁 Impressions | {imps:,} |",
            f"| 🔁 Frequency | {freq:.1f}x |",
            f"| 👆 Swipe-Ups | {swipes:,} |",
            f"| 📊 Swipe-Up Rate | {ctr:.2f}% |",
            f"| 📺 Video Views | {views:,} |",
            f"| 🛒 Purchases | {purchases:,} |",
            f"| 💵 Revenue | {fmt_money(rev * 1_000_000)} |",
            f"| 📈 ROAS | {roas:.2f}x |",
            f"| 🎯 CPA | ${cpa:.2f} |",
            f"| 📡 eCPM | ${ecpm:.2f} |",
        ]
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_update_status", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def snapchat_update_status(params: UpdateStatusInput) -> str:
    """
    Pause or activate a campaign, ad squad, or ad.

    Args:
        ad_account_id: required — needed for the correct Snapchat API collection endpoint
        entity_type: 'campaigns', 'adsquads', or 'ads'
        entity_id: the UUID to update
        status: 'ACTIVE' or 'PAUSED'
    """
    try:
        if params.status not in ("ACTIVE", "PAUSED"):
            return "Error: status must be 'ACTIVE' or 'PAUSED'."
        if params.entity_type not in COLLECTION_ENDPOINTS:
            return f"Error: entity_type must be one of: {list(COLLECTION_ENDPOINTS.keys())}"

        key = ENTITY_KEYS[params.entity_type]

        # Fetch current full entity object
        data = await snap_request(f"{params.entity_type}/{params.entity_id}")
        entity = data.get(params.entity_type, [{}])[0].get(key, {})
        entity["status"] = params.status

        # Bug 1 fix: PUT to the collection endpoint, not the individual resource
        collection = COLLECTION_ENDPOINTS[params.entity_type].format(
            ad_account_id=params.ad_account_id
        )
        await snap_request(collection, method="PUT", json={params.entity_type: [entity]})

        action = "▶️ Activated" if params.status == "ACTIVE" else "⏸️ Paused"
        return f"{action} {key} `{params.entity_id}` successfully."
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_update_campaign_budget", annotations={"readOnlyHint": False, "destructiveHint": False})
async def snapchat_update_campaign_budget(params: UpdateBudgetInput) -> str:
    """
    Update the daily budget or lifetime spend cap of a campaign.

    daily_budget_micro and lifetime_spend_cap_micro are in micro-dollars:
    $1 = 1,000,000 micro-dollars. Example: $50/day = 50000000.
    """
    try:
        data = await snap_request(f"campaigns/{params.campaign_id}")
        campaigns = data.get("campaigns", [{}])
        campaign = campaigns[0].get("campaign", {})

        if params.daily_budget_micro is not None:
            campaign["daily_budget_micro"] = params.daily_budget_micro
        if params.lifetime_spend_cap_micro is not None:
            campaign["lifetime_spend_cap_micro"] = params.lifetime_spend_cap_micro

        payload = {"campaigns": [campaign]}
        await snap_request(
            f"adaccounts/{params.ad_account_id}/campaigns",
            method="PUT",
            json=payload,
        )
        lines = [f"✅ Budget updated for campaign `{params.campaign_id}`"]
        if params.daily_budget_micro is not None:
            lines.append(f"- Daily Budget → {fmt_money(params.daily_budget_micro)}")
        if params.lifetime_spend_cap_micro is not None:
            lines.append(f"- Lifetime Cap → {fmt_money(params.lifetime_spend_cap_micro)}")
        return "\n".join(lines)
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_creatives", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_creatives(params: AdAccountInput) -> str:
    """List ALL creatives (ad formats, media, headlines) in your ad account. Fully paginated."""
    try:
        # Bug 3 fix: paginated fetch
        creatives = await snap_request_all(
            f"adaccounts/{params.ad_account_id}/creatives", "creatives"
        )
        if not creatives:
            return "No creatives found."
        lines = [f"## Creatives ({len(creatives)} total)\n"]
        for c in creatives:
            cr = c.get("creative", c)
            lines.append(f"### {cr.get('name', 'Unnamed')}")
            lines.append(f"- **ID**: `{cr.get('id')}`")
            lines.append(f"- **Type**: {cr.get('type', 'N/A')}")
            lines.append(f"- **Headline**: {cr.get('headline', 'N/A')}")
            lines.append(f"- **Call to Action**: {cr.get('call_to_action', 'N/A')}")
            lines.append(f"- **Brand Name**: {cr.get('brand_name', 'N/A')}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return err(e)


# ── Run ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    mcp.run()
