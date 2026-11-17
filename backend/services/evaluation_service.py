"""Model evaluation: compare VADER, the ML model and the hybrid on two test sets.

1. Held-out split of the sample corpus (20%, model retrained on the other 80%).
   This corpus is synthetic, so scores here are optimistic.
2. The hand-written evaluation set (datasets/eval_reviews.csv), written independently of
   the corpus generator. This is the more honest estimate of real-world performance.
"""

import csv
from functools import lru_cache

from sklearn.metrics import accuracy_score, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import train_test_split

from backend import config
from backend.nlp.sentiment import (LABELS, ML_WEIGHT, get_model, load_dataset, train_model, vader_compound,
                                   vader_label, vader_proba)


def _predict(model, texts: list[str]) -> dict[str, list[str]]:
    classes = list(model.classes_)
    preds = {"vader": [], "ml": [], "hybrid": []}
    for text, proba in zip(texts, model.predict_proba(texts)):
        ml = [float(proba[classes.index(lbl)]) for lbl in LABELS]
        c = vader_compound(text)
        v = vader_proba(c)
        hybrid = [ML_WEIGHT * m + (1 - ML_WEIGHT) * x for m, x in zip(ml, v)]
        preds["vader"].append(vader_label(c))
        preds["ml"].append(LABELS[max(range(3), key=lambda i: ml[i])])
        preds["hybrid"].append(LABELS[max(range(3), key=lambda i: hybrid[i])])
    return preds


def _metrics(y_true: list[str], y_pred: list[str]) -> dict:
    p, r, f, _ = precision_recall_fscore_support(y_true, y_pred, labels=list(LABELS), average="macro", zero_division=0)
    per_class = precision_recall_fscore_support(y_true, y_pred, labels=list(LABELS), zero_division=0)
    return {
        "accuracy": round(accuracy_score(y_true, y_pred), 3),
        "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
        "per_class": {lbl: {"precision": round(per_class[0][i], 3), "recall": round(per_class[1][i], 3),
                            "f1": round(per_class[2][i], 3), "support": int(per_class[3][i])}
                      for i, lbl in enumerate(LABELS)},
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=list(LABELS)).tolist(),
    }


def _load_eval() -> tuple[list[str], list[str]]:
    with open(config.EVAL_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [r["text"] for r in rows], [r["label"] for r in rows]


@lru_cache(maxsize=1)
def evaluate() -> dict:
    texts, labels = load_dataset()
    x_train, x_test, y_train, y_test = train_test_split(texts, labels, test_size=0.2, random_state=42,
                                                        stratify=labels)
    split_model = train_model(x_train, y_train)
    split_preds = _predict(split_model, x_test)

    eval_texts, eval_labels = _load_eval()
    eval_preds = _predict(get_model(), eval_texts)      # production model (trained on the full corpus)

    return {
        "labels": list(LABELS),
        "corpus": {"name": "Held-out 20% of the sample corpus", "size": len(x_test), "train_size": len(x_train),
                   "note": "Synthetic corpus: scores are optimistic.",
                   "models": {k: _metrics(y_test, v) for k, v in split_preds.items()}},
        "handwritten": {"name": "Hand-written evaluation set", "size": len(eval_texts),
                        "note": "Written independently of the corpus generator: a fairer estimate.",
                        "models": {k: _metrics(eval_labels, v) for k, v in eval_preds.items()}},
        "weights": {"ml": ML_WEIGHT, "vader": round(1 - ML_WEIGHT, 2)},
    }
