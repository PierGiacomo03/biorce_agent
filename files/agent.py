"""
Biorce Competitive Intelligence Agent
Scrapes weekly updates for 50 AI-Clinical Trial competitors,
scores them, selects Top 3, and outputs a Slack-ready brief.
"""

import os
import json
import time
import subprocess
from datetime import datetime, timedelta
import anthropic
from competitors import COMPETITORS
from scorer import score_update, urgency_label, emoji_for_rank

# ── Config ──────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")  # leave empty until Slack access
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Helpers ──────────────────────────────────────────────────────────────────
def today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def week_window() -> str:
    end = datetime.utcnow()
    start = end - timedelta(days=7)
    return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"


# ── Step 1: Scrape signals via Claude with web_search ────────────────────────
def fetch_competitor_update(competitor: dict) -> dict | None:
    """
    Uses Claude with web_search tool to find the latest update
    for a given competitor in the past 7 days.
    Returns a dict with update info or None if nothing relevant found.
    """
    name = competitor["name"]
    segment = competitor["segment"]
    focus = competitor["focus"]

    prompt = f"""You are a competitive intelligence analyst for Biorce, an AI-native clinical trial platform (product: Aika — explainable AI for protocol design, feasibility, and regulatory planning).

Search the web for news about "{name}" published in the LAST 7 DAYS only.
Focus area: {focus}

Find the single most relevant update about this company related to:
- Product launches or new features
- Funding rounds or acquisitions
- Partnerships with pharma companies
- Regulatory approvals or FDA/EMA mentions
- AI capabilities in clinical trials

If you find a relevant update from the last 7 days, respond in this exact JSON format:
{{
  "found": true,
  "competitor": "{name}",
  "segment": "{segment}",
  "what_happened": "One sentence describing what happened factually.",
  "why_it_matters": "One sentence on why this matters for Biorce specifically.",
  "source_url": "https://...",
  "raw_text": "Brief excerpt or summary of the source content"
}}

If NO relevant update is found from the last 7 days, respond:
{{
  "found": false,
  "competitor": "{name}"
}}

Respond ONLY with the JSON object. No preamble, no markdown."""

    try:
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract text content from response
        full_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                full_text += block.text

        if not full_text.strip():
            return None

        # Clean and parse JSON
        clean = full_text.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        data = json.loads(clean)
        return data if data.get("found") else None

    except Exception as e:
        print(f"  ⚠ Error fetching {name}: {e}")
        return None


# ── Step 2: Score all updates ────────────────────────────────────────────────
def score_all(updates: list[dict]) -> list[dict]:
    scored = []
    for update in updates:
        text = f"{update.get('what_happened', '')} {update.get('why_it_matters', '')} {update.get('raw_text', '')}"
        score = score_update(text, update.get("segment", ""))
        update["score"] = score
        update["urgency"] = urgency_label(score)
        if score >= 4:
            scored.append(update)
    return sorted(scored, key=lambda x: x["score"], reverse=True)


# ── Step 3: Select Top 3 ─────────────────────────────────────────────────────
def select_top_3(scored: list[dict]) -> list[dict]:
    return scored[:3]


# ── Step 4: Format Slack output ──────────────────────────────────────────────
def format_slack_message(top_3: list[dict], week: str) -> str:
    lines = [
        f"📊 *Weekly Competitor Intelligence — {today_str()}*",
        f"Biorce | AI-Clinical Trial Space | Week: {week}",
        ""
    ]

    if not top_3:
        lines.append("No high-relevance updates found this week.")
        return "\n".join(lines)

    for i, item in enumerate(top_3, 1):
        emoji = emoji_for_rank(i)
        action = item.get("action_suggested", "")
        lines += [
            f"{emoji} *{i}. {item['competitor']}* — {item['segment']}",
            f"What happened: {item['what_happened']}",
            f"Why it matters: {item['why_it_matters']}",
            f"Source: {item.get('source_url', 'N/A')}",
            ""
        ]

    if any(item.get("action_suggested") for item in top_3):
        action = next(item["action_suggested"] for item in top_3 if item.get("action_suggested"))
        lines.append(f"💡 *Action suggested:* {action}")

    return "\n".join(lines)


