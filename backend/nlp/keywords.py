"""Keyword extraction for a single review and for groups of reviews."""

import math
from collections import Counter

from backend.nlp.preprocess import NEGATIONS, lemmatize, remove_stopwords, split_clauses, split_sentences, tokenize

# Words that appear in almost every review and say nothing about the experience.
GENERIC = {"place", "visit", "visited", "visiting", "warangal", "time", "day", "really", "also", "one",
           "trip", "went", "come", "came", "people", "temple", "lake", "fort", "garden", "zoo", "hanamkonda",
           "just", "like", "lot", "thing", "bit", "overall", "experience", "make", "made", "spent", "family"}


def _terms(text: str) -> list[str]:
    """Unigrams and bigrams; bigrams never cross a clause or sentence boundary."""
    terms = []
    for sentence in split_sentences(text):
        for clause in split_clauses(sentence) or [sentence]:
            tokens = [lemmatize(t) for t in remove_stopwords(tokenize(clause))]
            tokens = [t for t in tokens if t not in GENERIC]
            terms += [t for t in tokens if t not in NEGATIONS and len(t) > 2]
            terms += [f"{a} {b}" for a, b in zip(tokens, tokens[1:]) if a != b]
    return terms


def extract_keywords(text: str, top_n: int = 8) -> list[str]:
    counts = Counter()
    for term in _terms(text):
        counts[term] += 1.2 if " " in term else 1.0   # phrases are slightly more informative
    return [t for t, _ in counts.most_common(top_n)]


# Pure opinion / filler words: they show THAT people liked something, not WHAT. Topic keywords
# such as "toilet", "queue" or "hanging bridge" are more useful to tourism officials.
FILLER = {"recommend", "recommended", "highly", "definitely", "telangana", "best", "need", "improvement",
          "authority", "authorities", "care", "spend", "hour", "seriously", "worth", "average", "fine", "okay",
          "great", "good", "nice", "loved", "love", "amazing", "excellent", "terrible", "disappointing",
          "waste", "poor", "bad", "beautiful", "lovely", "happy", "sad", "wonderful", "awesome", "worst",
          "right", "offered", "ago", "kept", "amazed"}


def _is_topic(term: str) -> bool:
    return any(w not in FILLER and w not in NEGATIONS for w in term.split())


def contrast_keywords(positive_texts: list[str], negative_texts: list[str], top_n: int = 15,
                      min_count: int = 3) -> dict:
    """Topic terms that are typical of positive vs negative reviews (smoothed log-odds ratio)."""
    pos = Counter(t for text in positive_texts for t in set(_terms(text)) if _is_topic(t))
    neg = Counter(t for text in negative_texts for t in set(_terms(text)) if _is_topic(t))
    n_pos, n_neg = max(len(positive_texts), 1), max(len(negative_texts), 1)

    def ranked(a: Counter, b: Counter, na: int, nb: int) -> list[dict]:
        rows = []
        for term, count in a.items():
            if count < min_count:
                continue
            score = math.log(((count + 1) / (na + 2)) / ((b.get(term, 0) + 1) / (nb + 2)))
            if score > 0:
                rows.append({"term": term, "count": count, "score": round(score, 2)})
        rows.sort(key=lambda r: (r["score"] * math.log(1 + r["count"])), reverse=True)
        return rows[:top_n]

    return {"positive": ranked(pos, neg, n_pos, n_neg), "negative": ranked(neg, pos, n_neg, n_pos)}
