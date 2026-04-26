"""
Chat Route â€” Main conversational endpoint.
Orchestrates the full pipeline: skill extraction â†’ intent detection â†’
ISCO mapping â†’ opportunity aggregation â†’ LLM response formatting.
"""

from flask import Blueprint, request, jsonify
import logging
import json

from services.core.skill_extractor import extract_skills
from services.core.intent_detector import detect_intent
from services.core.isco_mapper import map_skills_to_isco
from services.core.learning_engine import generate_learning, get_available_roles
from services.opportunity_engine.aggregator import find_opportunities
from services.llm.llm_client import query_llm
from services.llm.prompts import response_prompt
from services.utils.geolocation import resolve_user_location

logger = logging.getLogger(__name__)

chat_bp = Blueprint("chat", __name__)


@chat_bp.route("/api/chat", methods=["POST"])
def chat():
    """
    Main chat endpoint. Accepts natural language input, processes it
    through the full pipeline, and returns a structured + formatted response.

    Request body:
        { "message": "I know Python and want a job in Bangalore" }

    Response:
        {
            "success": true,
            "response": "formatted text from LLM",
            "data": { ... pipeline results ... }
        }
    """
    try:
        body = request.get_json(silent=True)

        if not body or not body.get("message"):
            return jsonify({
                "success": False,
                "error": "Missing 'message' field in request body"
            }), 400

        user_message = body["message"].strip()
        if not user_message:
            return jsonify({
                "success": False,
                "error": "Message cannot be empty"
            }), 400

        logger.info(f"Chat request: '{user_message[:100]}'")

        # â”€â”€ Step 1: Extract skills from user input â”€â”€
        skill_data = extract_skills(user_message)
        skills = skill_data.get("skills", [])

        # Location priority: request body > LLM extraction > default
        # 🔥 Geolocation integration

        # 🔥 MVP MODE: force Gurugram location
        location = "Gurugram"
        detected_location = "Gurugram"

        logger.info("[GEO] MVP mode → using Gurugram")

        logger.info(f"[GEO] Final location used: {location}")

        logger.info(f"Extracted skills: {skills}, location: {location}")

        # â”€â”€ Step 2: Detect user intent â”€â”€
        intent_data = detect_intent(user_message)
        intent = intent_data.get("intent", "opportunity")

        logger.info(f"Detected intent: {intent}")

        # â”€â”€ Step 3: Map skills to ISCO codes â”€â”€
        isco_results = map_skills_to_isco(skills)

        # -- Step 3b: LEARNING intent -- branch to learning engine --
        if intent == "learning":
            return _handle_learning_intent(
                skills, isco_results, skill_data, intent_data, body
            )

        # â”€â”€ Step 4: Find opportunities (tiered search) â”€â”€
        opportunities = {}
        if intent in ("opportunity", "unknown"):
            opportunities = find_opportunities(skills, location)

        # â”€â”€ Step 5: Compile results for LLM formatting â”€â”€
        pipeline_results = {
            "skills": skill_data,
            "intent": intent_data,
            "isco_mapping": isco_results,
            "opportunities": opportunities
        }

        # â”€â”€ Step 6: Format response with LLM â”€â”€
        formatted_response = _format_response_template(pipeline_results)

        return jsonify({
            "success": True,
            "response": formatted_response,
            "data": pipeline_results
        })

    except Exception as e:
        logger.error(f"Chat endpoint error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "An internal error occurred. Please try again.",
            "details": str(e)
        }), 500


def _format_with_llm(user_input: str, results: dict) -> str:
    """
    Use LLM to create a human-friendly response from raw pipeline data.
    Falls back to a simple text formatter if LLM is unavailable.
    """
    try:
        # Simplify results for the LLM prompt (avoid overly large payloads)
        simplified = _simplify_results(results)
        prompt = response_prompt(user_input, json.dumps(simplified))
        formatted = query_llm(prompt, temperature=0.5)

        # Check if LLM returned an error JSON
        if '"error"' in formatted and len(formatted) < 100:
            return _fallback_format(results)

        return formatted

    except Exception as e:
        logger.warning(f"LLM formatting failed, using fallback: {e}")
        return _fallback_format(results)
    
    
