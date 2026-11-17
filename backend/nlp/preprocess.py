"""Text preprocessing: cleaning, tokenisation, stop-word removal, light lemmatisation,
sentence and clause splitting."""

import re

from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

# Negation words carry sentiment ("not clean"), so they are NOT removed as stop words.
NEGATIONS = {"no", "not", "nor", "never", "none", "nothing", "nobody", "nowhere", "cannot",
             "without", "hardly", "barely"}
STOP_WORDS = frozenset((ENGLISH_STOP_WORDS | {"im", "ive", "us", "got", "get", "went", "go"}) - NEGATIONS)

_CONTRACTIONS = [
    (r"won't", "will not"), (r"can't", "cannot"), (r"n't\b", " not"), (r"'re\b", " are"),
    (r"'ll\b", " will"), (r"'ve\b", " have"), (r"'m\b", " am"), (r"'d\b", " would"), (r"'s\b", ""),
]
_URL = re.compile(r"https?://\S+|www\.\S+")
_TOKEN = re.compile(r"[a-z]+")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_CLAUSE_SPLIT = re.compile(r"\b(?:but|however|although|though|whereas|except|yet|and|while)\b|[,;:]", re.IGNORECASE)


def clean_text(text: str) -> str:
    """Lower-case, remove URLs, expand contractions, keep letters only, collapse spaces."""
    text = text.lower().replace("’", "'").replace("`", "'")
    text = _URL.sub(" ", text)
    for pattern, repl in _CONTRACTIONS:
        text = re.sub(pattern, repl, text)
    text = re.sub(r"[^a-z\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(clean_text(text)) if len(t) > 1 or t in NEGATIONS]


def lemmatize(token: str) -> str:
    """Light rule-based lemmatiser for plurals (toilets -> toilet, facilities -> facility)."""
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 4 and token.endswith(("ches", "shes", "sses", "xes")):
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is", "ous")):
        return token[:-1]
    return token


def remove_stopwords(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in STOP_WORDS]


def preprocess(text: str) -> str:
    """Full pipeline used by the machine-learning model: clean -> tokenise -> stop words -> lemmatise."""
    return " ".join(lemmatize(t) for t in remove_stopwords(tokenize(text)))


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_SPLIT.split(text.strip()) if s and s.strip()]


def split_clauses(sentence: str) -> list[str]:
    """Split a sentence on contrast words and punctuation so each part has one opinion:
    'clean but very crowded' -> ['clean', 'very crowded']."""
    return [c.strip() for c in _CLAUSE_SPLIT.split(sentence) if c and len(c.strip()) > 2]
