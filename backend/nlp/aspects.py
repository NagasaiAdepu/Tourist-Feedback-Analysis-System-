"""Aspect-based sentiment: which parts of the visit (cleanliness, crowd, parking ...)
a review talks about, and whether each part is praised or criticised."""

import re

from backend.nlp.preprocess import split_clauses, split_sentences
from backend.nlp.sentiment import vader_compound, vader_label

ASPECTS = {
    "cleanliness": {"label": "Cleanliness & Hygiene", "terms": [
        "clean", "cleaner", "cleanliness", "dirty", "garbage", "litter", "littered", "plastic", "hygiene",
        "hygienic", "toilet", "toilets", "washroom", "washrooms", "restroom", "restrooms", "trash",
        "dustbin", "dustbins", "smell", "smelly", "stink", "filthy", "waste", "spotless", "tidy", "sanitation"]},
    "crowd": {"label": "Crowd & Waiting", "terms": [
        "crowd", "crowded", "crowds", "rush", "queue", "queues", "waiting", "waited", "busy",
        "peaceful", "calm", "quiet", "packed", "darshan", "overcrowded", "serene"]},
    "access": {"label": "Access & Parking", "terms": [
        "road", "roads", "parking", "transport", "bus", "buses", "auto", "cab", "reach",
        "reached", "distance", "directions", "signboard", "signboards", "signage", "wheelchair", "ramp",
        "steps", "stairs", "route", "potholes", "highway", "connectivity"]},
    "pricing": {"label": "Ticket & Value", "terms": [
        "ticket", "tickets", "price", "prices", "priced", "fee", "fees", "entry", "cost", "costly",
        "expensive", "cheap", "affordable", "worth", "money", "overpriced", "charges", "charged", "free"]},
    "facilities": {"label": "Facilities & Amenities", "terms": [
        "drinking water", "water bottle", "food", "canteen", "shade", "seating", "benches", "bench", "shops",
        "stalls", "restaurant", "facilities", "facility", "lighting", "lights", "cloakroom", "amenities",
        "dustbin", "boating", "boat", "boats", "play area", "fountain", "snacks"]},
    "heritage": {"label": "Heritage & Architecture", "terms": [
        "architecture", "carving", "carvings", "carved", "sculpture", "sculptures", "history",
        "historical", "pillars", "pillar", "heritage", "ancient", "kakatiya", "monument", "art",
        "craftsmanship", "gateways", "gateway", "thoranam", "ruins", "nandi", "idol", "unesco", "bricks"]},
    "staff": {"label": "Staff & Guides", "terms": [
        "guide", "guides", "staff", "security", "guard", "guards", "helpful", "rude", "information",
        "priest", "priests", "employees", "officials", "volunteers", "keeper", "keepers", "audio guide"]},
    "nature": {"label": "Scenery & Nature", "terms": [
        "lake", "view", "views", "scenery", "scenic", "sunset", "sunrise", "greenery", "green", "nature",
        "trees", "island", "islands", "hanging bridge", "bridge", "wildlife", "birds", "forest", "animals",
        "landscape", "lawns", "garden", "hill", "hilltop"]},
    "safety": {"label": "Safety & Security", "terms": [
        "safe", "safety", "unsafe", "theft", "thieves", "police", "dangerous", "railing", "railings",
        "lifejacket", "lifejackets", "life jackets", "drunk", "harassment", "secure", "risky"]},
}

_PATTERNS = {
    key: re.compile(r"\b(" + "|".join(re.escape(t) for t in sorted(a["terms"], key=len, reverse=True)) + r")\b",
                    re.IGNORECASE)
    for key, a in ASPECTS.items()
}


def aspect_label(key: str) -> str:
    return ASPECTS[key]["label"]


def extract_aspects(text: str) -> list[dict]:
    """Return one entry per aspect mentioned:
    {aspect, label, sentiment, score, mentions, snippet}. The score is the mean VADER
    compound of the clauses that mention the aspect."""
    found: dict[str, dict] = {}
    for sentence in split_sentences(text):
        for clause in split_clauses(sentence) or [sentence]:
            for key, pattern in _PATTERNS.items():
                if not pattern.search(clause):
                    continue
                score = vader_compound(clause)
                entry = found.setdefault(key, {"scores": [], "snippets": []})
                entry["scores"].append(score)
                entry["snippets"].append(clause)
    out = []
    for key, e in found.items():
        score = sum(e["scores"]) / len(e["scores"])
        # Use the most opinionated clause as the evidence shown to the user.
        snippet = max(zip(e["scores"], e["snippets"]), key=lambda p: abs(p[0]))[1]
        out.append({"aspect": key, "label": aspect_label(key), "sentiment": vader_label(score),
                    "score": round(score, 3), "mentions": len(e["scores"]), "snippet": snippet[:200]})
    return sorted(out, key=lambda a: list(ASPECTS).index(a["aspect"]))
