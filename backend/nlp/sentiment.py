"""Sentiment analysis: VADER (lexicon) + TF-IDF/Logistic Regression (machine learning),
combined into a hybrid prediction."""

import csv
import logging
import re

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from backend import config
from backend.nlp.preprocess import preprocess

log = logging.getLogger(__name__)

LABELS = ("negative", "neutral", "positive")
ML_WEIGHT = 0.6           # hybrid = 0.6 x ML probabilities + 0.4 x VADER probabilities
VADER_THRESHOLD = 0.05    # standard VADER cut-off for positive / negative

# Domain lexicon: tourism words that VADER's general lexicon misses or under-weights.
# Valence uses VADER's scale (-4 very negative .. +4 very positive).
TOURISM_LEXICON = {
    "filthy": -2.6, "dirty": -2.0, "smelly": -2.0, "stinks": -2.2, "garbage": -1.8, "litter": -1.6,
    "littered": -1.8, "unhygienic": -2.2, "unusable": -2.0, "neglected": -2.0, "damaged": -1.8,
    "broken": -1.8, "polluted": -2.0, "overcrowded": -2.0, "crowded": -1.2, "rush": -0.8, "pushing": -1.2,
    "chaotic": -1.8, "potholes": -1.6, "overpriced": -2.0, "unsafe": -2.2, "risky": -1.5, "rude": -2.2,
    "scribbling": -1.5, "spotless": 2.6, "serene": 2.4, "peaceful": 2.2, "knowledgeable": 1.8,
    "breathtaking": 3.0, "affordable": 1.5, "tidy": 1.6,
}
# Note: this list was built from the sample corpus vocabulary only, never from the
# hand-written evaluation set, so the evaluation scores are not inflated.
_vader = SentimentIntensityAnalyzer()
_vader.lexicon.update(TOURISM_LEXICON)
_model: Pipeline | None = None


# ---------- VADER ----------
def vader_compound(text: str) -> float:
    return _vader.polarity_scores(text)["compound"]


def vader_label(compound: float) -> str:
    if compound >= VADER_THRESHOLD:
        return "positive"
    if compound <= -VADER_THRESHOLD:
        return "negative"
    return "neutral"


def vader_proba(compound: float) -> list[float]:
    """Map the compound score (-1..1) to [negative, neutral, positive] probabilities
    that agree with vader_label."""
    if compound >= VADER_THRESHOLD:
        pos = 0.5 + compound / 2
        return [0.0, 1 - pos, pos]
    if compound <= -VADER_THRESHOLD:
        neg = 0.5 + abs(compound) / 2
        return [neg, 1 - neg, 0.0]
    return [0.0, 1.0, 0.0]


def highlight_words(text: str) -> list[dict]:
    """Words from the VADER lexicon found in the text, with their valence (for the UI)."""
    seen, out = set(), []
    for word in re.findall(r"[a-zA-Z']+", text):
        w = word.lower()
        if w in _vader.lexicon and w not in seen:
            seen.add(w)
            out.append({"word": word, "valence": round(_vader.lexicon[w], 2)})
    return out


# ---------- Machine-learning model ----------
def build_pipeline() -> Pipeline:
    return Pipeline([
        ("tfidf", TfidfVectorizer(preprocessor=preprocess, ngram_range=(1, 2), min_df=2,
                                  sublinear_tf=True, max_features=20000)),
        ("clf", LogisticRegression(max_iter=2000, class_weight="balanced", C=2.0)),
    ])


def load_dataset(path=None) -> tuple[list[str], list[str]]:
    texts, labels = [], []
    with open(path or config.DATASET_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            texts.append(row["text"])
            labels.append(row["label"])
    return texts, labels


def train_model(texts: list[str] | None = None, labels: list[str] | None = None) -> Pipeline:
    if texts is None:
        texts, labels = load_dataset()
    pipe = build_pipeline()
    pipe.fit(texts, labels)
    return pipe


def get_model() -> Pipeline:
    """Load the trained model from disk, or train and save it on first use."""
    global _model
    if _model is None:
        if config.MODEL_PATH.exists():
            try:
                _model = joblib.load(config.MODEL_PATH)
            except Exception:  # e.g. saved with another scikit-learn version
                log.warning("Could not load saved model, retraining")
        if _model is None:
            _model = train_model()
            config.DATA_DIR.mkdir(parents=True, exist_ok=True)
            joblib.dump(_model, config.MODEL_PATH)
    return _model


def reset_model() -> None:
    global _model
    _model = None


# ---------- Hybrid ----------
def analyze_many(texts: list[str]) -> list[dict]:
    """Sentiment for a batch of texts (one ML call for the whole batch)."""
    if not texts:
        return []
    model = get_model()
    classes = list(model.classes_)
    ml_probas = model.predict_proba(texts)
    results = []
    for text, proba in zip(texts, ml_probas):
        ml = [float(proba[classes.index(lbl)]) for lbl in LABELS]
        compound = vader_compound(text)
        vader = vader_proba(compound)
        hybrid = [ML_WEIGHT * m + (1 - ML_WEIGHT) * v for m, v in zip(ml, vader)]
        best = max(range(3), key=lambda i: hybrid[i])
        results.append({
            "label": LABELS[best],
            "confidence": round(hybrid[best], 3),
            "probabilities": {lbl: round(p, 3) for lbl, p in zip(LABELS, hybrid)},
            "ml_label": LABELS[max(range(3), key=lambda i: ml[i])],
            "ml_probabilities": {lbl: round(p, 3) for lbl, p in zip(LABELS, ml)},
            "vader_compound": round(compound, 3),
            "vader_label": vader_label(compound),
        })
    return results


def analyze_sentiment(text: str) -> dict:
    return analyze_many([text])[0]
