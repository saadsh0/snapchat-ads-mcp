# Snapchat Ads MCP Server

A free, open-source Model Context Protocol (MCP) server that connects Claude AI directly to your Snapchat Ads account — enabling live campaign analysis and real actions without leaving your chat.

## What It Does

| Capability | Tools |
|---|---|
| **Analyze** | Account report, campaign stats, ad squad breakdown, creative performance |
| **Act** | Pause/activate campaigns & ad squads, update budgets, rename campaigns |
| **Metrics** | ROAS, CPA, CTR, eCPM, swipe-up rate, video views, avg screen time |

No CSV exports. No manual copy-paste. Just ask Claude in plain language.

---

## Quick Demo

```
"Give me a performance report for last 7 days"
"Pause all underperforming ad squads"
"What's my ROAS across all active campaigns?"
"Update daily budget for campaign X to $100"
```

---

## Requirements

- Python 3.10+
- Snapchat Business Account
- Snapchat Marketing API credentials (free — see setup below)

---

## Setup

### Step 1 — Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/snapchat-ads-mcp
cd snapchat-ads-mcp
pip install -r requirements.txt
```

### Step 2 — Get Snapchat API Credentials (Free)

1. Go to [business.snapchat.com](https://business.snapchat.com)
2. Navigate to **Business Details → OAuth Apps → New App**
3. Set redirect URI to `https://example.com`
4. Copy your **Client ID** and **Client Secret**

> ⚠️ Use **Business Manager** to create the app — NOT the Developer Portal

### Step 3 — Set Environment Variables

```bash
export SNAPCHAT_CLIENT_ID=your_client_id
export SNAPCHAT_CLIENT_SECRET=your_client_secret
```

Or create a `.env` file (see `.env.example`).

### Step 4 — Authorize Your Account (One Time)

```bash
python auth_setup.py
```

This opens Snapchat in your browser → you authorize → paste the redirect URL → tokens saved automatically. Never needed again.

### Step 5 — Connect to Claude Desktop

Add this to your `claude_desktop_config.json`:

**Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "snapchat-ads": {
      "command": "python3",
      "args": ["/full/path/to/snapchat-ads-mcp/server.py"],
      "env": {
        "SNAPCHAT_CLIENT_ID": "your_client_id",
        "SNAPCHAT_CLIENT_SECRET": "your_client_secret"
      }
    }
  }
}
```

Restart Claude Desktop. Done.

---

## Available Tools

| Tool | Description |
|---|---|
| `snapchat_get_ad_accounts` | List all ad accounts — **start here** |
| `snapchat_get_campaigns` | All campaigns with budget & status |
| `snapchat_get_ad_squads` | Ad squads with targeting & bid info |
| `snapchat_get_ads` | Individual ads |
| `snapchat_get_performance_stats` | Stats for any campaign / ad squad / ad |
| `snapchat_get_account_report` | Full account-level summary |
| `snapchat_update_status` | Pause or activate any entity |
| `snapchat_update_campaign_budget` | Change daily budget or lifetime cap |
| `snapchat_get_creatives` | List creative assets |

---

## Example Prompts

```
List all my Snapchat ad accounts

Give me a 7-day performance report for account [ID]

Which campaigns have the highest CTR this week?

Pause the Indonesia ad squad — CTR is too low

Update campaign [ID] daily budget to $150

Compare performance across all active ad squads

Rename campaign [ID] to [new name]
```

---

## Budget Values (Micro-Dollars)

Snapchat API uses micro-dollars: `$1 = 1,000,000`

| USD | Micro-dollars |
|-----|--------------|
| $10 | 10,000,000 |
| $50 | 50,000,000 |
| $100 | 100,000,000 |

---

## Antigravity / n8n Integration

See [`ANTIGRAVITY_SETUP.md`](./ANTIGRAVITY_SETUP.md) for connecting this MCP to Antigravity agents for automated reporting and optimization workflows.

---

## Troubleshooting

**"CLIENT_ID not set"** → Set env variables before running

**"No tokens found"** → Run `python auth_setup.py`

**"Error 401"** → Token expired, run `python auth_setup.py` again

**"Error 403"** → Check Snapchat Business account has Marketing API access

**Tools not showing in Claude** → Verify path in config and restart Claude Desktop

---

## Built By

[Sigma Digital](https://sigma.digital) — Performance Marketing & AI Automation Agency

---

## License

MIT — free to use, modify, and distribute.
