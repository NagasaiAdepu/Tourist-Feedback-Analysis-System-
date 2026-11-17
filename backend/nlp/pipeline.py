"""One entry point that runs the full NLP analysis for one or many reviews."""

from backend.nlp.aspects import extract_aspects
from backend.nlp.keywords import extract_keywords
from backend.nlp.preprocess import preprocess, split_sentences
from backend.nlp.sentiment import analyze_many, highlight_words


def analyze_reviews(texts: list[str], detail: bool = False) -> list[dict]:
    """Sentiment + aspects (+ keywords, highlighted words and preprocessing steps if detail=True)."""
    results = []
    for text, sentiment in zip(texts, analyze_many(texts)):
        item = {"sentiment": sentiment, "aspects": extract_aspects(text)}
        if detail:
            item.update({
                "keywords": extract_keywords(text),
                "highlights": highlight_words(text),
                "sentences": len(split_sentences(text)),
                "words": len(text.split()),
                "preprocessed": preprocess(text),
            })
        results.append(item)
    return results


def analyze_review(text: str) -> dict:
    return analyze_reviews([text], detail=True)[0]