def _format_response_template(results: dict) -> str:
    parts = []

    skills = results.get("skills", {}).get("skills", [])
    if skills:
        parts.append(f"You can work in: {', '.join(skills)}.\n")

    opps = results.get("opportunities", {})

    # JOBS
    jobs = opps.get("jobs", {}).get("jobs", [])
    if jobs:
        parts.append("🔹 Job Opportunities:")
        for j in jobs[:2]:
            parts.append(f"- {j.get('title')} at {j.get('company')}")
            parts.append(f"  {j.get('link')}")

    # FILTERS
    filters = opps.get("jobs", {}).get("filters", [])
    if filters:
        parts.append("\n🔹 More options:")
        for f in filters[:2]:
            parts.append(f"- {f.get('name')} → {f.get('link')}")

    # FREELANCE
    freelance = opps.get("freelance", {}).get("opportunities", [])
    if freelance:
        parts.append("\n🔹 Other ways to earn:")
        for f in freelance:
            if f.get("type") == "platform":
                parts.append(f"- Try {f.get('platform')} → {f.get('link')}")
            elif f.get("type") == "idea":
                tag = f.get("tag")
                if tag == "doorstep_service":
                    parts.append("- Offer doorstep repair services")
                elif tag == "shop_partnership":
                    parts.append("- Partner with local repair shops")
                elif tag == "emergency_service":
                    parts.append("- Provide emergency repair services")
                elif tag == "local_listing":
                    parts.append("- Promote your service locally")

    # WALK-IN
    walkin = opps.get("walkin", {}).get("places", [])
    if walkin:
        parts.append("\n🔹 Walk-in opportunities:")
        for w in walkin[:2]:
            parts.append(f"- Visit nearby {w.get('type')}")
            parts.append(f"  {w.get('map_link')}")

    parts.append("\nStart with jobs first, then try other options if needed.")

    return "\n".join(parts)


# -----------------------------
# ONLY THIS FUNCTION IS UPDATED
# -----------------------------
def _simplify_results(results: dict) -> dict:
    """Trim results to essential info to keep the LLM prompt manageable."""
    skills_list = results.get("skills", {}).get("skills", [])
    simplified = {
        "skills_found": skills_list,
        "intent": results.get("intent", {}).get("intent", "unknown"),
    }

    # Include ISCO role titles
    isco = results.get("isco_mapping", [])
    if isco:
        simplified["matched_roles"] = [
            {
                "skill": m.get("skill", ""),
                "role": m.get("title", ""),
                "confidence": m.get("confidence", "")
            }
            for m in isco if m.get("mapped")
        ]

    opps = results.get("opportunities", {})
    if opps:
        simplified["primary_tier"] = opps.get("primary_tier", "unknown")
        simplified["summary"] = opps.get("summary", "")

        # -----------------------------
        # JOBS (unchanged + filters added)
        # -----------------------------
        jobs = opps.get("jobs", {})
        if jobs.get("jobs"):
            simplified["jobs"] = [
                {
                    "title": j.get("title", ""),
                    "company": j.get("company", ""),
                    "link": j.get("link", "")
                }
                for j in jobs["jobs"][:3]
            ]

        # 🔥 ADD FILTERS (NEW)
        if jobs.get("filters"):
            simplified["job_filters"] = [
                {
                    "name": f.get("name", ""),
                    "link": f.get("link", "")
                }
                for f in jobs["filters"][:2]
            ]

        # -----------------------------
        # FREELANCE (FIXED)
        # -----------------------------
        freelance = opps.get("freelance", {})
        if freelance.get("opportunities"):
            simplified["freelance"] = freelance["opportunities"][:4]

        # -----------------------------
        # WALK-IN (FIXED)
        # -----------------------------
        walkin = opps.get("walkin", {})
        if walkin.get("places"):
            simplified["walkin"] = walkin["places"][:3]

    return simplified


