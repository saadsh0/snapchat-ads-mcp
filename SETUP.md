# Snapchat Ads MCP — Setup Guide (Claude Desktop)

## What's Included
| File | Purpose |
|------|---------|
| `server.py` | Main MCP server — all tools live here |
| `auth_setup.py` | Run once to authorize your Snapchat account |
| `requirements.txt` | Python dependencies |
| `config.json` | Auto-created after auth — stores tokens |

---

## Step 1 — Install Python Dependencies

Open Terminal and run:

```bash
cd /path/to/snapchat_ads_mcp
pip install -r requirements.txt
```

---

## Step 2 — Run Auth Setup (One Time Only)

```bash
python auth_setup.py
```

This will:
1. Open Snapchat in your browser
2. You log in and click Allow
3. Paste the redirect URL back into the terminal
4. Tokens are saved automatically to `config.json`

You only need to do this **once**. Tokens auto-refresh forever after.

---

## Step 3 — Add to Claude Desktop

Open your Claude Desktop config file:

**Mac**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add this inside `"mcpServers"`:

```json
{
  "mcpServers": {
    "snapchat_ads": {
      "command": "python",
      "args": ["/FULL/PATH/TO/snapchat_ads_mcp/server.py"],
      "env": {
        "SNAPCHAT_CLIENT_ID": "08e4ac8c-5495-41bf-ab32-746286992c64",
        "SNAPCHAT_CLIENT_SECRET": "720b3c2920990e0fea9b"
      }
    }
  }
}
```

> Replace `/FULL/PATH/TO/` with the actual folder path on your machine.

---

## Step 4 — Restart Claude Desktop

Close and reopen Claude Desktop. You should see the Snapchat tools available.

---

## Step 5 — Test It

Try this prompt in Claude:

> "List my Snapchat ad accounts"

Then once you have your Ad Account ID:

> "Give me a full performance report for account [ID] from 2026-03-01 to 2026-03-25"

---

## Available Tools

| Tool | What It Does |
|------|-------------|
| `snapchat_get_ad_accounts` | List all ad accounts (get your account ID here) |
| `snapchat_get_campaigns` | All campaigns with budget & status |
| `snapchat_get_ad_squads` | All ad sets with targeting & bid info |
| `snapchat_get_ads` | All individual ads |
| `snapchat_get_performance_stats` | ROAS, CPA, CTR, spend, impressions for any entity |
| `snapchat_get_account_report` | Full account-level performance summary |
| `snapchat_update_status` | Pause or activate campaigns / ad squads / ads |
| `snapchat_update_campaign_budget` | Change daily budget or lifetime cap |
| `snapchat_get_creatives` | List all creative assets |

---

## Example Prompts for Claude

```
List all my Snapchat campaigns and their status

Give me a performance report for campaign [ID] from March 1 to March 25

Pause campaign [ID] — it's underperforming

Update the daily budget for campaign [ID] to $100/day

Which ad squads have the highest ROAS this month?

Compare CTR across all active campaigns
```

---

## Troubleshooting

**"No tokens found"** → Run `python auth_setup.py` again

**"Error 401"** → Token expired. Run `python auth_setup.py` again

**"Error 403"** → Check that your Snap Business account has API access enabled

**Tools not showing in Claude** → Check the path in `claude_desktop_config.json` is correct and restart Claude
