"""
Helper utilities for the UNMAPPED backend.
"""

import json
import re
import logging

logger = logging.getLogger(__name__)


def safe_json_parse(text: str) -> dict | None:
    """
    Safely parse JSON from a string that might contain extra text.
    Tries direct parse first, then regex extraction.
    """
    if not text:
        return None

    # Direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from surrounding text
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    # Try to extract JSON array
    match = re.search(r'\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    return None


def truncate(text: str, max_length: int = 200) -> str:
    """Truncate text to max_length with ellipsis."""
    if len(text) <= max_length:
        return text
    return text[:max_length - 3] + "..."


def clean_skill(skill: str) -> str:
    """Normalize a skill string for matching."""
    return skill.lower().strip().replace("-", " ").replace("_", " ")
