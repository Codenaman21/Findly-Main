"""
Intent Detector — Classifies user intent using LLM with keyword fallback.
Always returns one of: opportunity, learning, risk, startup, unknown.
"""

import json
import re
import logging

from services.llm.llm_client import query_llm
from services.llm.prompts import intent_prompt

logger = logging.getLogger(__name__)

# Valid intent categories
VALID_INTENTS = {"opportunity", "learning", "risk", "startup", "unknown"}

# Keyword-based fallback rules (deterministic)
INTENT_KEYWORDS = {
    "opportunity": [
        "job", "work", "hire", "career", "employ", "gig", "freelance",
        "earn", "income", "salary", "opportunity", "opening", "vacancy",
        "position", "role", "apply", "resume"
    ],
    "learning": [
        "learn", "course", "study", "skill", "training", "tutorial",
        "certificate", "education", "upskill", "improve", "practice",
        "class", "workshop", "bootcamp"
    ],
    "risk": [
        "risk", "danger", "challenge", "problem", "difficult", "threat",
        "market crash", "recession", "downturn", "competition", "failure"
    ],
    "startup": [
        "start business", "startup", "entrepreneur", "self-employed",
        "own business", "founder", "launch", "venture", "bootstrap",
        "side hustle", "business idea", "business plan"
    ],
}


def detect_intent(user_input: str) -> dict:
    """
    Detect the user's intent from their message.

    Returns:
        {
            "intent": "opportunity" | "learning" | "risk" | "startup" | "unknown",
            "confidence": float,
            "source": "llm" | "fallback"
        }
    """
    # Try LLM-based detection first
    try:
        prompt = intent_prompt(user_input)
        raw_response = query_llm(prompt)
        parsed = _parse_intent_response(raw_response)

        if parsed and parsed.get("intent") in VALID_INTENTS:
            parsed["source"] = "llm"
            logger.info(f"LLM detected intent: {parsed['intent']}")
            return parsed

    except Exception as e:
        logger.warning(f"LLM intent detection failed: {e}")

    # Fallback: deterministic keyword matching
    logger.info("Using fallback keyword intent detection")
    return _keyword_intent_fallback(user_input)


def _parse_intent_response(raw: str) -> dict | None:
    """Parse JSON from LLM intent response."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    json_match = re.search(r'\{[\s\S]*?\}', raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return None


def _keyword_intent_fallback(user_input: str) -> dict:
    """
    Deterministic keyword scoring for intent classification.
    Scores each category by counting matching keywords.
    """
    input_lower = user_input.lower()
    scores = {}

    for intent, keywords in INTENT_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in input_lower)
        if score > 0:
            scores[intent] = score

    if not scores:
        return {"intent": "opportunity", "confidence": 0.5, "source": "fallback"}

    # Pick intent with highest keyword match count
    best_intent = max(scores, key=scores.get)
    total_keywords = sum(scores.values())
    confidence = round(scores[best_intent] / max(total_keywords, 1), 2)

    return {
        "intent": best_intent,
        "confidence": confidence,
        "source": "fallback"
    }
