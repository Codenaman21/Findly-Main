"""
Opportunity Aggregator — Orchestrates the tiered opportunity search.

Strategy:
  Tier 1: Job search (Indeed scraping) → if found, return
  Tier 2: Freelance suggestions → if found, return
  Tier 3: Walk-in opportunities → always available as fallback

All tiers run and contribute to the final result, but the primary
recommendation follows the tier priority.
"""

import logging

from services.opportunity_engine.job_search import search_jobs
from services.opportunity_engine.freelance_search import search_freelance
from services.opportunity_engine.walkin_search import search_walkin

logger = logging.getLogger(__name__)


def find_opportunities(skills: list[str], location: str = "Remote") -> dict:
    """
    Aggregate opportunities across all three tiers for the given skills.

    Args:
        skills: List of extracted skill strings.
        location: Target location for job search.

    Returns:
        {
            "primary_tier": "jobs" | "freelance" | "walkin",
            "jobs": {...},
            "freelance": {...},
            "walkin": {...},
            "skills_searched": [...],
            "location": str,
            "summary": str
        }
    """
    if not skills:
        skills = ["general"]

    # Use the first (primary) skill for focused search
    primary_skill = skills[0]
    logger.info(f"Aggregating opportunities for skills={skills}, location={location}")

    # --- Tier 1: Job Search ---
    job_results = _safe_search(
        lambda: search_jobs(primary_skill, location),
        "job_search"
    )

    # --- Tier 2: Freelance Suggestions ---
    freelance_results = _safe_search(
        lambda: search_freelance(primary_skill),
        "freelance_search"
    )

    # --- Tier 3: Walk-in Opportunities ---
    walkin_results = _safe_search(
        lambda: search_walkin(primary_skill, location),
        "walkin_search"
    )

    # Determine primary tier based on what's available
    primary_tier = _determine_primary_tier(job_results, freelance_results, walkin_results)

    # Build summary
    summary = _build_summary(primary_tier, primary_skill, job_results, freelance_results, walkin_results)

    return {
        "primary_tier": primary_tier,
        "jobs": job_results,
        "freelance": freelance_results,
        "walkin": walkin_results,
        "skills_searched": skills,
        "location": location,
        "summary": summary
    }


def _safe_search(search_fn, name: str) -> dict:
    """
    Execute a search function with full error isolation.
    Ensures one failing tier doesn't crash the entire aggregation.
    """
    try:
        result = search_fn()
        return result if result else {"error": f"{name} returned empty"}
    except Exception as e:
        logger.error(f"{name} failed: {e}")
        return {"error": str(e), "source": "error"}


def _determine_primary_tier(jobs: dict, freelance: dict, walkin: dict) -> str:
    """
    Deterministic tier selection logic.
    Priority: jobs > freelance > walkin
    """
    # Check if jobs have actual results (not just fallback links)
    if (jobs.get("source") == "indeed" and
            jobs.get("count", 0) > 0):
        return "jobs"

    # Check freelance
    if (freelance.get("count", 0) > 0 and
            "error" not in freelance):
        return "freelance"

    # Walk-in is always the safety net
    return "walkin"


def _build_summary(
    tier: str,
    skill: str,
    jobs: dict,
    freelance: dict,
    walkin: dict
) -> str:
    """Build a human-readable summary of what was found."""
    parts = []

    if tier == "jobs":
        count = jobs.get("count", 0)
        parts.append(f"Found {count} recent job listing(s) for '{skill}'.")
    elif tier == "freelance":
        count = freelance.get("count", 0)
        parts.append(f"Found {count} freelance platform(s) for '{skill}'.")
    else:
        count = walkin.get("count", 0)
        parts.append(f"Found {count} walk-in opportunity(ies) near you for '{skill}'.")

    # Add secondary options
    if tier != "freelance" and freelance.get("count", 0) > 0:
        parts.append(f"Also found {freelance['count']} freelance option(s).")
    if tier != "walkin" and walkin.get("count", 0) > 0:
        parts.append(f"Plus {walkin['count']} walk-in business(es) for direct contact.")

    return " ".join(parts)
