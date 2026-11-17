"""Data access for attractions and reviews."""

import csv
import io
from datetime import date

from backend import config
from backend.attractions import VISITOR_TYPES
from backend.database import get_db
from backend.nlp.pipeline import analyze_reviews


# ---------- Attractions ----------
def list_attractions() -> list[dict]:
    with get_db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM attractions ORDER BY id")]


def get_attraction(attraction_id: int) -> dict | None:
    with get_db() as db:
        row = db.execute("SELECT * FROM attractions WHERE id = ?", (attraction_id,)).fetchone()
    return dict(row) if row else None


def attraction_lookup() -> dict[str, int]:
    """Lower-case name and slug -> id, used to match the attraction column of uploaded CSVs."""
    out = {}
    for a in list_attractions():
        out[a["name"].lower()] = a["id"]
        out[a["slug"]] = a["id"]
    return out


# ---------- Reviews ----------
def insert_reviews(rows: list[dict], source: str) -> list[dict]:
    """Analyse and store reviews. Each row: attraction_id, text, rating, visit_date,
    visitor_type, reviewer_name (all but attraction_id and text optional).
    Returns [{"id": ..., "sentiment": ...}] in the same order."""
    analyses = analyze_reviews([r["text"] for r in rows])
    ids = []
    with get_db() as db:
        for row, a in zip(rows, analyses):
            s = a["sentiment"]
            cur = db.execute(
                """INSERT INTO reviews (attraction_id, reviewer_name, visitor_type, rating, visit_date, text,
                   source, sentiment, confidence, vader_compound, vader_label, ml_label)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (row["attraction_id"], row.get("reviewer_name"), row.get("visitor_type"), row.get("rating"),
                 row.get("visit_date"), row["text"], source, s["label"], s["confidence"],
                 s["vader_compound"], s["vader_label"], s["ml_label"]))
            db.executemany(
                "INSERT INTO review_aspects (review_id, aspect, sentiment, score, snippet) VALUES (?, ?, ?, ?, ?)",
                [(cur.lastrowid, x["aspect"], x["sentiment"], x["score"], x["snippet"]) for x in a["aspects"]])
            ids.append({"id": cur.lastrowid, "sentiment": s["label"]})
    return ids


def build_filters(attraction_id=None, sentiment=None, aspect=None, q=None, date_from=None, date_to=None,
                  visitor_type=None) -> tuple[str, list]:
    where, params = ["1 = 1"], []
    if attraction_id:
        where.append("r.attraction_id = ?"); params.append(attraction_id)
    if sentiment:
        where.append("r.sentiment = ?"); params.append(sentiment)
    if visitor_type:
        where.append("r.visitor_type = ?"); params.append(visitor_type)
    if aspect:
        where.append("EXISTS (SELECT 1 FROM review_aspects x WHERE x.review_id = r.id AND x.aspect = ?)")
        params.append(aspect)
    if q:
        where.append("r.text LIKE ?"); params.append(f"%{q}%")
    if date_from:
        where.append("r.visit_date >= ?"); params.append(date_from)
    if date_to:
        where.append("r.visit_date <= ?"); params.append(date_to)
    return " AND ".join(where), params


def list_reviews(limit: int = 20, offset: int = 0, sort: str = "newest", **filters) -> dict:
    where, params = build_filters(**filters)
    order = {"newest": "r.visit_date DESC, r.id DESC", "oldest": "r.visit_date ASC, r.id ASC",
             "most_negative": "r.vader_compound ASC", "most_positive": "r.vader_compound DESC"}[sort]
    with get_db() as db:
        total = db.execute(f"SELECT COUNT(*) FROM reviews r WHERE {where}", params).fetchone()[0]
        rows = [dict(r) for r in db.execute(
            f"""SELECT r.*, a.name AS attraction FROM reviews r JOIN attractions a ON a.id = r.attraction_id
                WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?""", [*params, limit, offset])]
        for r in rows:
            r["aspects"] = [dict(x) for x in db.execute(
                "SELECT aspect, sentiment, score, snippet FROM review_aspects WHERE review_id = ?", (r["id"],))]
    return {"total": total, "reviews": rows}


def delete_review(review_id: int) -> bool:
    with get_db() as db:
        return db.execute("DELETE FROM reviews WHERE id = ?", (review_id,)).rowcount > 0


def review_count() -> int:
    with get_db() as db:
        return db.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]


# ---------- CSV import ----------
def parse_csv(raw: bytes) -> tuple[list[dict], list[dict]]:
    """Validate an uploaded CSV. Required columns: attraction, text. Optional: rating, visit_date,
    visitor_type, reviewer_name. Returns (valid_rows, errors)."""
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The file must be UTF-8 encoded CSV")
    reader = csv.DictReader(io.StringIO(content))
    fields = {f.strip().lower() for f in (reader.fieldnames or [])}
    missing = {"attraction", "text"} - fields
    if missing:
        raise ValueError(f"Missing required column(s): {', '.join(sorted(missing))}")
    lookup = attraction_lookup()
    rows, errors = [], []
    for i, raw_row in enumerate(reader, start=2):              # row 1 is the header
        if len(rows) + len(errors) >= config.MAX_CSV_ROWS:
            errors.append({"row": i, "error": f"Stopped: more than {config.MAX_CSV_ROWS} rows"})
            break
        r = {(k or "").strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        attraction_id = lookup.get(r.get("attraction", "").lower())
        text = r.get("text", "")
        problem = None
        if not attraction_id:
            problem = f"Unknown attraction '{r.get('attraction', '')}'"
        elif len(text.split()) < 3:
            problem = "Review text is empty or too short"
        rating = r.get("rating") or None
        if not problem and rating is not None:
            if not rating.isdigit() or not 1 <= int(rating) <= 5:
                problem = "Rating must be a whole number from 1 to 5"
        visit_date = r.get("visit_date") or None
        if not problem and visit_date:
            try:
                if date.fromisoformat(visit_date) > date.today():
                    problem = "Visit date is in the future"
            except ValueError:
                problem = "Visit date must look like 2026-01-31"
        visitor_type = r.get("visitor_type") or None
        if not problem and visitor_type and visitor_type not in VISITOR_TYPES:
            problem = f"Visitor type must be one of: {', '.join(VISITOR_TYPES)}"
        if problem:
            errors.append({"row": i, "error": problem})
            continue
        rows.append({"attraction_id": attraction_id, "text": text[:3000],
                     "rating": int(rating) if rating else None, "visit_date": visit_date,
                     "visitor_type": visitor_type, "reviewer_name": (r.get("reviewer_name") or None)})
    return rows, errors


def seed_sample_reviews() -> int:
    """Load datasets/warangal_reviews.csv into an empty database (first start)."""
    if review_count() > 0 or not config.DATASET_PATH.exists():
        return 0
    rows, _ = parse_csv(config.DATASET_PATH.read_bytes())
    return len(insert_reviews(rows, source="sample"))
