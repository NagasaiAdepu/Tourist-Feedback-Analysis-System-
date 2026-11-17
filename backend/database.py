"""SQLite database: connection helper and schema."""

import sqlite3
from contextlib import contextmanager

from backend import config
from backend.attractions import ATTRACTIONS

SCHEMA = """
CREATE TABLE IF NOT EXISTS attractions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL UNIQUE,
    category    TEXT NOT NULL,
    location    TEXT NOT NULL,
    description TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reviews (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    attraction_id  INTEGER NOT NULL REFERENCES attractions(id) ON DELETE CASCADE,
    reviewer_name  TEXT,
    visitor_type   TEXT,
    rating         INTEGER CHECK (rating BETWEEN 1 AND 5),
    visit_date     TEXT,                 -- YYYY-MM-DD
    text           TEXT NOT NULL,
    source         TEXT NOT NULL,        -- form | csv | sample
    sentiment      TEXT NOT NULL,        -- positive | neutral | negative (hybrid model)
    confidence     REAL NOT NULL,
    vader_compound REAL NOT NULL,
    vader_label    TEXT NOT NULL,
    ml_label       TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS review_aspects (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    review_id INTEGER NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    aspect    TEXT NOT NULL,
    sentiment TEXT NOT NULL,
    score     REAL NOT NULL,
    snippet   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reviews_attraction ON reviews(attraction_id, visit_date);
CREATE INDEX IF NOT EXISTS idx_reviews_sentiment ON reviews(sentiment);
CREATE INDEX IF NOT EXISTS idx_aspects_review ON review_aspects(review_id);
"""


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Open a connection, commit on success, roll back on error, always close."""
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_db() as conn:
        conn.executescript(SCHEMA)
        conn.executemany(
            """INSERT OR IGNORE INTO attractions (slug, name, category, location, description)
               VALUES (:slug, :name, :category, :location, :description)""", ATTRACTIONS)
