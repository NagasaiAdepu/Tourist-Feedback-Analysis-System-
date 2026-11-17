"""App settings, read from environment variables."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# Runtime data (SQLite database + trained model). Tests point this at a temporary folder.
DATA_DIR = Path(os.getenv("NLP_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "reviews.db"
MODEL_PATH = DATA_DIR / "sentiment_model.joblib"

# Datasets shipped with the project.
DATASET_PATH = BASE_DIR / "datasets" / "warangal_reviews.csv"   # training + sample reviews
EVAL_PATH = BASE_DIR / "datasets" / "eval_reviews.csv"          # hand-written evaluation set

# Load the sample reviews into an empty database on first start (set to 0 for an empty system).
SEED_SAMPLE = os.getenv("NLP_SEED_SAMPLE", "1") == "1"

MAX_UPLOAD_MB = 5
MAX_CSV_ROWS = 5000
