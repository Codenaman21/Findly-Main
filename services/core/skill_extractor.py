"""
Skill Extractor — Extracts skills from user input via LLM.
Includes robust JSON parsing with fallback keyword-based extraction
and a post-processing layer that merges fragmented tokens into
meaningful compound skills (e.g. "repair" + "phone" → "mobile repair").
"""

import json
import re
import logging

from services.llm.llm_client import query_llm
from services.llm.prompts import extract_skills_prompt

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
#  Skill merge rules — maps token pairs/groups
#  to their correct compound skill name.
#  Checked AFTER initial extraction (LLM or keyword).
# ──────────────────────────────────────────────

SKILL_MERGE_RULES: list[dict] = [
    # Repair-related
    {"tokens": {"repair", "phone"},    "merged": "mobile repair"},
    {"tokens": {"repair", "mobile"},   "merged": "mobile repair"},
    {"tokens": {"fix", "phone"},       "merged": "mobile repair"},
    {"tokens": {"fix", "mobile"},      "merged": "mobile repair"},
    {"tokens": {"repair", "laptop"},   "merged": "computer repair"},
    {"tokens": {"repair", "computer"}, "merged": "computer repair"},
    {"tokens": {"fix", "laptop"},      "merged": "computer repair"},
    {"tokens": {"fix", "computer"},    "merged": "computer repair"},
    {"tokens": {"repair", "ac"},       "merged": "ac repair"},
    {"tokens": {"repair", "tv"},       "merged": "electronics repair"},
    {"tokens": {"fix", "tv"},          "merged": "electronics repair"},
    {"tokens": {"repair", "electronics"}, "merged": "electronics repair"},

    # Development-related
    {"tokens": {"web", "development"}, "merged": "web development"},
    {"tokens": {"web", "design"},      "merged": "web design"},
    {"tokens": {"mobile", "development"}, "merged": "mobile development"},
    {"tokens": {"app", "development"}, "merged": "mobile development"},
    {"tokens": {"game", "development"}, "merged": "game development"},
    {"tokens": {"software", "development"}, "merged": "software development"},

    # Data-related
    {"tokens": {"data", "science"},    "merged": "data science"},
    {"tokens": {"data", "analysis"},   "merged": "data analysis"},
    {"tokens": {"data", "entry"},      "merged": "data entry"},
    {"tokens": {"machine", "learning"}, "merged": "machine learning"},
    {"tokens": {"deep", "learning"},   "merged": "deep learning"},
    {"tokens": {"artificial", "intelligence"}, "merged": "ai"},

    # Design-related
    {"tokens": {"graphic", "design"},  "merged": "graphic design"},
    {"tokens": {"ui", "design"},       "merged": "ui design"},
    {"tokens": {"ux", "design"},       "merged": "ux design"},
    {"tokens": {"video", "editing"},   "merged": "video editing"},

    # Business-related
    {"tokens": {"project", "management"}, "merged": "project management"},
    {"tokens": {"digital", "marketing"},  "merged": "digital marketing"},
    {"tokens": {"content", "writing"},    "merged": "content writing"},
    {"tokens": {"customer", "service"},   "merged": "customer service"},
    {"tokens": {"cloud", "computing"},    "merged": "cloud computing"},
    {"tokens": {"social", "media"},       "merged": "social media marketing"},
]

# Fallback keyword bank when LLM parsing fails.
# Includes compound phrases (checked longest-first in _keyword_fallback).
KEYWORD_BANK = {
    # Compound skills (multi-word — matched first)
    "mobile repair", "computer repair", "ac repair", "electronics repair",
    "data science", "data analysis", "data entry",
    "machine learning", "deep learning",
    "graphic design", "ui design", "ux design",
    "web development", "web design", "mobile development",
    "game development", "software development",
    "content writing", "copywriting", "digital marketing",
    "video editing", "project management", "customer service",
    "cloud computing", "social media marketing",

    # Single-word / short keywords
    "python", "javascript", "java", "react", "node.js", "html", "css",
    "sql", "mongodb", "flask", "django", "docker", "aws", "kubernetes",
    "ai", "figma", "photoshop",
    "writing", "marketing", "seo",
    "photography",
    "teaching", "tutoring", "nursing", "healthcare",
    "cooking", "baking", "plumbing", "electrician", "carpentry",
    "welding", "driving", "tailoring", "sewing", "farming", "gardening",
    "sales", "accounting", "finance", "bookkeeping",
    "leadership", "communication",
    "flutter", "swift", "kotlin",
    "networking", "cybersecurity",
    "devops", "rust", "go", "typescript", "angular", "vue",
}


