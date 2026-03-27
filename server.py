#!/usr/bin/env python3
"""
Snapchat Ads MCP Server
Analyze campaign performance and take actions on Snapchat Ads via Claude.

Multi-client support: set SNAPCHAT_CONFIG_FILE env var to point to a
specific client's config.json. Org is locked to the org_id saved in that
config file, preventing cross-client data access.
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

# Config file: env var takes priority (enables per-client isolation),
# falls back to config.json next to server.py
CONFIG_FILE = os.environ.get(
    "SNAPCHAT_CONFIG_FILE",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
)

# ── Cache (in-memory, 5-min TTL for read operations) ─────────────────────────
_cache: dict[str, tuple[float, str]] = {}
CACHE_TTL = 300  # seconds


def cache_get(key: str) -> Optional[str]:
    entry = _cache.get(key)
    if entry and entry[0] > time.time():
        return entry[1]
    return None


def cache_set(key: str, value: str) -> None:
    _cache[key] = (time.time() + CACHE_TTL, value)


def cache_invalidate(ad_account_id: str) -> None:
    """Clear all cached responses for a specific account after a write action."""
    stale = [k for k in _cache if ad_account_id in k]
    for k in stale:
        del _cache[k]


# ── Rate Limiter (30 requests per minute) ────────────────────────────────────
_request_times: list[float] = []
_rate_lock = asyncio.Lock()
RATE_LIMIT_PER_MINUTE = 30


async def _rate_limit():
    async with _rate_lock:
        now = time.time()
        _request_times[:] = [t for t in _request_times if now - t < 60]
        if len(_request_times) >= RATE_LIMIT_PER_MINUTE:
            wait = 60 - (now - _request_times[0]) + 0.5
            await asyncio.sleep(wait)
        _request_times.append(time.time())


# ── Token Management ─────────────────────────────────────────────────────────
_token_lock = asyncio.Lock()


def load_config() -> dict:
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}


def save_config(cfg: dict) -> None:
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)


def get_org_id() -> str:
    """Returns the locked org ID — from config.json (set during auth_setup)."""
    return load_config().get("org_id", "")


async def get_access_token() -> str:
    async with _token_lock:
        cfg = load_config()
        if not cfg:
            raise RuntimeError(
                f"No config found at {CONFIG_FILE}. "
                "Run auth_setup.py first (or auth_setup.py --client <name> for agency use)."
            )
        if cfg.get("access_token") and cfg.get("expires_at", 0) > time.time() + 60:
            return cfg["access_token"]
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
            "No tokens found. Run auth_setup.py to authorise your Snapchat account."
        )


# ── API Helpers ───────────────────────────────────────────────────────────────
async def snap_request(endpoint: str, method: str = "GET", **kwargs) -> dict:
    await _rate_limit()
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
    """Paginated fetch — follows paging.next_link until all pages are retrieved."""
    results = []
    url = f"{API_BASE}/{endpoint}"
    token = await get_access_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as c:
        while url:
            await _rate_limit()
            r = await c.get(url, headers=headers, timeout=30.0)
            r.raise_for_status()
            data = r.json()
            results.extend(data.get(list_key, []))
            url = data.get("paging", {}).get("next_link")

    return results


# ── Error Handler ─────────────────────────────────────────────────────────────
def err(e: Exception) -> str:
    if isinstance(e, httpx.HTTPStatusError):
        code = e.response.status_code
        if code == 401:
            return "Error 401: Auth expired. Run auth_setup.py again."
        if code == 403:
            return "Error 403: Permission denied. Check API scopes."
        if code == 404:
            return "Error 404: Not found. Verify the ID is correct."
        if code == 429:
            return "Error 429: Rate limit hit. Waiting and will retry on next call."
        try:
            body = e.response.json()
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
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID")
    entity_type: str = Field(..., description="'campaigns', 'adsquads', or 'ads'")
    entity_id: str = Field(..., description="ID of the entity to update")
    status: str = Field(..., description="'ACTIVE' or 'PAUSED'")

class UpdateBudgetInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    ad_account_id: str = Field(..., description="Snapchat Ad Account ID (UUID)")
    campaign_id: str = Field(..., description="Campaign ID to update")
    daily_budget_micro: Optional[int] = Field(None, description="Daily budget in micro-dollars ($1 = 1,000,000)")
    lifetime_spend_cap_micro: Optional[int] = Field(None, description="Lifetime spend cap in micro-dollars")

# ── Tools ────────────────────────────────────────────────────────────────────

@mcp.tool(name="snapchat_get_ad_accounts", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_ad_accounts() -> str:
    """
    List all Snapchat Ad Accounts linked to this config.
    When an org_id is saved in config, only that org's accounts are returned —
    preventing cross-client data access in agency setups.
    """
    try:
        org_id = get_org_id()

        if org_id:
            # Org is locked — skip /me/organizations, go directly to known org
            acc_data = await snap_request(f"organizations/{org_id}/adaccounts")
            accounts = acc_data.get("adaccounts", [])
            all_accounts = []
            for a in accounts:
                ac = a.get("adaccount", a)
                ac["_org_id"] = org_id
                all_accounts.append(ac)
        else:
            # No org locked — discover all (single-user fallback)
            org_data = await snap_request("me/organizations")
            orgs = org_data.get("organizations", [])
            if not orgs:
                return "No organizations found. Re-run auth_setup.py."
            all_accounts = []
            for org in orgs:
                org_obj = org.get("organization", org)
                oid = org_obj.get("id")
                acc_data = await snap_request(f"organizations/{oid}/adaccounts")
                for a in acc_data.get("adaccounts", []):
                    ac = a.get("adaccount", a)
                    ac["_org_id"] = oid
                    all_accounts.append(ac)

        if not all_accounts:
            return "No ad accounts found."

        lines = ["## Your Snapchat Ad Accounts\n"]
        if org_id:
            lines.append(f"🔒 Scoped to org: `{org_id}`\n")
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
    """
    List all campaigns for a Snapchat Ad Account with status and budget info.
    Returns ACTIVE, PAUSED, and COMPLETED campaigns — excludes DELETED only.
    Results cached for 5 minutes.
    """
    cache_key = f"campaigns:{params.ad_account_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        campaigns = await snap_request_all(
            f"adaccounts/{params.ad_account_id}/campaigns", "campaigns"
        )
        # Exclude permanently deleted campaigns — they have no operational value
        campaigns = [c for c in campaigns
                     if c.get("campaign", c).get("status") != "DELETED"]

        if not campaigns:
            return "No campaigns found for this account."

        lines = [f"## Campaigns — Account {params.ad_account_id}\n"]
        lines.append(f"Total: {len(campaigns)} campaigns (DELETED excluded)\n")
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

        result = "\n".join(lines)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_ad_squads", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_ad_squads(params: AdSquadInput) -> str:
    """
    List all Ad Squads for an account or specific campaign.
    Excludes DELETED. Results cached for 5 minutes.
    """
    cache_key = f"adsquads:{params.ad_account_id}:{params.campaign_id or 'all'}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        if params.campaign_id:
            squads = await snap_request_all(
                f"campaigns/{params.campaign_id}/adsquads", "adsquads"
            )
        else:
            squads = await snap_request_all(
                f"adaccounts/{params.ad_account_id}/adsquads", "adsquads"
            )

        squads = [s for s in squads
                  if s.get("adsquad", s).get("status") != "DELETED"]

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

        result = "\n".join(lines)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_ads", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_ads(params: AdAccountInput) -> str:
    """
    List all Ads in an account. Excludes DELETED. Results cached for 5 minutes.
    """
    cache_key = f"ads:{params.ad_account_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
        ads = await snap_request_all(
            f"adaccounts/{params.ad_account_id}/ads", "ads"
        )
        ads = [a for a in ads if a.get("ad", a).get("status") != "DELETED"]

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

        result = "\n".join(lines)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_performance_stats", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_performance_stats(params: StatsInput) -> str:
    """
    Get performance statistics for a campaign, ad squad, or ad.
    Returns: impressions, swipe-ups, spend, CTR, eCPM, video views, conversions, ROAS.
    Results cached per entity + date range for 5 minutes.
    """
    cache_key = f"stats:{params.entity_type}:{params.entity_id}:{params.start_date}:{params.end_date}:{params.granularity}"
    cached = cache_get(cache_key)
    if cached:
        return cached

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

        total = {}

        # Snapchat returns different structures based on granularity:
        # TOTAL -> total_stats[].total_stat.stats (flat dict)
        # DAY/HOUR -> timeseries_stats[].timeseries_stat.timeseries[].stats
        if "total_stats" in data:
            stat_block = data["total_stats"][0].get("total_stat", {})
            raw = stat_block.get("stats", {})
            for k, v in raw.items():
                if isinstance(v, (int, float)):
                    total[k] = v
        elif "timeseries_stats" in data:
            ts = data["timeseries_stats"]
            if not ts:
                return "No stats returned for this period."
            stat_block = ts[0].get("timeseries_stat", {})
            for row in stat_block.get("timeseries", [stat_block]):
                for k, v in row.get("stats", row).items():
                    if isinstance(v, (int, float)):
                        total[k] = total.get(k, 0) + v
        else:
            return "No stats returned for this period."

        if not total or total.get("impressions", 0) == 0 and total.get("spend", 0) == 0:
            return f"No activity found for this entity in {params.start_date} to {params.end_date}."

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
        result = "\n".join(lines)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_get_account_report", annotations={"readOnlyHint": True, "destructiveHint": False})
async def snapchat_get_account_report(params: StatsInput) -> str:
    """
    Full account-level performance report across all campaigns for a date range.
    Results cached per account + date range for 5 minutes.
    """
    cache_key = f"report:{params.ad_account_id}:{params.start_date}:{params.end_date}:{params.granularity}"
    cached = cache_get(cache_key)
    if cached:
        return cached

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

        total = {}
        if "total_stats" in data:
            stat_block = data["total_stats"][0].get("total_stat", {})
            for k, v in stat_block.get("stats", {}).items():
                if isinstance(v, (int, float)):
                    total[k] = v
        elif "timeseries_stats" in data:
            ts = data["timeseries_stats"]
            stats = ts[0].get("timeseries_stat", {}) if ts else {}
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
        result = "\n".join(lines)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_update_status", annotations={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True})
async def snapchat_update_status(params: UpdateStatusInput) -> str:
    """
    Pause or activate a campaign, ad squad, or ad.
    Automatically clears cached data for the account after the update.
    """
    try:
        if params.status not in ("ACTIVE", "PAUSED"):
            return "Error: status must be 'ACTIVE' or 'PAUSED'."
        if params.entity_type not in COLLECTION_ENDPOINTS:
            return f"Error: entity_type must be one of: {list(COLLECTION_ENDPOINTS.keys())}"

        key = ENTITY_KEYS[params.entity_type]
        data = await snap_request(f"{params.entity_type}/{params.entity_id}")
        entity = data.get(params.entity_type, [{}])[0].get(key, {})
        entity["status"] = params.status

        collection = COLLECTION_ENDPOINTS[params.entity_type].format(
            ad_account_id=params.ad_account_id
        )
        await snap_request(collection, method="PUT", json={params.entity_type: [entity]})

        # Invalidate cache so next read reflects the change immediately
        cache_invalidate(params.ad_account_id)

        action = "▶️ Activated" if params.status == "ACTIVE" else "⏸️ Paused"
        return f"{action} {key} `{params.entity_id}` successfully."
    except Exception as e:
        return err(e)


@mcp.tool(name="snapchat_update_campaign_budget", annotations={"readOnlyHint": False, "destructiveHint": False})
async def snapchat_update_campaign_budget(params: UpdateBudgetInput) -> str:
    """
    Update the daily budget or lifetime spend cap of a campaign.
    $1 = 1,000,000 micro-dollars. Example: $50/day = 50000000.
    Automatically clears cached data for the account after the update.
    """
    try:
        data = await snap_request(f"campaigns/{params.campaign_id}")
        campaigns = data.get("campaigns", [{}])
        campaign = campaigns[0].get("campaign", {})

        if params.daily_budget_micro is not None:
            campaign["daily_budget_micro"] = params.daily_budget_micro
        if params.lifetime_spend_cap_micro is not None:
            campaign["lifetime_spend_cap_micro"] = params.lifetime_spend_cap_micro

        await snap_request(
            f"adaccounts/{params.ad_account_id}/campaigns",
            method="PUT",
            json={"campaigns": [campaign]},
        )

        # Invalidate cache so next read reflects the change immediately
        cache_invalidate(params.ad_account_id)

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
    """List all creatives in your ad account. Results cached for 5 minutes."""
    cache_key = f"creatives:{params.ad_account_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    try:
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

        result = "\n".join(lines)
        cache_set(cache_key, result)
        return result
    except Exception as e:
        return err(e)


# ── Run ───────────────────────────────────────────────────────────────────────
def main():
    """Entry point for PyPI package / uvx installation."""
    mcp.run()


if __name__ == "__main__":
    main()
