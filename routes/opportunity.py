"""
Opportunity Route — Direct endpoint for the opportunity engine.
Allows querying opportunities by skill and location without going
through the full chat pipeline.
"""

from flask import Blueprint, request, jsonify
import logging

from services.core.isco_mapper import map_skills_to_isco
from services.opportunity_engine.aggregator import find_opportunities

logger = logging.getLogger(__name__)

opportunity_bp = Blueprint("opportunity", __name__)


@opportunity_bp.route("/api/opportunities", methods=["POST"])
def get_opportunities():
    """
    Direct opportunity search endpoint.

    Request body:
        {
            "skills": ["python", "data science"],
            "location": "Bangalore"    // optional, defaults to "Remote"
        }

    Response:
        {
            "success": true,
            "opportunities": { ... tiered results ... },
            "isco_mapping": [ ... ]
        }
    """
    try:
        body = request.get_json(silent=True)

        if not body or not body.get("skills"):
            return jsonify({
                "success": False,
                "error": "Missing 'skills' field. Provide a list of skills."
            }), 400

        skills = body["skills"]
        if isinstance(skills, str):
            skills = [skills]  # Handle single skill as string

        location = body.get("location", "Remote")

        logger.info(f"Opportunity search: skills={skills}, location={location}")

        # Map to ISCO codes
        isco_results = map_skills_to_isco(skills)

        # Run tiered opportunity search
        opportunities = find_opportunities(skills, location)

        return jsonify({
            "success": True,
            "opportunities": opportunities,
            "isco_mapping": isco_results
        })

    except Exception as e:
        logger.error(f"Opportunity endpoint error: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "error": "Failed to search opportunities",
            "details": str(e)
        }), 500


@opportunity_bp.route("/api/opportunities/jobs", methods=["GET"])
def search_jobs_direct():
    """
    Quick job search via query params.

    Query params:
        ?skill=python&location=Remote
    """
    try:
        from services.opportunity_engine.job_search import search_jobs

        skill = request.args.get("skill", "general")
        location = request.args.get("location", "Remote")

        results = search_jobs(skill, location)

        return jsonify({
            "success": True,
            "results": results
        })

    except Exception as e:
        logger.error(f"Job search endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@opportunity_bp.route("/api/opportunities/freelance", methods=["GET"])
def search_freelance_direct():
    """
    Quick freelance search via query params.

    Query params:
        ?skill=python
    """
    try:
        from services.opportunity_engine.freelance_search import search_freelance

        skill = request.args.get("skill", "general")
        results = search_freelance(skill)

        return jsonify({
            "success": True,
            "results": results
        })

    except Exception as e:
        logger.error(f"Freelance search endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@opportunity_bp.route("/api/opportunities/walkin", methods=["GET"])
def search_walkin_direct():
    """
    Quick walk-in search via query params.

    Query params:
        ?skill=cooking&location=nearby
    """
    try:
        from services.opportunity_engine.walkin_search import search_walkin

        skill = request.args.get("skill", "general")
        location = request.args.get("location", "nearby")
        results = search_walkin(skill, location)

        return jsonify({
            "success": True,
            "results": results
        })

    except Exception as e:
        logger.error(f"Walk-in search endpoint error: {e}")
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500
