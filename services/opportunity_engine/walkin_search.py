"""
Walk-in Opportunity Engine (Real-world, location-aware)

Returns:
- Google Maps search links
- Business categories
- Strategy signals

LLM will generate human text.
"""

import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def search_walkin(skill: str, location: str = "nearby") -> dict:
    skill = skill.lower().strip()
    location = location.lower().strip()

    places = []

    # 🔥 Generate relevant categories
    categories = _map_skill_to_places(skill)

    for category in categories:
        query = f"{category} near {location}"
        encoded = quote_plus(query)

        map_link = f"https://www.google.com/maps/search/{encoded}"

        places.append({
            "type": category,
            "query": query,
            "map_link": map_link
        })

    return {
        "places": places,
        "skill": skill,
        "location": location,
        "count": len(places),
        "source": "maps"
    }


# -----------------------------
# SKILL → PLACE MAPPING
# -----------------------------
def _map_skill_to_places(skill: str) -> list:
    skill = skill.lower()

    # 🔧 Repair skills
    if "repair" in skill:
        return [
            "mobile repair shop",
            "electronics repair shop",
            "phone service center"
        ]

    # 🍔 Food
    elif "cooking" in skill or "baking" in skill:
        return [
            "restaurant",
            "cafe",
            "bakery"
        ]

    # 🎨 Design
    elif "design" in skill:
        return [
            "printing shop",
            "advertising agency",
            "design studio"
        ]

    # 💻 Tech
    elif any(k in skill for k in ["python", "web", "software", "development"]):
        return [
            "it company office",
            "startup office",
            "computer service center"
        ]

    # 🧠 Generic fallback
    return [
        "local businesses",
        "service centers",
        "shops hiring staff"
    ]