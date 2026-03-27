"""
Relevance scoring logic for Biorce competitive intelligence agent.
Scores updates 1-5 based on strategic relevance to Biorce/Aika.
"""

# Keywords that indicate high-priority signals for Biorce
HIGH_PRIORITY_KEYWORDS = [
    # Direct competitive threats
    "protocol design", "protocol optimization", "feasibility", "explainable ai", "explainability",
    "regulatory planning", "regulatory ai", "amendment prevention", "protocol amendment",
    # Business signals
    "funding", "series", "raised", "million", "acquisition", "acquires", "merger",
    "partnership", "collaboration", "pharma deal", "contract",
    # Product signals
    "launch", "product launch", "new feature", "platform update", "general availability",
    "fda", "ema", "regulatory approval", "cleared",
]

MEDIUM_PRIORITY_KEYWORDS = [
    "clinical trial", "trial design", "site selection", "patient recruitment",
    "real world evidence", "rwe", "decentralized", "dct", "ehr", "electronic health",
    "biomarker", "adaptive design", "ai agent", "agentic",
    "hiring", "expansion", "new market", "apac", "europe", "us market",
]

LOW_PRIORITY_KEYWORDS = [
    "conference", "webinar", "award", "whitepaper", "report", "survey",
    "thought leadership", "blog", "podcast",
]

# Segments that are most critical for Biorce (overlap with Aika modules)
CRITICAL_SEGMENTS = ["Protocol Design", "Regulatory & Compliance", "Site Selection & Feasibility"]
IMPORTANT_SEGMENTS = ["Trial Operations", "Patient Recruitment"]
BROAD_SEGMENTS = ["Broad Platform"]


def score_update(text: str, segment: str) -> int:
    """
    Score a competitor update from 1 to 5.
    
    5 = Direct competitive threat (new protocol/feasibility/regulatory product, large funding, major pharma deal)
    4 = Indirect threat or significant market signal
    3 = Noteworthy but not urgent
    2 = Low relevance
    1 = Irrelevant
    """
    text_lower = text.lower()
    score = 2

    # Base score by segment
    if segment in CRITICAL_SEGMENTS:
        score += 2
    elif segment in IMPORTANT_SEGMENTS:
        score += 1

    # Keyword boosting
    high_hits = sum(1 for kw in HIGH_PRIORITY_KEYWORDS if kw in text_lower)
    medium_hits = sum(1 for kw in MEDIUM_PRIORITY_KEYWORDS if kw in text_lower)

    if high_hits >= 2:
        score += 2
    elif high_hits == 1:
        score += 1

    if medium_hits >= 3:
        score += 1

    # Penalty for low-priority only content
    low_hits = sum(1 for kw in LOW_PRIORITY_KEYWORDS if kw in text_lower)
    if low_hits > 0 and high_hits == 0 and medium_hits <= 1:
        score -= 1

    # Cap at 5
    return min(max(score, 1), 5)


def urgency_label(score: int) -> str:
    if score == 5:
        return "high"
    elif score == 4:
        return "medium"
    else:
        return "low"


def emoji_for_rank(rank: int) -> str:
    return {1: "🔴", 2: "🟡", 3: "🟢"}.get(rank, "⚪")
