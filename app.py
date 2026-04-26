from flask import Flask, jsonify
from flask_cors import CORS
import logging
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


def create_app() -> Flask:
    """Application factory — creates and configures the Flask app."""

    app = Flask(__name__)

    # Enable CORS for frontend integration
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # App configuration
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1MB max request size

    # ── Register route blueprints ──
    from routes.chat import chat_bp
    from routes.opportunity import opportunity_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(opportunity_bp)

    # ── Health check and root endpoints ──

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "name": "UNMAPPED API",
            "version": "1.0.0",
            "status": "running",
            "description": "Conversational AI system for skill-to-opportunity mapping",
            "endpoints": {
                "chat": "POST /api/chat",
                "opportunities": "POST /api/opportunities",
                "jobs": "GET /api/opportunities/jobs?skill=python&location=Remote",
                "freelance": "GET /api/opportunities/freelance?skill=python",
                "walkin": "GET /api/opportunities/walkin?skill=cooking",
                "health": "GET /api/health"
            }
        })

    @app.route("/api/health", methods=["GET"])
    def health():
        """Health check — verifies Ollama connectivity."""
        from services.llm.llm_client import check_health

        ollama_ok = check_health()

        return jsonify({
            "status": "healthy" if ollama_ok else "degraded",
            "ollama": "connected" if ollama_ok else "unavailable",
            "note": (
                "All systems operational."
                if ollama_ok
                else "Ollama is not reachable. LLM features will use fallbacks."
            )
        }), 200 if ollama_ok else 503

    # ── Global error handlers ──

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Endpoint not found", "success": False}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"error": "Method not allowed", "success": False}), 405

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error", "success": False}), 500

    logger.info("UNMAPPED API initialized successfully")
    return app


# ── Main entry point ──
if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5000))
    debug = False

    logger.info(f"Starting UNMAPPED API on port {port} (debug={debug})")
    app.run(host="0.0.0.0", port=port, debug=debug)
