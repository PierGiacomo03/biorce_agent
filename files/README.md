# Biorce Intel Agent

Weekly competitive intelligence agent for Biorce — tracks 50 competitors in the AI-Clinical Trial space and delivers a Top 3 brief to Slack.

## Setup

```bash
pip install -r requirements.txt
```

Set environment variables:
```bash
export ANTHROPIC_API_KEY="your_key_here"
export SLACK_WEBHOOK_URL="your_slack_webhook_here"  # optional until you have Slack access
```

## Run

```bash
python agent.py
```

## Output

- `output/latest.json` — most recent brief (consumed by Lovable dashboard)
- `output/weekly_brief_YYYY-MM-DD.json` — archived briefs
- `output/weekly_brief_YYYY-MM-DD.txt` — Slack-formatted text
- `output/signal_log.json` — full audit trail of all scored signals

## Architecture

```
agent.py          ← orchestrates the full pipeline
competitors.py    ← list of 50 competitors with segments
scorer.py         ← relevance scoring logic (1-5)
output/           ← generated briefs pushed to GitHub → read by Lovable
CLAUDE.md         ← agent instructions and domain context
```

## Slack Integration

When you have Biorce Slack access, set `SLACK_WEBHOOK_URL` and the agent will auto-post every Monday at 08:00.

## Lovable Dashboard

The Lovable dashboard reads `output/latest.json` from this GitHub repo and renders the Top 3 brief with a "Send to Slack" button.
