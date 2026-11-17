"""Tests for the NLP pipeline and the API. Each test run uses a fresh temporary data folder."""

import io
import os
import tempfile

import pytest

_tmp = tempfile.mkdtemp()
os.environ["NLP_DATA_DIR"] = _tmp
os.environ["NLP_SEED_SAMPLE"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from backend import config, repository  # noqa: E402
from backend.database import get_db  # noqa: E402
from backend.main import app  # noqa: E402
from backend.nlp import preprocess as pp  # noqa: E402
from backend.nlp.aspects import extract_aspects  # noqa: E402
from backend.nlp.keywords import contrast_keywords, extract_keywords  # noqa: E402
from backend.nlp.recommendations import build_insights  # noqa: E402
from backend.nlp.sentiment import analyze_sentiment, vader_label, vader_proba  # noqa: E402


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_reviews(client):     # depends on client so the database exists first
    yield
    with get_db() as db:
        db.execute("DELETE FROM reviews")


def attraction_id(client, name="Ramappa Temple"):
    return next(a["id"] for a in client.get("/api/meta").json()["attractions"] if a["name"] == name)


# ---------- Preprocessing ----------
def test_preprocess_keeps_negations_and_lemmatises():
    out = pp.preprocess("The toilets weren't clean and the carvings are AMAZING!! https://x.com")
    assert out == "toilet not clean carving amazing"
    assert pp.lemmatize("facilities") == "facility" and pp.lemmatize("bus") == "bus" and pp.lemmatize("glass") == "glass"


def test_sentence_and_clause_splitting():
    assert pp.split_sentences("Great view! Bad roads.\nCome early.") == ["Great view!", "Bad roads.", "Come early."]
    assert pp.split_clauses("Clean temple but very crowded, parking was hard") == ["Clean temple", "very crowded", "parking was hard"]


# ---------- Sentiment ----------
def test_vader_thresholds_and_probabilities():
    assert vader_label(0.5) == "positive" and vader_label(-0.5) == "negative" and vader_label(0.0) == "neutral"
    for c in (-0.9, -0.03, 0.0, 0.4):
        p = vader_proba(c)
        assert abs(sum(p) - 1) < 1e-9
        assert ["negative", "neutral", "positive"][p.index(max(p))] == vader_label(c)


@pytest.mark.parametrize("text,label", [
    ("Absolutely beautiful temple, the sculptures are breathtaking and the staff were helpful.", "positive"),
    ("Filthy toilets, garbage everywhere and rude guards. Terrible experience.", "negative"),
])
def test_hybrid_sentiment_on_clear_reviews(text, label):
    r = analyze_sentiment(text)
    assert r["label"] == label
    assert 0 < r["confidence"] <= 1
    assert abs(sum(r["probabilities"].values()) - 1) < 0.01


# ---------- Aspects, keywords, recommendations ----------
def test_aspect_sentiment_handles_contrast():
    aspects = {a["aspect"]: a for a in extract_aspects(
        "The carvings are stunning but the toilets were filthy and the queue was terribly long. Parking was easy.")}
    assert aspects["heritage"]["sentiment"] == "positive"
    assert aspects["cleanliness"]["sentiment"] == "negative"
    assert aspects["crowd"]["sentiment"] == "negative"
    assert aspects["access"]["sentiment"] == "positive"
    assert extract_aspects("We went there yesterday.") == []


def test_keywords():
    kws = extract_keywords("The hanging bridge was beautiful. The hanging bridge was crowded.")
    assert kws[0] == "hanging bridge"
    result = contrast_keywords(["clean lawns and lovely view"] * 3, ["dirty toilets and long queue"] * 3)
    assert "dirty" not in {r["term"] for r in result["positive"]}
    assert any(r["term"] == "dirty" for r in result["negative"])


def test_recommendation_rules():
    out = build_insights({"cleanliness": {"positive": 1, "neutral": 0, "negative": 4},
                          "heritage": {"positive": 9, "neutral": 1, "negative": 0},
                          "pricing": {"positive": 0, "neutral": 0, "negative": 2}})     # too few mentions
    assert [i["aspect"] for i in out["issues"]] == ["cleanliness"]
    assert out["issues"][0]["priority"] == "high" and "sanitation" in out["issues"][0]["recommendation"]
    assert [s["aspect"] for s in out["strengths"]] == ["heritage"]


# ---------- API ----------
def test_analyze_endpoint(client):
    r = client.post("/api/analyze", json={"text": "Lovely lake view but the boating charges are too expensive."})
    assert r.status_code == 200
    body = r.json()
    assert {"sentiment", "aspects", "keywords", "highlights", "preprocessed"} <= body.keys()
    assert {a["aspect"] for a in body["aspects"]} >= {"nature", "pricing"}
    assert client.post("/api/analyze", json={"text": ""}).status_code == 422


def test_submit_review_and_validation(client):
    aid = attraction_id(client)
    ok = client.post("/api/reviews", json={"attraction_id": aid, "rating": 5, "visitor_type": "family",
                                           "visit_date": "2026-10-01", "text": "Stunning sculptures and very clean premises."})
    assert ok.status_code == 201 and ok.json()["analysis"]["sentiment"]["label"] == "positive"
    bad = [{"attraction_id": aid, "rating": 6, "text": "Nice place to visit really"},
           {"attraction_id": aid, "rating": 4, "text": "ok"},
           {"attraction_id": aid, "rating": 4, "text": "Nice place to visit", "visit_date": "2999-01-01"},
           {"attraction_id": aid, "rating": 4, "text": "Nice place to visit", "visitor_type": "alien"}]
    for body in bad:
        assert client.post("/api/reviews", json=body).status_code == 422
    assert client.post("/api/reviews", json={"attraction_id": 999, "rating": 4, "text": "Nice place to visit"}).status_code == 404


def test_list_filter_and_delete_reviews(client):
    aid = attraction_id(client, "Warangal Fort")
    for text, rating in [("Garbage everywhere and dirty toilets, very poor.", 1),
                         ("Beautiful gateways, lovely evening view.", 5)]:
        client.post("/api/reviews", json={"attraction_id": aid, "rating": rating, "text": text})
    assert client.get("/api/reviews").json()["total"] == 2
    neg = client.get("/api/reviews", params={"sentiment": "negative"}).json()
    assert neg["total"] == 1 and "Garbage" in neg["reviews"][0]["text"]
    assert client.get("/api/reviews", params={"aspect": "cleanliness"}).json()["total"] == 1
    assert client.get("/api/reviews", params={"q": "gateways"}).json()["total"] == 1
    assert client.get("/api/reviews", params={"aspect": "magic"}).status_code == 400
    rid = neg["reviews"][0]["id"]
    assert client.delete(f"/api/reviews/{rid}").status_code == 200
    assert client.delete(f"/api/reviews/{rid}").status_code == 404
    with get_db() as db:   # aspects are deleted with the review (cascade)
        assert db.execute("SELECT COUNT(*) FROM review_aspects WHERE review_id = ?", (rid,)).fetchone()[0] == 0


def test_csv_upload(client):
    csv_text = ("attraction,rating,visit_date,visitor_type,text\n"
                "Ramappa Temple,5,2026-09-10,family,Amazing sculptures and very peaceful atmosphere.\n"
                "laknavaram-lake,2,2026-09-11,friends,The bridge was overcrowded and unsafe for kids.\n"
                "Unknown Place,4,2026-09-12,family,Lovely place with good views.\n"
                "Warangal Fort,9,2026-09-12,family,Lovely place with good views.\n"
                "Warangal Fort,4,2026-09-12,family,ok\n")
    r = client.post("/api/reviews/upload", files={"file": ("r.csv", io.BytesIO(csv_text.encode()), "text/csv")})
    assert r.status_code == 201
    body = r.json()
    assert body["imported"] == 2 and body["skipped"] == 3
    assert [e["row"] for e in body["errors"]] == [4, 5, 6]
    missing = client.post("/api/reviews/upload", files={"file": ("r.csv", io.BytesIO(b"name,comment\na,b\n"), "text/csv")})
    assert missing.status_code == 400 and "attraction" in missing.json()["detail"]
    assert client.post("/api/reviews/upload", files={"file": ("r.txt", io.BytesIO(b"x"), "text/plain")}).status_code == 400


def test_dashboard_insights_and_export(client):
    aid = attraction_id(client, "Bhadrakali Temple")
    reviews = [("Very crowded, we waited four hours in the queue. Terrible.", 1),
               ("Huge rush and the queue was badly managed, exhausting wait.", 2),
               ("The queue was chaotic and overcrowded, poor experience.", 2),
               ("Beautiful lake view from the hill, lovely temple.", 5)]
    for text, rating in reviews:
        client.post("/api/reviews", json={"attraction_id": aid, "rating": rating, "visit_date": "2026-10-05", "text": text})
    d = client.get("/api/dashboard").json()
    assert d["total_reviews"] == 4
    assert d["distribution"]["negative"] >= 2
    assert sum(d["distribution"].values()) == 4
    assert d["monthly"][0]["month"] == "2026-10"
    ins = client.get(f"/api/attractions/{aid}/insights").json()
    assert ins["total_reviews"] == 4
    assert ins["issues"] and ins["issues"][0]["aspect"] == "crowd"
    assert "concerns" in ins["summary"].lower()
    assert client.get("/api/attractions/999/insights").status_code == 404
    csv_out = client.get("/api/export.csv", params={"attraction_id": aid})
    assert csv_out.status_code == 200 and csv_out.text.count("\n") == 5    # header + 4 rows


def test_model_evaluation(client):
    e = client.get("/api/model/evaluation").json()
    hybrid = e["handwritten"]["models"]["hybrid"]
    assert e["handwritten"]["size"] == 60
    assert hybrid["accuracy"] >= 0.8                     # guards against regressions in the pipeline
    assert sum(map(sum, hybrid["confusion_matrix"])) == 60


def test_sample_dataset_seeds_into_empty_db(client):
    assert repository.review_count() == 0
    assert repository.seed_sample_reviews() == 1500
    assert repository.seed_sample_reviews() == 0      # only seeds an empty database
    assert config.MODEL_PATH.exists()
