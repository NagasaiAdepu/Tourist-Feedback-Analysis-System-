"""Turn aspect statistics into strengths, issues and action points for tourism authorities."""

from backend.nlp.aspects import ASPECTS, aspect_label

ACTIONS = {
    "cleanliness": "Deploy more sanitation staff and dustbins, clean toilets on a fixed schedule and display a cleanliness helpline number.",
    "crowd": "Introduce timed entry slots or online darshan/entry booking for weekends and festivals, and add queue shelters.",
    "access": "Improve approach roads and signboards, mark parking bays and run shuttle or bus services from Warangal and Hanamkonda.",
    "pricing": "Review ticket and parking charges, add combo tickets for nearby sites and publish a clear price board.",
    "facilities": "Provide drinking water points, shaded seating, clean food stalls and better lighting.",
    "heritage": "Restore damaged structures, add multilingual information boards and QR-code audio guides about Kakatiya history.",
    "staff": "Train and license guides, place an information desk at the entrance and brief staff on courteous behaviour.",
    "nature": "Protect the greenery and water body, remove plastic waste and maintain viewpoints and walking paths.",
    "safety": "Add railings and life jackets where needed, increase security patrols and CCTV, and display emergency numbers.",
}

MIN_MENTIONS = 3


def build_insights(aspect_stats: dict[str, dict]) -> dict:
    """aspect_stats: {aspect: {"positive": n, "neutral": n, "negative": n}}.
    Returns strengths, issues (with priority and recommendation) and per-aspect summary rows."""
    rows, strengths, issues = [], [], []
    for key in ASPECTS:
        s = aspect_stats.get(key)
        if not s:
            continue
        total = s["positive"] + s["neutral"] + s["negative"]
        if not total:
            continue
        pos_share, neg_share = s["positive"] / total, s["negative"] / total
        net = round((s["positive"] - s["negative"]) / total * 100)
        row = {"aspect": key, "label": aspect_label(key), "mentions": total,
               "positive": s["positive"], "neutral": s["neutral"], "negative": s["negative"],
               "positive_pct": round(pos_share * 100), "negative_pct": round(neg_share * 100), "net_score": net}
        rows.append(row)
        if total < MIN_MENTIONS:
            continue
        if neg_share >= 0.3:
            priority = "high" if neg_share >= 0.5 else "medium"
            issues.append({**row, "priority": priority, "recommendation": ACTIONS[key]})
        elif pos_share >= 0.6:
            strengths.append(row)
    issues.sort(key=lambda r: (r["priority"] != "high", -r["negative_pct"], -r["mentions"]))
    strengths.sort(key=lambda r: (-r["positive_pct"], -r["mentions"]))
    return {"aspects": rows, "strengths": strengths, "issues": issues}
