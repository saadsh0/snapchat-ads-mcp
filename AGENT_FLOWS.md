# Snapchat Ads MCP — Suggested Agent Flows

These are ideas for how you can combine this MCP with AI agents (Antigravity, n8n, Make, etc.) to automate Snapchat Ads workflows. These are starting points — adapt them to your stack and business logic.

---

## Flow 1 — Daily Performance Monitor

**Trigger**: Every morning at 9am
**What it does**: Pulls yesterday's data, flags underperformers, pauses them, sends a summary

```
1. snapchat_get_campaigns → get all active campaigns
2. snapchat_get_performance_stats → pull yesterday's ROAS, CPA, CTR per campaign
3. Agent logic:
   - If ROAS < 1.5 → flag
   - If CPA > threshold → flag
   - If CTR < 0.5% → flag
4. snapchat_update_status → pause flagged campaigns
5. Send summary via WhatsApp / Slack / Email
```

**Value**: Stops budget waste overnight without manual checks.

---

## Flow 2 — Budget Pacing Guard

**Trigger**: Every 6 hours
**What it does**: Monitors daily spend pace, adjusts to avoid over/under-spending

```
1. snapchat_get_performance_stats → current day spend vs daily budget
2. Agent logic:
   - If spend > 80% of daily budget before 6pm → pause until midnight
   - If spend < 20% of daily budget by noon → increase bid by 10%
3. snapchat_update_campaign_budget or snapchat_update_status → act
4. Log action to Notion / Google Sheets
```

**Value**: Keeps campaigns on budget without babysitting.

---

## Flow 3 — Weekly Creative Performance Audit

**Trigger**: Every Monday morning
**What it does**: Ranks all ads by swipe-up rate and screen time, kills bottom performers

```
1. snapchat_get_ads → list all active ads
2. snapchat_get_performance_stats → CTR, swipe rate, screen time per ad
3. Agent logic:
   - Rank by swipe-up rate
   - Bottom 20% → pause
   - Top performers → flag for scaling
4. Generate weekly creative report
5. Send to team
```

**Value**: Systematic creative testing without manual analysis.

---

## Flow 4 — Pre-Eid / Seasonal Push Automation

**Trigger**: 7 days before a key date (Eid, National Day, etc.)
**What it does**: Ramps up budget on best-performing campaigns automatically

```
1. snapchat_get_campaigns → get all campaigns tagged for the event
2. snapchat_get_performance_stats → identify top ROAS campaigns from last 7 days
3. snapchat_update_campaign_budget → increase budget by 50% on top performers
4. snapchat_update_status → activate any paused campaigns prepared for the event
5. Monitor daily and adjust
```

**Value**: Never miss a peak window because of manual delays.

---

## Flow 5 — Multi-Account Agency Report

**Trigger**: Weekly / Monthly
**What it does**: Pulls data across all client accounts and generates a consolidated report

```
1. snapchat_get_ad_accounts → list all accounts
2. For each account:
   - snapchat_get_account_report → 7-day / 30-day summary
   - snapchat_get_campaigns → active campaign list
3. Compile into one report per client
4. Export to PDF / Google Slides / Notion
5. Auto-send to client email
```

**Value**: Agency reporting on autopilot across all accounts.

---

## Flow 6 — Lead Follow-Up Trigger (Snapchat → CRM)

**Trigger**: New lead from Snapchat Lead Gen form
**What it does**: Captures lead, enriches it, sends to CRM, triggers WhatsApp follow-up

```
1. Snapchat Ads Lead Gen form fires webhook
2. Agent captures lead data (name, phone, email)
3. Enriches with ad/campaign source from snapchat_get_ads
4. Pushes to CRM (HubSpot, Zoho, etc.)
5. Triggers WhatsApp message via your funnel within 5 minutes
```

**Value**: Speed-to-lead — the #1 factor in conversion for travel/e-commerce.

---

## Tools Available in This MCP

| Tool | Use in Agent |
|---|---|
| `snapchat_get_ad_accounts` | Start here — get account IDs |
| `snapchat_get_campaigns` | List campaigns for iteration |
| `snapchat_get_ad_squads` | Ad set level data |
| `snapchat_get_ads` | Individual ad performance |
| `snapchat_get_performance_stats` | Core metrics for any entity |
| `snapchat_get_account_report` | Top-level account summary |
| `snapchat_update_status` | Pause / activate |
| `snapchat_update_campaign_budget` | Change budgets |
| `snapchat_get_creatives` | Creative asset details |

---

## Notes

- These flows are directional — implementation depends on your agent platform (Antigravity, n8n, Make, etc.)
- Combine with other MCPs (Meta Ads, Google Ads, CRM) for cross-platform automation
- All write actions (pause, update budget) should include a confirmation step or threshold logic to avoid unintended changes
