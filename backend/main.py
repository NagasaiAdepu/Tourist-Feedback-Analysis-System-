"""Warangal Tourist Review Sentiment and Feedback Analysis System: FastAPI application.

Run:  uvicorn backend.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from backend import config, repository
from backend.attractions import VISITOR_TYPES
from backend.database import init_db
from backend.models import AnalyzeRequest, ReviewIn
from backend.nlp.aspects import ASPECTS
from backend.nlp.pipeline import analyze_review
from backend.nlp.sentiment import get_model
from backend.services import analytics_service, evaluation_service

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
Sentiment = Optional[Literal["positive", "neutral", "negative"]]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    get_model()                      # train or load the model once at start-up
    if config.SEED_SAMPLE:
        repository.seed_sample_reviews()
    yield


app = FastAPI(title="Warangal Tourist Review Sentiment & Feedback Analysis", version="1.0.0",
              description="NLP-based analysis of tourist reviews for Warangal attractions", lifespan=lifespan)


def _filters(attraction_id, sentiment, aspect, q, date_from, date_to, visitor_type) -> dict:
    if aspect and aspect not in ASPECTS:
        raise HTTPException(status_code=400, detail=f"Unknown aspect '{aspect}'")
    if attraction_id and not repository.get_attraction(attraction_id):
        raise HTTPException(status_code=404, detail="Attraction not found")
    return {"attraction_id": attraction_id, "sentiment": sentiment, "aspect": aspect, "q": q,
            "date_from": date_from, "date_to": date_to, "visitor_type": visitor_type}


DATE = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$")
VISITOR = Query(None, pattern="^(" + "|".join(VISITOR_TYPES) + ")$")


# ---------- Reference data ----------
@app.get("/api/meta")
def meta():
    return {"attractions": repository.list_attractions(),
            "aspects": [{"key": k, "label": v["label"]} for k, v in ASPECTS.items()],
            "visitor_types": list(VISITOR_TYPES)}


# ---------- Analysis ----------
@app.post("/api/analyze")
def analyze(body: AnalyzeRequest):
    """Analyse text without saving it (live analyser)."""
    return analyze_review(body.text)


# ---------- Reviews ----------
@app.post("/api/reviews", status_code=201)
def create_review(body: ReviewIn):
    if not repository.get_attraction(body.attraction_id):
        raise HTTPException(status_code=404, detail="Attraction not found")
    row = body.model_dump()
    row["visit_date"] = body.visit_date.isoformat() if body.visit_date else None
    review_id = repository.insert_reviews([row], source="form")[0]["id"]
    return {"id": review_id, "analysis": analyze_review(body.text)}


@app.get("/api/reviews")
def list_reviews(attraction_id: Optional[int] = None, sentiment: Sentiment = None, aspect: Optional[str] = None,
                 q: Optional[str] = Query(None, max_length=100), date_from: Optional[str] = DATE,
                 date_to: Optional[str] = DATE, visitor_type: Optional[str] = VISITOR,
                 sort: Literal["newest", "oldest", "most_negative", "most_positive"] = "newest",
                 limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    filters = _filters(attraction_id, sentiment, aspect, q, date_from, date_to, visitor_type)
    return repository.list_reviews(limit=limit, offset=offset, sort=sort, **filters)


@app.delete("/api/reviews/{review_id}")
def delete_review(review_id: int):
    if not repository.delete_review(review_id):
        raise HTTPException(status_code=404, detail="Review not found")
    return {"ok": True}


@app.post("/api/reviews/upload", status_code=201)
async def upload_reviews(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a .csv file")
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File is larger than {config.MAX_UPLOAD_MB} MB")
    try:
        rows, errors = repository.parse_csv(raw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not rows:
        raise HTTPException(status_code=400, detail={"message": "No valid reviews found in the file",
                                                     "errors": errors[:50]})
    created = repository.insert_reviews(rows, source="csv")
    summary = {s: sum(r["sentiment"] == s for r in created) for s in ("positive", "neutral", "negative")}
    return {"imported": len(created), "skipped": len(errors), "errors": errors[:50], "sentiment": summary}


# ---------- Insights ----------
@app.get("/api/dashboard")
def get_dashboard(attraction_id: Optional[int] = None, date_from: Optional[str] = DATE,
                  date_to: Optional[str] = DATE, visitor_type: Optional[str] = VISITOR):
    filters = _filters(attraction_id, None, None, None, date_from, date_to, visitor_type)
    return analytics_service.dashboard(**filters)


@app.get("/api/attractions/{attraction_id}/insights")
def get_insights(attraction_id: int):
    attraction = repository.get_attraction(attraction_id)
    if not attraction:
        raise HTTPException(status_code=404, detail="Attraction not found")
    return {"attraction": attraction, **analytics_service.attraction_insights(attraction_id)}


@app.get("/api/model/evaluation")
def model_evaluation():
    return evaluation_service.evaluate()


@app.get("/api/export.csv")
def export(attraction_id: Optional[int] = None, sentiment: Sentiment = None, aspect: Optional[str] = None,
           date_from: Optional[str] = DATE, date_to: Optional[str] = DATE):
    filters = _filters(attraction_id, sentiment, aspect, None, date_from, date_to, None)
    return Response(analytics_service.export_csv(**filters), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="warangal_reviews_analysis.csv"'})


# ---------- Frontend ----------
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
