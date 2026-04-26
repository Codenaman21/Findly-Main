"""
Learning Engine — services/core/learning_engine.py

Deterministic, LLM-free learning plan generator for the UNMAPPED
career assistant system.

Takes a user's existing skills and a target role, compares them
against the categorised role-skill matrix in
data/role_skills_cleaned.json, identifies gaps, and returns a
prioritised, stage-gated learning plan with dynamic resource links.

Priority order:
    core → frameworks → backend → database → tools → other → advanced
"""

import json
import logging
from pathlib import Path
from urllib.parse import quote_plus

# ──────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────

_FILE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _FILE_DIR.parent.parent
_ROLE_SKILLS_PATH = _PROJECT_ROOT / "data" / "role_skills_cleaned.json"

# Singleton cache — loaded once, reused forever
_role_skills_cache: dict | None = None

# Learning stages in priority order
STAGE_ORDER = [
    "core",
    "frameworks",
    "backend",
    "database",
    "tools",
    "other",
    "advanced",
]

# Human-friendly stage labels
STAGE_LABELS = {
    "core":       "foundation",
    "frameworks": "frameworks",
    "backend":    "backend",
    "database":   "database",
    "tools":      "tools",
    "other":      "supplementary",
    "advanced":   "advanced",
}

# Max skills to recommend per stage
STAGE_LIMITS = {
    "core":       3,
    "frameworks": 2,
    "backend":    2,
    "database":   2,
    "tools":      2,
    "other":      2,
    "advanced":   2,
}

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
#  1. Data Loading
# ──────────────────────────────────────────────

def load_role_skills() -> dict:
    """
    Load and cache the role-skills matrix from
    data/role_skills_cleaned.json.

    Returns the full dict: { role_name: { category: [skills] } }
    Raises FileNotFoundError if the JSON is missing.
    """
    global _role_skills_cache

    if _role_skills_cache is not None:
        return _role_skills_cache

    if not _ROLE_SKILLS_PATH.exists():
        raise FileNotFoundError(
            f"Role skills file not found: {_ROLE_SKILLS_PATH}"
        )

    with open(_ROLE_SKILLS_PATH, "r", encoding="utf-8") as f:
        _role_skills_cache = json.load(f)

    logger.info(
        "Loaded role_skills_cleaned.json: %d roles",
        len(_role_skills_cache),
    )
    return _role_skills_cache


# ──────────────────────────────────────────────
#  2. Skill Normalization
# ──────────────────────────────────────────────

def normalize_skills(skills: list[str]) -> list[str]:
    """
    Normalize a list of skill strings:
      - lowercase
      - strip whitespace
      - remove empty / duplicate entries
    """
    seen: set[str] = set()
    normalized: list[str] = []

    for s in skills:
        clean = s.lower().strip()
        if clean and clean not in seen:
            seen.add(clean)
            normalized.append(clean)

    return normalized


# ──────────────────────────────────────────────
#  3. Gap Analysis
# ──────────────────────────────────────────────

def get_missing_skills(
    user_skills: list[str],
    role_data: dict,
) -> dict[str, list[str]]:
    """
    Compare the user's skills against every category of a role.

    Args:
        user_skills: normalized list of user's current skills.
        role_data:    dict { category: [skills] } for the target role.

    Returns:
        dict { category: [missing_skills] }  — only non-empty cats.
    """
    user_set = set(user_skills)
    missing: dict[str, list[str]] = {}

    for category in STAGE_ORDER:
        role_skills_in_cat = role_data.get(category, [])
        if not role_skills_in_cat:
            continue

        # Normalize the role skills for comparison
        gaps = [
            s for s in role_skills_in_cat
            if s.lower().strip() not in user_set
        ]

        if gaps:
            missing[category] = gaps

    return missing


# ──────────────────────────────────────────────
#  4. Learning Prioritization
# ──────────────────────────────────────────────

def prioritize_learning(
    missing_skills: dict[str, list[str]],
) -> dict:
    """
    Apply stage-gating to decide what the user should learn next.

    Rules (evaluated in priority order):
      1. If core skills are missing   → return ONLY core (max 3)
      2. Else if frameworks missing   → frameworks (max 2)
      3. Else backend                 → max 2
      4. Else database                → max 2
      5. Else tools                   → max 2
      6. Else other                   → max 2
      7. Else advanced                → max 2
      8. Nothing missing              → user is job-ready

    Returns:
        {
            "stage": "foundation" | "frameworks" | ... | "ready",
            "skills": ["skill1", ...]
        }
    """
    for category in STAGE_ORDER:
        gaps = missing_skills.get(category, [])
        if gaps:
            limit = STAGE_LIMITS.get(category, 2)
            return {
                "stage": STAGE_LABELS[category],
                "skills": gaps[:limit],
            }

    # No missing skills at all
    return {"stage": "ready", "skills": []}


