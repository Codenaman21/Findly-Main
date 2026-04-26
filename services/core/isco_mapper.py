"""
ISCO Mapper â€” Maps extracted skills to International Standard
Classification of Occupations (ISCO) codes.

Primary source: CSV-based ISCO-08 dataset (619 occupations) via isco_loader.
Fallback: Legacy JSON mapping file for guaranteed coverage.

Matching tiers (in priority order):
  1. Exact keyword match  â€” skill found in occupation title
  2. Partial match        â€” skill found in occupation description
  3. Fuzzy match          â€” rapidfuzz similarity (optional, if installed)
  4. JSON fallback        â€” original curated mapping file
"""

import json
import os
import logging

from services.core.isco_loader import (
    load_isco_csv,
    get_title_index,
    get_description_index,
)

logger = logging.getLogger(__name__)

# Path to the legacy JSON mapping (fallback)
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
ISCO_JSON_FILE = os.path.join(DATA_DIR, "isco_mapping.json")

# Cache for legacy JSON mapping
_json_cache: dict | None = None

# Fuzzy match threshold (0-100). Only accept matches above this score.
FUZZY_THRESHOLD = 70


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  Legacy JSON fallback loader (unchanged logic)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _load_json_mapping() -> dict:
    """Load legacy ISCO mapping from JSON file, with caching."""
    global _json_cache

    if _json_cache is not None:
        return _json_cache

    try:
        with open(ISCO_JSON_FILE, "r", encoding="utf-8") as f:
            _json_cache = json.load(f)
            logger.info(f"Loaded {len(_json_cache)} legacy ISCO mappings from JSON")
            return _json_cache
    except FileNotFoundError:
        logger.error(f"Legacy ISCO JSON not found: {ISCO_JSON_FILE}")
        return {}
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in legacy ISCO file: {e}")
        return {}


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  CSV-based matching tiers
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _match_exact_title(skill_lower: str, csv_data: list[dict]) -> dict | None:
    """
    Tier 1 â€” Exact keyword match: check if the skill appears
    as a word/phrase within any occupation title.
    Uses the pre-built title index for fast lookup.
    """
    title_idx = get_title_index()

    # Split multi-word skills and find entries matching ALL words
    words = [w.strip(".,;:()-/") for w in skill_lower.split() if len(w) >= 3]
    if not words:
        return None

    # Get candidate indices from the first word, then intersect
    candidates = set(title_idx.get(words[0], []))
    for word in words[1:]:
        candidates &= set(title_idx.get(word, []))

    if not candidates:
        # Also try the full skill phrase directly against titles
        for i, record in enumerate(csv_data):
            if skill_lower in record["title"]:
                # Prefer Level 4 (most specific) entries
                return record
        return None

    # Among candidates, prefer Level 4 (most specific)
    best = None
    for idx in candidates:
        record = csv_data[idx]
        if best is None or record["level"] > best["level"]:
            best = record

    return best


def _match_partial_description(skill_lower: str, csv_data: list[dict]) -> dict | None:
    """
    Tier 2 â€” Partial match: check if the skill appears anywhere
    in the occupation description (definition + tasks + included).
    Uses index for initial filtering, then verifies with substring check.
    """
    desc_idx = get_description_index()

    words = [w.strip(".,;:()-/") for w in skill_lower.split() if len(w) >= 3]
    if not words:
        return None

    # Gather candidates from description index
    candidates = set()
    for word in words:
        candidates.update(desc_idx.get(word, []))

    if not candidates:
        return None

    # Verify: full skill phrase must appear in the description
    best = None
    for idx in candidates:
        record = csv_data[idx]
        if skill_lower in record["description"]:
            # Prefer Level 4 (most specific) entries
            if best is None or record["level"] > best["level"]:
                best = record

    return best


def _match_fuzzy(skill_lower: str, csv_data: list[dict]) -> tuple[dict | None, int]:
    """
    Tier 3 â€” Fuzzy match using rapidfuzz (optional dependency).
    Only runs if rapidfuzz is installed. Matches against titles only
    to keep it fast.

    Returns:
        (best_record, score) or (None, 0) if unavailable/no match.
    """
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return None, 0

    # Build a list of (title, index) for Level 4 entries only (fastest + most specific)
    choices = {}
    for i, record in enumerate(csv_data):
        if record["level"] == 4:
            choices[i] = record["title"]

    if not choices:
        return None, 0

    # Use extractOne for the fastest single-best match
    result = process.extractOne(
        skill_lower,
        choices,
        scorer=fuzz.token_set_ratio,
        score_cutoff=FUZZY_THRESHOLD,
    )

    if result:
        match_title, score, idx = result
        return csv_data[idx], int(score)

    return None, 0


