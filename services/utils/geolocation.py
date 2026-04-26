"""
Geolocation Wrapper — services/utils/geolocation.py
Thin adapter between Flask chat pipeline and IP-based geolocation service.
"""

import logging
from services.geolocation.geolocation_service import get_user_location

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Extract correct client IP with proxy support.
    """
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        ip = forwarded.split(",")[0].strip()
    elif request.headers.get("X-Real-IP"):
        ip = request.headers.get("X-Real-IP").strip()
    else:
        ip = request.remote_addr or "127.0.0.1"

    return ip


def resolve_user_location(request):
    """
    Resolve user's city from IP using existing geolocation service.
    """
    try:
        ip = get_client_ip(request)

        # Debug log
        print(f"[GEO] Resolved IP: {ip}")

        # 🔹 Local testing fallback ONLY
        if ip in ("127.0.0.1", "0.0.0.0"):
            return "Gurgaon"

        # 🔹 Call existing geo module
        result = get_user_location(ip)

        # 🔹 Handle failure cases
        if not result or result.get("status") == "fail" or "error" in result:
            logger.warning(f"[GEO] Failed lookup for IP: {ip}")
            return "India"

        # 🔹 Extract city
        city = result.get("city", "").strip()

        if city and city.lower() != "unknown":
            return city

        # 🔹 Fallback if no city found
        return "India"

    except Exception as e:
        logger.error(f"[GEO] Resolution error: {e}")
        return "India"