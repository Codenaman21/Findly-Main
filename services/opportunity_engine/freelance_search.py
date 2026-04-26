"""
Freelance Opportunity Engine (LLM-driven text)

Returns structured opportunities:
- platform links
- idea signals

NO human text — LLM will generate explanations.
"""

import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)


def search_freelance(skill: str) -> dict:
    skill = skill.lower().strip()
    encoded = quote_plus(skill)

    opportunities = []

    # -----------------------------
    # 🔗 PLATFORM LINKS (NO TEXT)
    # -----------------------------
    opportunities.append({
        "type": "platform",
        "platform": "fiverr",
        "link": f"https://www.fiverr.com/search/gigs?query={encoded}"
    })

    opportunities.append({
        "type": "platform",
        "platform": "peopleperhour",
        "link": f"https://www.peopleperhour.com/freelance-jobs?q={encoded}"
    })

    # -----------------------------
    # 💡 IDEA SIGNALS (NO TEXT)
    # -----------------------------
    idea_tags = _generate_idea_tags(skill)

    for tag in idea_tags:
        opportunities.append({
            "type": "idea",
            "tag": tag
        })

    return {
        "opportunities": opportunities,
        "skill": skill,
        "count": len(opportunities),
        "source": "structured"
    }


# -----------------------------
# IDEA TAG GENERATOR
# -----------------------------
def _generate_idea_tags(skill: str) -> list:
    skill = skill.lower()

    if "repair" in skill:
        return [
            "doorstep_service",
            "shop_partnership",
            "emergency_service",
            "local_listing"
        ]

    elif "design" in skill:
        return [
            "logo_design",
            "social_media_design",
            "template_selling",
            "startup_outreach"
        ]

    elif any(k in skill for k in ["python", "web", "development", "coding"]):
        return [
            "website_building",
            "bug_fixing",
            "automation_tools",
            "startup_projects"
        ]

    return [
        "local_services",
        "online_promotion",
        "direct_outreach"
    ]