"""Dashboard statistics and per-attraction insights (all aggregation happens on the server)."""

import csv
import io

from backend.database import get_db
from backend.nlp.aspects import ASPECTS, aspect_label
from backend.nlp.keywords import contrast_keywords
from backend.nlp.recommendations import build_insights
from backend.repository import build_filters

SENTIMENTS = ("positive", "neutral", "negative")


def _net(pos: int, neg: int, total: int) -> int:
    """Net sentiment score from -100 (all negative) to +100 (all positive)."""
    return round((pos - neg) / total * 100) if total else 0


def _distribution(db, where: str, params: list) -> dict:
    counts = {s: 0 for s in SENTIMENTS}
    for r in db.execute(f"SELECT sentiment, COUNT(*) n FROM reviews r WHERE {where} GROUP BY sentiment", params):
        counts[r["sentiment"]] = r["n"]
    return counts


def _aspect_stats(db, where: str, params: list) -> dict[str, dict]:
    stats: dict[str, dict] = {}
    for r in db.execute(
            f"""SELECT x.aspect, x.sentiment, COUNT(*) n FROM review_aspects x JOIN reviews r ON r.id = x.review_id
                WHERE {where} GROUP BY x.aspect, x.sentiment""", params):
        stats.setdefault(r["aspect"], {s: 0 for s in SENTIMENTS})[r["sentiment"]] = r["n"]
    return stats


def dashboard(**filters) -> dict:
    where, params = build_filters(**filters)
    with get_db() as db:
        dist = _distribution(db, where, params)
        total = sum(dist.values())
        avg_rating = db.execute(f"SELECT AVG(rating) FROM reviews r WHERE {where} AND rating IS NOT NULL",
                                params).fetchone()[0]

        per_attraction = []
        for r in db.execute(
                f"""SELECT a.id, a.name, COUNT(r.id) n, AVG(r.rating) rating,
                       SUM(r.sentiment = 'positive') pos, SUM(r.sentiment = 'neutral') neu,
                       SUM(r.sentiment = 'negative') neg
                    FROM attractions a JOIN reviews r ON r.attraction_id = a.id
                    WHERE {where} GROUP BY a.id ORDER BY a.id""", params):
            per_attraction.append({"id": r["id"], "name": r["name"], "reviews": r["n"],
                                   "avg_rating": round(r["rating"], 2) if r["rating"] else None,
                                   "positive": r["pos"], "neutral": r["neu"], "negative": r["neg"],
                                   "net_score": _net(r["pos"], r["neg"], r["n"])})
        per_attraction.sort(key=lambda a: a["net_score"], reverse=True)

        # Heatmap: attraction x aspect net score
        heat: dict[int, dict] = {}
        for r in db.execute(
                f"""SELECT r.attraction_id aid, x.aspect, COUNT(*) n,
                       SUM(x.sentiment = 'positive') pos, SUM(x.sentiment = 'negative') neg
                    FROM review_aspects x JOIN reviews r ON r.id = x.review_id
                    WHERE {where} GROUP BY r.attraction_id, x.aspect""", params):
            heat.setdefault(r["aid"], {})[r["aspect"]] = {"mentions": r["n"], "net_score": _net(r["pos"], r["neg"], r["n"])}
        heatmap = [{"id": a["id"], "name": a["name"], "cells": heat.get(a["id"], {})} for a in per_attraction]

        aspect_stats = _aspect_stats(db, where, params)
        aspects = []
        for key in ASPECTS:
            s = aspect_stats.get(key, {s_: 0 for s_ in SENTIMENTS})
            n = sum(s.values())
            aspects.append({"aspect": key, "label": aspect_label(key), "mentions": n, **s,
                            "net_score": _net(s["positive"], s["negative"], n)})

        trend = {}
        for r in db.execute(
                f"""SELECT substr(r.visit_date, 1, 7) month, r.sentiment, COUNT(*) n FROM reviews r
                    WHERE {where} AND r.visit_date IS NOT NULL GROUP BY month, r.sentiment ORDER BY month""", params):
            trend.setdefault(r["month"], {s: 0 for s in SENTIMENTS})[r["sentiment"]] = r["n"]
        monthly = [{"month": m, **c, "net_score": _net(c["positive"], c["negative"], sum(c.values()))}
                   for m, c in sorted(trend.items())]

        visitors = {}
        for r in db.execute(
                f"""SELECT COALESCE(r.visitor_type, 'unknown') vt, COUNT(*) n, SUM(r.sentiment = 'positive') pos,
                       SUM(r.sentiment = 'negative') neg FROM reviews r WHERE {where} GROUP BY vt""", params):
            visitors[r["vt"]] = {"reviews": r["n"], "net_score": _net(r["pos"], r["neg"], r["n"])}

        texts = {s: [r["text"] for r in db.execute(
            f"SELECT text FROM reviews r WHERE {where} AND r.sentiment = ?", [*params, s])] for s in ("positive", "negative")}

        # Rating says one thing, the text says another: worth a manual look.
        mismatches = [dict(r) for r in db.execute(
            f"""SELECT r.id, a.name attraction, r.rating, r.sentiment, r.text FROM reviews r
                JOIN attractions a ON a.id = r.attraction_id WHERE {where} AND
                ((r.rating >= 4 AND r.sentiment = 'negative') OR (r.rating <= 2 AND r.sentiment = 'positive'))
                ORDER BY r.visit_date DESC LIMIT 10""", params)]

    return {
        "total_reviews": total,
        "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "distribution": dist,
        "percentages": {s: round(dist[s] / total * 100) if total else 0 for s in SENTIMENTS},
        "net_score": _net(dist["positive"], dist["negative"], total),
        "attractions": per_attraction,
        "aspects": aspects,
        "heatmap": heatmap,
        "monthly": monthly,
        "visitor_types": visitors,
        "keywords": contrast_keywords(texts["positive"], texts["negative"]),
        "mismatches": mismatches,
    }