def _match_json_fallback(skill_lower: str) -> dict | None:
    """
    Tier 4 â€” Fallback to the original curated JSON mapping.
    Exact key match first, then best substring match (longest key wins).
    """
    mapping = _load_json_mapping()
    if not mapping:
        return None

    # Direct key match (highest priority)
    if skill_lower in mapping:
        return mapping[skill_lower]

    # Substring match â€” collect ALL matches, pick the most specific (longest key)
    candidates = []
    for key, entry in mapping.items():
        if key in skill_lower or skill_lower in key:
            candidates.append((key, entry))

    if candidates:
        # Prefer the longest matching key (most specific)
        best_key, best_entry = max(candidates, key=lambda x: len(x[0]))
        return best_entry

    return None


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  Main public API (signature preserved)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def map_skills_to_isco(skills: list[str]) -> list[dict]:
    """
    Map a list of skill strings to their ISCO occupation codes.

    Uses a 4-tier matching strategy:
      1. Exact keyword in CSV title
      2. Partial match in CSV description
      3. Fuzzy match via rapidfuzz (optional)
      4. Legacy JSON mapping fallback

    Args:
        skills: List of skill strings (e.g., ["python", "data science"])

    Returns:
        List of dicts with: skill, isco_code, title, confidence, explanation.
    """
    # Ensure CSV is loaded (cached after first call)
    csv_data = load_isco_csv()
    use_csv = len(csv_data) > 0

    results = []

    for skill in skills:
        skill_lower = skill.lower().strip()

        try:
            result = _map_single_skill(skill, skill_lower, csv_data, use_csv)
        except Exception as e:
            logger.error(f"Error mapping skill '{skill}': {e}")
            result = _generic_result(skill)

        results.append(result)

    mapped_count = sum(1 for r in results if r.get("confidence") != "low")
    logger.info(f"Mapped {len(results)} skills, {mapped_count} matched (CSV available: {use_csv})")
    return results


def _map_single_skill(skill: str, skill_lower: str, csv_data: list[dict], use_csv: bool) -> dict:
    """Run all matching tiers for a single skill."""

    # â”€â”€ Tier 1: Exact title match (CSV) â”€â”€
    if use_csv:
        match = _match_exact_title(skill_lower, csv_data)
        if match:
            return {
                "skill": skill,
                "isco_code": match["code"],
                "title": match["title_original"],
                "confidence": "high",
                "explanation": f"'{skill}' directly matches the ISCO occupation '{match['title_original']}'.",
                "mapped": True,
            }

    # â”€â”€ Tier 2: Partial description match (CSV) â”€â”€
    if use_csv:
        match = _match_partial_description(skill_lower, csv_data)
        if match:
            return {
                "skill": skill,
                "isco_code": match["code"],
                "title": match["title_original"],
                "confidence": "medium",
                "explanation": f"'{skill}' is referenced in the description of '{match['title_original']}'.",
                "mapped": True,
            }

    # â”€â”€ Tier 3: Fuzzy match (CSV, optional) â”€â”€
    if use_csv:
        match, score = _match_fuzzy(skill_lower, csv_data)
        if match:
            return {
                "skill": skill,
                "isco_code": match["code"],
                "title": match["title_original"],
                "confidence": "medium",
                "explanation": f"'{skill}' is similar to '{match['title_original']}' (fuzzy score: {score}%).",
                "mapped": True,
            }

    # â”€â”€ Tier 4: Legacy JSON fallback â”€â”€
    json_match = _match_json_fallback(skill_lower)
    if json_match:
        return {
            "skill": skill,
            "isco_code": json_match["code"],
            "title": json_match["title"],
            "confidence": "high",
            "explanation": f"'{skill}' matched via curated skill mapping to '{json_match['title']}'.",
            "mapped": True,
        }

    # â”€â”€ No match anywhere â”€â”€
    return _generic_result(skill)


def _generic_result(skill: str) -> dict:
    """Return a generic fallback entry for completely unmapped skills."""
    return {
        "skill": skill,
        "isco_code": "9999",
        "title": "Workers Not Elsewhere Classified",
        "confidence": "low",
        "explanation": f"No specific ISCO match found for '{skill}'. Assigned generic category.",
        "mapped": False,
    }