# ── Step 5: Save output files ─────────────────────────────────────────────────
def save_outputs(top_3: list[dict], all_signals: list[dict], slack_message: str):
    date = today_str()

    # Weekly brief JSON (consumed by Lovable dashboard)
    brief = {
        "week": date,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "top_3": [
            {
                "rank": i + 1,
                "urgency": item["urgency"],
                "competitor": item["competitor"],
                "segment": item["segment"],
                "what_happened": item["what_happened"],
                "why_it_matters": item["why_it_matters"],
                "source_url": item.get("source_url", ""),
                "action_suggested": item.get("action_suggested", "")
            }
            for i, item in enumerate(top_3)
        ]
    }

    brief_path = os.path.join(OUTPUT_DIR, f"weekly_brief_{date}.json")
    with open(brief_path, "w") as f:
        json.dump(brief, f, indent=2)
    print(f"✅ Brief saved: {brief_path}")

    # Also save as latest.json so Lovable always reads the most recent
    latest_path = os.path.join(OUTPUT_DIR, "latest.json")
    with open(latest_path, "w") as f:
        json.dump(brief, f, indent=2)

    # Full signal log (audit trail — all 4-5 scored items)
    log_path = os.path.join(OUTPUT_DIR, "signal_log.json")
    existing_log = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            existing_log = json.load(f)

    existing_log.append({
        "run_date": date,
        "signals": all_signals
    })

    with open(log_path, "w") as f:
        json.dump(existing_log, f, indent=2)

    # Slack-formatted text file
    txt_path = os.path.join(OUTPUT_DIR, f"weekly_brief_{date}.txt")
    with open(txt_path, "w") as f:
        f.write(slack_message)
    print(f"✅ Slack message saved: {txt_path}")

    return brief_path, latest_path


# ── Step 6: Post to Slack (when webhook is available) ────────────────────────
def post_to_slack(message: str) -> bool:
    if not SLACK_WEBHOOK_URL:
        print("ℹ Slack webhook not configured — skipping Slack delivery.")
        print("\n── SLACK OUTPUT PREVIEW ──────────────────────────────")
        print(message)
        print("──────────────────────────────────────────────────────\n")
        return False

    try:
        import urllib.request
        payload = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(
            SLACK_WEBHOOK_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                print("✅ Posted to Slack successfully.")
                return True
    except Exception as e:
        print(f"⚠ Slack post failed: {e}")
    return False


# ── Step 7: Push to GitHub ────────────────────────────────────────────────────
def push_to_github():
    try:
        subprocess.run(["git", "add", "output/"], check=True)
        subprocess.run(["git", "commit", "-m", f"Weekly brief {today_str()}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"⚠ GitHub push failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print(f"\n🚀 Biorce Intel Agent starting — {today_str()}")
    print(f"   Scanning {len(COMPETITORS)} competitors...\n")

    week = week_window()
    all_updates = []

    for i, competitor in enumerate(COMPETITORS):
        print(f"  [{i+1}/{len(COMPETITORS)}] Searching: {competitor['name']}...")
        update = fetch_competitor_update(competitor)
        if update:
            all_updates.append(update)
            print(f"    ✓ Update found")
        else:
            print(f"    – No relevant update")
        time.sleep(1)  # rate limit buffer

    print(f"\n📥 Total updates found: {len(all_updates)}")

    # Score and filter
    scored = score_all(all_updates)
    print(f"📊 High-relevance signals (score ≥ 4): {len(scored)}")

    # Select Top 3
    top_3 = select_top_3(scored)
    print(f"🏆 Top 3 selected\n")

    # Format
    slack_message = format_slack_message(top_3, week)

    # Save
    save_outputs(top_3, scored, slack_message)

    # Post to Slack
    post_to_slack(slack_message)

    # Push to GitHub (Lovable reads from here)
    push_to_github()

    print("\n✅ Agent run complete.")


if __name__ == "__main__":
    run()
