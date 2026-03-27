"""
Biorce Competitive Intelligence Agent v2
Architecture:
- Google News RSS (free, no API key) → collect signals for all 50 competitors
- Single Claude call → analyze all signals, select Top 3, write brief
- Output → JSON file + Slack-ready text + GitHub push
"""

from typing import Optional
import os
import json
import time
import subprocess
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import re
from datetime import datetime, timedelta
import anthropic
from competitors import COMPETITORS
from dotenv import load_dotenv
load_dotenv()

# ── Config ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── Helpers ───────────────────────────────────────────────────────────────────
def today_str() -> str:
    return datetime.utcnow().strftime("%Y-%m-%d")

def week_window() -> str:
    end = datetime.utcnow()
    start = end - timedelta(days=7)
    return f"{start.strftime('%Y-%m-%d')} to {end.strftime('%Y-%m-%d')}"

def clean_html(text: str) -> str:
    return re.sub(r'<[^>]+>', '', text).strip()


# ── Step 1: Fetch Google News RSS for each competitor (FREE) ──────────────────
def fetch_google_news(competitor_name: str, max_results: int = 3) -> list:
    query = urllib.parse.quote(f'"{competitor_name}" clinical trial AI')
    url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()

        root = ET.fromstring(xml_data)
        items = root.findall(".//item")

        results = []
        for item in items[:max_results]:
            title = clean_html(item.findtext("title", ""))
            link = item.findtext("link", "")
            pub_date = item.findtext("pubDate", "")
            description = clean_html(item.findtext("description", ""))

            if title:
                results.append({
                    "title": title,
                    "url": link,
                    "date": pub_date,
                    "description": description[:200] if description else ""
                })

        return results

    except Exception as e:
        print(f"    RSS error for {competitor_name}: {e}")
        return []


# ── Step 2: Collect all signals ───────────────────────────────────────────────
def collect_all_signals() -> list:
    all_signals = []

    for i, competitor in enumerate(COMPETITORS):
        name = competitor["name"]
        segment = competitor["segment"]
        print(f"  [{i+1}/{len(COMPETITORS)}] {name}...")

        articles = fetch_google_news(name)

        if articles:
            for article in articles:
                all_signals.append({
                    "competitor": name,
                    "segment": segment,
                    "focus": competitor["focus"],
                    "title": article["title"],
                    "url": article["url"],
                    "date": article["date"],
                    "description": article["description"]
                })
            print(f"    + {len(articles)} articles")
        else:
            print(f"    - nothing")

        time.sleep(0.5)

    return all_signals