def _fallback_format(results: dict) -> str:
    """Simple text formatter when LLM is unavailable."""
    parts = ["Here's what I found for you:\n"]

    skills = results.get("skills", {}).get("skills", [])
    if skills:
        parts.append(f"**Skills identified:** {', '.join(skills)}\n")

    opps = results.get("opportunities", {})
    if opps:
        tier = opps.get("primary_tier", "")
        summary = opps.get("summary", "")
        if summary:
            parts.append(f"**Summary:** {summary}\n")

        # Jobs
        jobs = opps.get("jobs", {}).get("jobs", [])
        if jobs:
            parts.append("\n**Job Opportunities:**")
            for j in jobs[:3]:
                parts.append(f"â€¢ {j.get('title', 'N/A')} at {j.get('company', 'N/A')} â€” {j.get('link', '')}")

        # Freelance
        freelance = opps.get("freelance", {}).get("suggestions", [])
        if freelance:
            parts.append("\n**Freelance Options:**")
            for f in freelance[:3]:
                parts.append(f"â€¢ {f.get('platform', 'N/A')}: {f.get('gig_type', 'N/A')} â€” {f.get('url', '')}")

        # Walk-in
        walkin = opps.get("walkin", {}).get("businesses", [])
        if walkin:
            parts.append("\n**Walk-in Opportunities:**")
            for w in walkin[:3]:
                parts.append(f"â€¢ {w.get('name', 'N/A')} ({w.get('contact', 'N/A')}) â€” {w.get('strategy', '')}")

    parts.append("\nKeep going â€” every step forward counts! ðŸ’ª")
    return "\n".join(parts)


# ──────────────────────────────────────────────
#  Learning Engine Integration
# ──────────────────────────────────────────────

def _handle_learning_intent(
    skills: list[str],
    isco_results: list[dict],
    skill_data: dict,
    intent_data: dict,
    body: dict,
):
    """
    Handle intent='learning' by calling the learning engine.
    Derives the target role from ISCO mapping results or request body.
    Returns a Flask JSON response.
    """
    target_role = body.get("role", "").strip()

    if not target_role:
        target_role = _best_role_from_isco(isco_results)

    if not target_role:
        return jsonify({
            "success": True,
            "response": (
                "I'd love to create a learning plan for you! "
                "Could you tell me what role you're aiming for?\n\n"
                "Some examples: "
                + ", ".join(get_available_roles()[:10])
                + ", and more."
            ),
            "data": {
                "skills": skill_data,
                "intent": intent_data,
                "available_roles": get_available_roles(),
            },
        })

    learning_plan = generate_learning(skills, target_role)
    formatted = _format_learning_response(learning_plan)

    return jsonify({
        "success": True,
        "response": formatted,
        "data": {
            "skills": skill_data,
            "intent": intent_data,
            "isco_mapping": isco_results,
            "learning_plan": learning_plan,
        },
    })


def _best_role_from_isco(isco_results: list[dict]) -> str:
    """Extract the most confident mapped role title from ISCO results."""
    mapped = [r for r in isco_results if r.get("mapped") and r.get("title")]
    if not mapped:
        return ""
    for level in ("exact", "high", "medium", "low"):
        for r in mapped:
            if r.get("confidence", "").lower() == level:
                return r["title"]
    return mapped[0]["title"]


def _format_learning_response(plan: dict) -> str:
    """Convert a learning engine result into user-friendly text."""
    if plan.get("error") == "unknown_role":
        roles_sample = plan.get("available_roles", [])[:10]
        return (
            "I could not find the role you mentioned.\n\n"
            "Here are some roles I can help with:\n"
            + "\n".join(f"  - {r}" for r in roles_sample)
            + "\n\nTry again with one of these!"
        )

    role = plan.get("role", "your target role")
    stage = plan.get("stage", "")
    progress = plan.get("progress", {})
    pct = progress.get("percent_complete", 0)
    parts = []

    if stage == "ready":
        parts.append(f"Great news! You are job-ready for {role}!")
        parts.append(f"\nProgress: {pct}% complete")
        parts.append("\n" + plan.get("message", ""))
        return "\n".join(parts)

    parts.append(f"Learning Plan for {role}")
    parts.append(f"You are {pct}% of the way there!")
    parts.append(f"\nCurrent stage: {stage.title()}")

    focus = plan.get("focus_skills", [])
    if focus:
        parts.append("\nSkills to learn next:")
        for i, skill in enumerate(focus, 1):
            parts.append(f"  {i}. {skill}")

    resources = plan.get("resources", {})
    if resources:
        parts.append("\nLearning resources:")
        for skill, links in resources.items():
            parts.append(f"\n  {skill}:")
            if links.get("youtube"):
                parts.append(f"    YouTube: {links['youtube']}")
            if links.get("google"):
                parts.append(f"    Google: {links['google']}")
            if links.get("freeCodeCamp"):
                parts.append(f"    freeCodeCamp: {links['freeCodeCamp']}")

    parts.append(
        "\nMaster these skills first, then come back "
        "for your next learning stage!"
    )
    return "\n".join(parts)
