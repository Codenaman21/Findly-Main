"""
ISCO CSV Loader — Loads ISCO-08 occupation data from CSV into a
cached in-memory structure. Loaded ONCE at first access, then
served from the global cache for all subsequent requests.
"""

import os
import logging

logger = logging.getLogger(__name__)

# Path to the ISCO CSV data file
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
CSV_PATH = os.path.join(DATA_DIR, "isco_data.csv")

# ── Global cache (populated once, reused forever) ──
_csv_cache: list[dict] | None = None

# Pre-built lookup indexes for fast matching (built once alongside cache)
_title_index: dict[str, list[int]] = {}       # word → list of cache indices
_description_index: dict[str, list[int]] = {}  # word → list of cache indices


def load_isco_csv() -> list[dict]:
    """
    Load and return ISCO occupation data from the CSV file.
    Uses a module-level cache — the CSV is read only on the first call.

    Returns:
        List of dicts, each with keys: code, title, description, level.
        Returns empty list if CSV loading fails entirely.
    """
    global _csv_cache

    if _csv_cache is not None:
        return _csv_cache

    try:
        import pandas as pd

        logger.info(f"Loading ISCO CSV from {CSV_PATH}")
        df = pd.read_csv(CSV_PATH)

        # Validate required columns exist
        required = {"ISCO 08 Code", "Title EN", "Definition"}
        if not required.issubset(set(df.columns)):
            missing = required - set(df.columns)
            logger.error(f"ISCO CSV missing columns: {missing}")
            _csv_cache = []
            return _csv_cache

        # Clean and transform
        records = []
        for _, row in df.iterrows():
            code = str(row["ISCO 08 Code"]).strip()
            title = str(row.get("Title EN", "")).strip()
            definition = str(row.get("Definition", "")).strip()
            tasks = str(row.get("Tasks include", "")).strip()
            included = str(row.get("Included occupations", "")).strip()
            level = int(row.get("Level", 0))

            # Skip rows with empty essential fields
            if not code or not title or title == "nan":
                continue

            # Build a combined searchable description from all text columns
            desc_parts = [definition]
            if tasks and tasks != "nan":
                desc_parts.append(tasks)
            if included and included != "nan":
                desc_parts.append(included)

            description = " ".join(desc_parts)

            records.append({
                "code": code,
                "title": title.lower(),
                "title_original": title,
                "description": description.lower(),
                "level": level,
            })

        _csv_cache = records
        logger.info(f"Loaded {len(_csv_cache)} ISCO occupation records from CSV")

        # Build lookup indexes for fast searching
        _build_indexes()

        return _csv_cache

    except ImportError:
        logger.error("pandas is not installed. Cannot load ISCO CSV.")
        _csv_cache = []
        return _csv_cache

    except FileNotFoundError:
        logger.error(f"ISCO CSV file not found: {CSV_PATH}")
        _csv_cache = []
        return _csv_cache

    except Exception as e:
        logger.error(f"Failed to load ISCO CSV: {e}")
        _csv_cache = []
        return _csv_cache


def _build_indexes():
    """
    Build inverted keyword indexes over titles and descriptions
    for O(1) lookup per keyword instead of scanning all 619 rows.
    Called once after CSV load.
    """
    global _title_index, _description_index

    if not _csv_cache:
        return

    # Minimum word length to index (skip noise like "a", "of", "and")
    MIN_WORD_LEN = 3
    STOP_WORDS = {
        "the", "and", "for", "are", "with", "that", "this", "from",
        "not", "but", "they", "their", "have", "has", "been", "were",
        "who", "which", "such", "other", "than", "also", "may",
        "include", "including", "related", "elsewhere", "classified",
    }

    _title_index.clear()
    _description_index.clear()

    for idx, record in enumerate(_csv_cache):
        # Index title words
        for word in record["title"].split():
            word = word.strip(".,;:()-/")
            if len(word) >= MIN_WORD_LEN and word not in STOP_WORDS:
                _title_index.setdefault(word, []).append(idx)

        # Index description words (sample — every 3rd word to keep index lean)
        words = record["description"].split()
        for i, word in enumerate(words):
            if i % 3 != 0:
                continue
            word = word.strip(".,;:()-/")
            if len(word) >= MIN_WORD_LEN and word not in STOP_WORDS:
                _description_index.setdefault(word, []).append(idx)

    logger.info(f"Built indexes: {len(_title_index)} title keywords, "
                f"{len(_description_index)} description keywords")


def get_title_index() -> dict[str, list[int]]:
    """Return the pre-built title word index."""
    if _csv_cache is None:
        load_isco_csv()
    return _title_index


def get_description_index() -> dict[str, list[int]]:
    """Return the pre-built description word index."""
    if _csv_cache is None:
        load_isco_csv()
    return _description_index
