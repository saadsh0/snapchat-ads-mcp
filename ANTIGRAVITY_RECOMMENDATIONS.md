# Snapchat Ads MCP — Antigravity Integration Recommendations

This document is specifically for teams using **Antigravity** as their agent platform. It covers how to connect this MCP, which flows to prioritize, and the recommended agent architectures that match Antigravity's strengths.

---

## How to Connect This MCP to Antigravity

1. In Antigravity, go to **Settings → MCP Servers → Add Server**
2. Point it to `server.py` in this repo
3. Set the following environment variables in Antigravity's MCP config:

```
SNAPCHAT_CLIENT_ID=your_client_id
SNAPCHAT_CLIENT_SECRET=your_client_secret
```

4. Run `auth_setup.py` once to generate `config.json` (OAuth tokens)
5. Place `config.json` in the same directory as `server.py`
6. Restart Antigravity — the 9 Snapchat tools will appear in your tool list

---

## Recommended Agent Architectures for Antigravity

### Agent 1 — Daily Ops Agent

**Purpose**: Runs every morning, audits performance, takes action, sends a brief  
**Recommended trigger**: Scheduled (cron — 9:00am daily)

**Suggested prompt for Antigravity**:
```
You are a Snapchat Ads performance manager for [client name].

Every morning:
1. Pull all active campaigns for ad account [ad_account_id]
2. Get performance stats for yesterday (use yesterday's date)
3. Flag any campaign where ROAS < 1.5 or CPA > [threshold] or CTR < 0.5%
4. Pause flagged campaigns using snapchat_update_status
5. Return a plain-text summary: campaigns paused, reason, current ROAS/CPA

Be concise. Take action first, explain second.
```

**Tools to enable**: `snapchat_get_campaigns`, `snapchat_get_performance_stats`, `snapchat_update_status`

---

### Agent 2 — Budget Pacing Agent

**Purpose**: Prevents overspend and underspend within the day  
**Recommended trigger**: Scheduled (every 6 hours)

**Suggested prompt for Antigravity**:
```
You are a budget pacing agent for Snapchat Ads.

Check the current day's spend pacing:
1. Get today's spend and daily budget for ad account [ad_account_id]
2. Calculate: spend / budget × 100 = pacing %
3. If pacing > 80% and it's before 6pm local time → pause the overspending campaign
4. If pacing < 20% and it's after 12pm local time → increase budget by 10%
5. Log the action with timestamp and reason

Always confirm the action was applied before logging.
```

**Tools to enable**: `snapchat_get_performance_stats`, `snapchat_update_campaign_budget`, `snapchat_update_status`

---

### Agent 3 — Creative Audit Agent

**Purpose**: Weekly ranking and pruning of ad creatives  
**Recommended trigger**: Scheduled (Monday 8:00am)

**Suggested prompt for Antigravity**:
```
You are a creative performance analyst for Snapchat Ads.

Every Monday:
1. Get all active ads for ad account [ad_account_id]
2. Get last 7 days of stats: swipe_up_rate, screen_time_millis, spend
3. Rank ads by swipe_up_rate (highest to lowest)
4. Pause bottom 20% by swipe_up_rate (minimum spend > $5 to qualify)
5. Return a ranked table: Ad name | Swipe Rate | Screen Time | Status

Highlight top 3 performers and bottom 3 paused.
```

**Tools to enable**: `snapchat_get_ads`, `snapchat_get_performance_stats`, `snapchat_update_status`

---

### Agent 4 — Account Intelligence Agent

**Purpose**: On-demand deep analysis — ask it anything about your account  
**Recommended trigger**: On-demand (chat interface in Antigravity)

**Suggested prompt for Antigravity**:
```
You are a senior Snapchat Ads analyst with full access to the account.

When asked a question:
1. Pull the relevant data (campaigns, ad squads, ads, stats)
2. Analyze with a media buyer's lens — look for patterns, waste, opportunities
3. Give a direct recommendation with numbers to back it

Default date range: last 7 days unless specified.
Ad account ID: [ad_account_id]

Always answer: What's happening? Why? What should we do?
```

**Tools to enable**: All 9 tools

---

### Agent 5 — Agency Reporting Agent

**Purpose**: Generates client-ready performance reports  
**Recommended trigger**: Weekly (Friday 5pm) or on-demand

**Suggested prompt for Antigravity**:
```
You are a performance marketing analyst preparing a client report.

For ad account [ad_account_id]:
1. Pull last 7-day and last 30-day account summary
2. List top 3 and bottom 3 campaigns by ROAS
3. Identify any campaigns that were paused this week and why
4. Summarize: total spend, total conversions, avg ROAS, avg CPA
5. Give 3 recommendations for next week

Format the output as a structured report, suitable for sharing with a client.
```

**Tools to enable**: `snapchat_get_account_report`, `snapchat_get_campaigns`, `snapchat_get_performance_stats`

---

## Key Variables to Set Per Client

When deploying these agents per client in Antigravity, replace the following in each prompt:

| Variable | Description |
|---|---|
| `[ad_account_id]` | Found via `snapchat_get_ad_accounts` |
| `[client name]` | Client or brand name |
| `[threshold]` | Target CPA ceiling (e.g., $15) |

---

## Recommended Stack Alongside This MCP

| Layer | Tool |
|---|---|
| Agent platform | Antigravity |
| Cross-platform ads | Meta Ads MCP + Google Ads MCP |
| CRM sync | HubSpot / Zoho via webhook |
| Reporting output | Notion / Google Sheets |
| Lead follow-up | WhatsApp funnel (n8n or Make) |

---

## Notes

- All write actions (pause, update budget) should include a threshold or confirmation step — build this into the agent logic, not just the prompt
- Run `auth_setup.py` on each new machine — `config.json` stores the refresh token and must be present
- Tokens auto-refresh in the background via `server.py` — no manual intervention needed
- For multi-client agencies: run one MCP server instance per client, each with its own `config.json` and credentials