def extract_skills(user_input: str) -> dict:
    """
    Extract skills from user input using the LLM, then post-process
    to merge fragmented tokens into compound skills.
    Falls back to keyword matching if LLM response is unparseable.

    Returns:
        {
            "skills": [...],
            "experience_level": "...",
            "location": "...",
            "raw_summary": "...",
            "source": "llm" | "fallback"
        }
    """
    try:
        prompt = extract_skills_prompt(user_input)
        raw_response = query_llm(prompt)

        # Attempt to parse LLM JSON response
        parsed = _parse_json_response(raw_response)

        if parsed and parsed.get("skills"):
            # Post-process: merge fragmented skill tokens
            parsed["skills"] = _merge_related_skills(parsed["skills"], user_input)
            parsed["source"] = "llm"
            logger.info(f"LLM extracted skills (post-merge): {parsed['skills']}")
            return parsed

    except Exception as e:
        logger.warning(f"LLM skill extraction failed: {e}")

    # Fallback: keyword-based extraction
    logger.info("Using fallback keyword extraction")
    return _keyword_fallback(user_input)


def _merge_related_skills(skills: list[str], user_input: str) -> list[str]:
    """
    Post-processing layer: detects fragmented tokens and merges them
    into semantically correct compound skills.

    E.g. ["repair", "phone"] → ["mobile repair"]
         ["data", "science", "python"] → ["data science", "python"]
    """
    if not skills:
        return skills

    # Normalize all skills to lowercase for matching
    skill_set = {s.lower().strip() for s in skills}
    input_lower = user_input.lower()
    merged_result = set()
    consumed_tokens = set()

    # Pass 1: Apply merge rules — check if token pairs are present
    for rule in SKILL_MERGE_RULES:
        rule_tokens = rule["tokens"]
        merged_name = rule["merged"]

        # Check if all tokens in the rule are present in the extracted skills
        # OR present in the original user input (catches tokenization misses)
        tokens_in_skills = rule_tokens.issubset(skill_set)
        tokens_in_input = all(t in input_lower for t in rule_tokens)

        if tokens_in_skills or tokens_in_input:
            merged_result.add(merged_name)
            consumed_tokens.update(rule_tokens)
            logger.debug(f"Merged {rule_tokens} → '{merged_name}'")

    # Pass 2: Keep any skills that weren't consumed by merge rules
    for skill in skills:
        s = skill.lower().strip()
        if s not in consumed_tokens and s not in merged_result:
            merged_result.add(s)

    result = list(merged_result)
    if not result:
        result = list(skill_set)  # Safety: never return empty

    return result


def _parse_json_response(raw: str) -> dict | None:
    """
    Attempt to parse JSON from LLM output.
    Handles cases where JSON is embedded in surrounding text.
    """
    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object in the response using regex
    json_match = re.search(r'\{[\s\S]*\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    logger.warning(f"Could not parse JSON from LLM response: {raw[:200]}")
    return None


def _keyword_fallback(user_input: str) -> dict:
    """
    Keyword matching fallback when LLM fails.
    Checks multi-word compound skills first (longest-match-first),
    then single keywords. Applies merge rules at the end.
    """
    input_lower = user_input.lower()
    found_skills = []

    # Sort keywords longest-first so compound phrases match before fragments
    sorted_keywords = sorted(KEYWORD_BANK, key=len, reverse=True)

    for keyword in sorted_keywords:
        # Short keywords (≤3 chars) need word-boundary matching to avoid
        # false positives (e.g. "ai" inside "repair", "go" inside "going")
        if len(keyword) <= 3:
            if not re.search(r'\b' + re.escape(keyword) + r'\b', input_lower):
                continue
        elif keyword not in input_lower:
            continue

        # Avoid adding a single token if it's already covered by a compound match
        is_substring_of_existing = any(
            keyword != existing and keyword in existing
            for existing in found_skills
        )
        if not is_substring_of_existing:
            found_skills.append(keyword)

    # Apply merge rules on top (catches cross-keyword combinations)
    found_skills = _merge_related_skills(found_skills, user_input)

    # If keyword bank found nothing, try merge rules directly against input.
    # This catches cases like "repair phones" where neither "repair" nor "phone"
    # are in the keyword bank, but the merge rule {"repair","phone"} → "mobile repair" applies.
    if not found_skills:
        for rule in SKILL_MERGE_RULES:
            if all(t in input_lower for t in rule["tokens"]):
                found_skills.append(rule["merged"])
        # Deduplicate
        found_skills = list(set(found_skills))

    # If still nothing found, use generic classification
    if not found_skills:
        found_skills = ["general skills"]

    return {
        "skills": found_skills,
        "experience_level": "unknown",
        "location": "not specified",
        "raw_summary": user_input[:100],
        "source": "fallback"
    }