def attraction_insights(attraction_id: int) -> dict:
    where, params = build_filters(attraction_id=attraction_id)
    with get_db() as db:
        dist = _distribution(db, where, params)
        total = sum(dist.values())
        avg_rating = db.execute(f"SELECT AVG(rating) FROM reviews r WHERE {where}", params).fetchone()[0]
        insights = build_insights(_aspect_stats(db, where, params))

        def sample(sentiment: str, order: str) -> list[dict]:
            return [dict(r) for r in db.execute(
                f"""SELECT id, rating, visit_date, visitor_type, text, confidence FROM reviews r
                    WHERE {where} AND sentiment = ? ORDER BY {order} LIMIT 3""", [*params, sentiment])]

        texts = {s: [r["text"] for r in db.execute(
            f"SELECT text FROM reviews r WHERE {where} AND r.sentiment = ?", [*params, s])] for s in ("positive", "negative")}
        recent = db.execute(
            f"""SELECT SUM(sentiment = 'positive') pos, SUM(sentiment = 'negative') neg, COUNT(*) n
                FROM (SELECT sentiment FROM reviews r WHERE {where} ORDER BY visit_date DESC LIMIT 50)""", params).fetchone()
        top_positive = sample("positive", "vader_compound DESC")
        top_negative = sample("negative", "vader_compound ASC")

    summary = _summary_sentence(total, dist, insights)
    return {
        "total_reviews": total, "avg_rating": round(avg_rating, 2) if avg_rating else None,
        "distribution": dist, "net_score": _net(dist["positive"], dist["negative"], total),
        "recent_net_score": _net(recent["pos"] or 0, recent["neg"] or 0, recent["n"]),
        "summary": summary, **insights,
        "keywords": contrast_keywords(texts["positive"], texts["negative"], top_n=10, min_count=2),
        "top_positive": top_positive,
        "top_negative": top_negative,
    }


def _summary_sentence(total: int, dist: dict, insights: dict) -> str:
    if not total:
        return "No reviews yet for this attraction."
    pos = round(dist["positive"] / total * 100)
    parts = [f"{pos}% of {total} reviews are positive."]
    if insights["strengths"]:
        parts.append("Visitors appreciate " + ", ".join(s["label"].lower() for s in insights["strengths"][:2]) + ".")
    if insights["issues"]:
        parts.append("Main concerns: " + ", ".join(i["label"].lower() for i in insights["issues"][:2]) + ".")
    return " ".join(parts)


def export_csv(**filters) -> str:
    where, params = build_filters(**filters)
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["id", "attraction", "reviewer_name", "visitor_type", "rating", "visit_date", "sentiment",
                     "confidence", "vader_compound", "aspects", "text"])
    with get_db() as db:
        for r in db.execute(
                f"""SELECT r.*, a.name attraction,
                       (SELECT GROUP_CONCAT(x.aspect || ':' || x.sentiment, '; ') FROM review_aspects x
                        WHERE x.review_id = r.id) aspects
                    FROM reviews r JOIN attractions a ON a.id = r.attraction_id WHERE {where}
                    ORDER BY r.visit_date DESC""", params):
            writer.writerow([r["id"], r["attraction"], r["reviewer_name"], r["visitor_type"], r["rating"],
                             r["visit_date"], r["sentiment"], r["confidence"], r["vader_compound"],
                             r["aspects"] or "", r["text"]])
    return out.getvalue()
