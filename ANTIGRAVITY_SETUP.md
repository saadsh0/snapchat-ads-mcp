# Snapchat Ads MCP — Antigravity Setup Guide

## Overview
This guide connects the Snapchat Ads MCP server to Antigravity so your AI agents
can analyze performance and take actions on Snapchat campaigns automatically.

---

## Prerequisites
- Snapchat Ads MCP already authorized (run `auth_setup.py` first — see SETUP.md)
- Antigravity installed and running
- Python 3.10+ installed on the machine running Antigravity

---

## Step 1 — Place the MCP Folder

Copy the entire `snapchat_ads_mcp/` folder to your Antigravity machine (or the
server where Antigravity agents run). Note the full absolute path — you'll need it.

Example path: `/home/user/mcps/snapchat_ads_mcp/`

---

## Step 2 — Install Dependencies

On the Antigravity machine:

```bash
cd /home/user/mcps/snapchat_ads_mcp
pip install -r requirements.txt
```

---

## Step 3 — Run Auth Setup (Once)

```bash
python auth_setup.py
```

Follow the prompts. This creates `config.json` with your access + refresh tokens.
Tokens auto-refresh — you only do this once.

---

## Step 4 — Add MCP to Antigravity

In your Antigravity configuration (usually `antigravity.config.json` or via the
Antigravity dashboard), add the following MCP server definition:

```json
{
  "mcp_servers": [
    {
      "name": "snapchat_ads",
      "description": "Snapchat Ads — campaign analysis, performance reporting, pause/activate campaigns, update budgets",
      "transport": "stdio",
      "command": "python",
      "args": ["/home/user/mcps/snapchat_ads_mcp/server.py"],
      "env": {
        "SNAPCHAT_CLIENT_ID": "08e4ac8c-5495-41bf-ab32-746286992c64",
        "SNAPCHAT_CLIENT_SECRET": "720b3c2920990e0fea9b"
      }
    }
  ]
}
```

> Adjust the path in `args` to match where you saved the folder.

---

## Step 5 — Verify Connection

In Antigravity, run a test agent prompt:

```
List all Snapchat ad accounts
```

Expected response: your ad account name and ID.

---

## Available Tools for Antigravity Agents

| Tool Name | Description | Read/Write |
|-----------|-------------|------------|
| `snapchat_get_ad_accounts` | List all accounts — **start here to get Ad Account ID** | Read |
| `snapchat_get_campaigns` | All campaigns with budget and status | Read |
| `snapchat_get_ad_squads` | All ad squads with targeting and bid info | Read |
| `snapchat_get_ads` | All individual ads | Read |
| `snapchat_get_performance_stats` | ROAS, CPA, CTR, spend, impressions for any entity | Read |
| `snapchat_get_account_report` | Full account-level performance summary | Read |
| `snapchat_update_status` | Pause or activate campaigns / ad squads / ads | **Write** |
| `snapchat_update_campaign_budget` | Change daily budget or lifetime spend cap | **Write** |
| `snapchat_get_creatives` | List all creative assets with headlines and CTAs | Read |

---

## Recommended Antigravity Agent Flows

### Daily Performance Monitor Agent
```
Every morning at 9am:
1. Get account report for yesterday
2. Flag any campaign with ROAS < 1.5 or CPA > $30
3. Auto-pause those campaigns
4. Send Slack/WhatsApp summary
```

### Budget Pacing Agent
```
Every 6 hours:
1. Pull spend vs budget for all active campaigns
2. If spend > 80% of daily budget before 6pm → pause until midnight
3. If spend < 20% of daily budget by noon → increase bid by 10%
```

### Creative Performance Agent
```
Weekly:
1. Pull ad-level performance (CTR, swipe rate, screen time)
2. Rank creatives by swipe-up rate
3. Pause bottom 20%
4. Flag top performers for scaling
```

### Full Audit Agent
```
Monthly:
1. Account-level report (full month)
2. Campaign-level breakdown
3. Ad squad comparison
4. Creative performance ranking
5. Output structured report with recommendations
```

---

## Micro-Dollar Conversion Reference

Snapchat API uses micro-dollars for budget values:

| USD | Micro-Dollars |
|-----|--------------|
| $1 | 1,000,000 |
| $10 | 10,000,000 |
| $50 | 50,000,000 |
| $100 | 100,000,000 |
| $500 | 500,000,000 |

When using `snapchat_update_campaign_budget`, pass the micro-dollar value:
- $50/day → `daily_budget_micro: 50000000`

---

## Troubleshooting

**Agent gets "No tokens found"** → Run `auth_setup.py` on the Antigravity machine

**Agent gets "Error 401"** → Tokens expired. Run `auth_setup.py` again

**Agent gets "Error 403"** → Snapchat account missing Marketing API permission

**Path errors** → Double-check the absolute path in `args` matches actual folder location

**Python not found** → Use full path: `"command": "/usr/bin/python3"`

---

## Security Notes

- `config.json` contains OAuth tokens — do not commit to git or share
- Use environment variables for `CLIENT_ID` and `CLIENT_SECRET` in production
- Limit Antigravity agent write permissions to specific ad accounts if possible
- Rotate tokens periodically by re-running `auth_setup.py`