# ── Step 3: Single Claude call ────────────────────────────────────────────────
def analyze_with_claude(signals: list, week: str) -> Optional[dict]:
    if not signals:
        return None

    signals_text = ""
    for s in signals:
        signals_text += f"\n---\nCompetitor: {s['competitor']} ({s['segment']})\nHeadline: {s['title']}\nDate: {s['date']}\nSummary: {s['description']}\nURL: {s['url']}\n"

    prompt = f"""You are a competitive intelligence analyst for Biorce, an AI-native clinical trial platform.

BIORCE CONTEXT:
- Product: Aika — explainable AI for protocol design, feasibility, and regulatory planning
- Differentiator: 100% explainable AI (not a black box)
- Target: Pharma companies and CROs
- Key threats: competitors gaining traction in protocol design AI, feasibility, or explainability

WEEK: {week}

Below are news signals from 50 competitors in the AI-Clinical Trial space.
Select the TOP 3 most strategically relevant for Biorce's leadership.

Prioritize:
1. Direct competitive threats (protocol/feasibility/regulatory AI)
2. Large funding or acquisitions
3. Major pharma partnerships
4. FDA/EMA mentions
5. Explainability claims

NEWS SIGNALS:
{signals_text}

Respond ONLY with this exact JSON, no other text:
{{
  "top_3": [
    {{
      "rank": 1,
      "urgency": "high",
      "competitor": "Name",
      "segment": "Segment",
      "what_happened": "One factual sentence.",
      "why_it_matters": "One sentence for Biorce.",
      "source_url": "https://...",
      "action_suggested": ""
    }},
    {{
      "rank": 2,
      "urgency": "medium",
      "competitor": "Name",
      "segment": "Segment",
      "what_happened": "One factual sentence.",
      "why_it_matters": "One sentence for Biorce.",
      "source_url": "https://...",
      "action_suggested": ""
    }},
    {{
      "rank": 3,
      "urgency": "low",
      "competitor": "Name",
      "segment": "Segment",
      "what_happened": "One factual sentence.",
      "why_it_matters": "One sentence for Biorce.",
      "source_url": "https://...",
      "action_suggested": ""
    }}
  ]
}}"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}]
        )

        text = response.content[0].text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            return None

        return json.loads(text[start:end])

    except Exception as e:
        print(f"Claude error: {e}")
        return None


# ── Step 4: Format Slack ──────────────────────────────────────────────────────
def format_slack_message(top_3: list, week: str) -> str:
    emoji_map = {1: "🔴", 2: "🟡", 3: "🟢"}
    lines = [
        f"📊 *Weekly Competitor Intelligence — {today_str()}*",
        f"Biorce | AI-Clinical Trial Space | Week: {week}",
        ""
    ]

    if not top_3:
        lines.append("No high-relevance updates found this week.")
        return "\n".join(lines)

    for item in top_3:
        rank = item.get("rank", 1)
        lines += [
            f"{emoji_map.get(rank, '⚪')} *{rank}. {item['competitor']}* — {item['segment']}",
            f"What happened: {item['what_happened']}",
            f"Why it matters: {item['why_it_matters']}",
            f"Source: {item.get('source_url', 'N/A')}",
            ""
        ]

    actions = [item.get("action_suggested", "") for item in top_3 if item.get("action_suggested")]
    if actions:
        lines.append(f"💡 *Action suggested:* {actions[0]}")

    return "\n".join(lines)


# ── Step 5: Save outputs ──────────────────────────────────────────────────────
def save_outputs(top_3: list, all_signals: list, slack_message: str):
    date = today_str()
    brief = {
        "week": date,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "top_3": top_3
    }

    with open(os.path.join(OUTPUT_DIR, f"weekly_brief_{date}.json"), "w") as f:
        json.dump(brief, f, indent=2)
    print(f"Brief saved: output/weekly_brief_{date}.json")

    with open(os.path.join(OUTPUT_DIR, "latest.json"), "w") as f:
        json.dump(brief, f, indent=2)

    log_path = os.path.join(OUTPUT_DIR, "signal_log.json")
    existing = []
    if os.path.exists(log_path):
        with open(log_path) as f:
            existing = json.load(f)
    existing.append({"run_date": date, "total_signals": len(all_signals), "signals": all_signals})
    with open(log_path, "w") as f:
        json.dump(existing, f, indent=2)

    with open(os.path.join(OUTPUT_DIR, f"weekly_brief_{date}.txt"), "w") as f:
        f.write(slack_message)
    print(f"Slack message saved: output/weekly_brief_{date}.txt")


# ── Step 6: Slack ─────────────────────────────────────────────────────────────
def post_to_slack(message: str):
    if not SLACK_WEBHOOK_URL:
        print("\n── SLACK OUTPUT PREVIEW ──────────────────────────────")
        print(message)
        print("──────────────────────────────────────────────────────\n")
        return
    try:
        payload = json.dumps({"text": message}).encode("utf-8")
        req = urllib.request.Request(SLACK_WEBHOOK_URL, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            if resp.status == 200:
                print("Posted to Slack.")
    except Exception as e:
        print(f"Slack error: {e}")


# ── Step 7: GitHub ────────────────────────────────────────────────────────────
def push_to_github():
    try:
        subprocess.run(["git", "add", "output/"], check=True)
        subprocess.run(["git", "commit", "-m", f"Weekly brief {today_str()}"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("Pushed to GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"GitHub push failed: {e}")


# ── Main ──────────────────────────────────────────────────────────────────────
def run():
    print(f"\n🚀 Biorce Intel Agent v2 — {today_str()}")
    print(f"   Scanning {len(COMPETITORS)} competitors via Google News RSS...\n")

    week = week_window()
    all_signals = collect_all_signals()
    print(f"\n📥 Total signals: {len(all_signals)}")

    all_signals_for_claude = all_signals[:60]

    print("\n🤖 Analyzing with Claude (1 API call)...")
    result = analyze_with_claude(all_signals_for_claude, week)

    top_3 = result.get("top_3", []) if result else []
    print(f"🏆 Top 3 selected\n")

    slack_message = format_slack_message(top_3, week)
    save_outputs(top_3, all_signals, slack_message)
    post_to_slack(slack_message)
    push_to_github()

    print("\n✅ Done.")


if __name__ == "__main__":
    run()