# ──────────────────────────────────────────────
#  5. Resource Generation
# ──────────────────────────────────────────────

def fetch_resources(skill: str) -> dict[str, str]:
    """
    Generate dynamic learning resource URLs for a given skill.
    No hardcoded links — fully deterministic URL construction.

    Returns:
        {
            "youtube":     "https://www.youtube.com/results?search_query=learn+...",
            "google":      "https://www.google.com/search?q=learn+...",
            "freeCodeCamp": "https://www.google.com/search?q=site:freecodecamp.org+...",
            "w3schools":   "https://www.google.com/search?q=site:w3schools.com+...",
        }
    """
    encoded = quote_plus(f"learn {skill}")
    encoded_raw = quote_plus(skill)

    return {
        "youtube": f"https://www.youtube.com/results?search_query={encoded}",
        "google": f"https://www.google.com/search?q={encoded}",
        "freeCodeCamp": (
            f"https://www.google.com/search?q=site%3Afreecodecamp.org+{encoded_raw}"
        ),
        "w3schools": (
            f"https://www.google.com/search?q=site%3Aw3schools.com+{encoded_raw}"
        ),
    }


# ──────────────────────────────────────────────
#  6. Main Entry Point
# ──────────────────────────────────────────────

def generate_learning(
    user_skills: list[str],
    role: str,
) -> dict:
    """
    Full learning-plan pipeline.

    Args:
        user_skills: list of skill strings the user already knows.
        role:        target role name (must match a key in the JSON).

    Returns:
        On success:
        {
            "role": "Web Developer",
            "stage": "foundation",
            "focus_skills": ["javascript"],
            "resources": {
                "javascript": { "youtube": "...", "google": "..." }
            },
            "progress": {
                "total_required": 28,
                "user_has": 12,
                "percent_complete": 42
            }
        }

        If user is job-ready:
        {
            "role": "Web Developer",
            "stage": "ready",
            "message": "You are job-ready. Start applying ..."
        }

        On unknown role:
        {
            "error": "unknown_role",
            "message": "Role 'XYZ' not found.",
            "available_roles": [...]
        }
    """
    # ── Load role skills ──
    all_roles = load_role_skills()

    # ── Validate role ──
    role_data = _find_role(role, all_roles)

    if role_data is None:
        return {
            "error": "unknown_role",
            "message": f"Role '{role}' not found in our database.",
            "available_roles": sorted(all_roles.keys()),
        }

    matched_role_name = _find_role_name(role, all_roles)

    # ── Normalize user skills ──
    normalized_user = normalize_skills(user_skills or [])

    # ── Gap analysis ──
    missing = get_missing_skills(normalized_user, role_data)

    # ── Prioritize ──
    priority = prioritize_learning(missing)

    # ── Calculate progress ──
    total_required = sum(
        len(v) for v in role_data.values() if isinstance(v, list)
    )
    total_missing = sum(len(v) for v in missing.values())
    user_has = total_required - total_missing
    percent = round((user_has / total_required) * 100) if total_required else 100

    # ── Job-ready? ──
    if priority["stage"] == "ready":
        return {
            "role": matched_role_name,
            "stage": "ready",
            "message": (
                "You are job-ready. "
                "Start applying for jobs and building projects."
            ),
            "progress": {
                "total_required": total_required,
                "user_has": user_has,
                "percent_complete": 100,
            },
        }

    # ── Build resources for focus skills ──
    resources = {}
    for skill in priority["skills"]:
        resources[skill] = fetch_resources(skill)

    return {
        "role": matched_role_name,
        "stage": priority["stage"],
        "focus_skills": priority["skills"],
        "resources": resources,
        "progress": {
            "total_required": total_required,
            "user_has": user_has,
            "percent_complete": percent,
        },
    }


# ──────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────

def _find_role(role: str, all_roles: dict) -> dict | None:
    """
    Case-insensitive role lookup.
    Returns the role data dict or None.
    """
    # Exact match first
    if role in all_roles:
        return all_roles[role]

    # Case-insensitive fallback
    role_lower = role.lower().strip()
    for name, data in all_roles.items():
        if name.lower() == role_lower:
            return data

    return None


def _find_role_name(role: str, all_roles: dict) -> str:
    """
    Return the canonical role name (preserving original casing).
    """
    if role in all_roles:
        return role

    role_lower = role.lower().strip()
    for name in all_roles:
        if name.lower() == role_lower:
            return name

    return role


def get_available_roles() -> list[str]:
    """Return a sorted list of all supported role names."""
    return sorted(load_role_skills().keys())
