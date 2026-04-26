"""
Findy — IP-Based Geolocation Service
=====================================
Standalone, plug-and-play FastAPI module that resolves a user's
approximate city-level location from their IP address.

Usage:
    from geolocation_service import router
    app.include_router(router, prefix="/api")
"""

from __future__ import annotations

import requests
from fastapi import APIRouter, Request, Query
from fastapi.responses import JSONResponse

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_IP_API_URL = "http://ip-api.com/json/{ip}"
_TIMEOUT_SECONDS = 5

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
router = APIRouter(tags=["Geolocation"])

# ---------------------------------------------------------------------------
# Helper — extract the real client IP
# ---------------------------------------------------------------------------

def _extract_client_ip(request: Request) -> str:
    """Return the most likely real client IP from the incoming request.

    Priority:
      1. ``X-Forwarded-For`` header (first entry — original client behind proxies)
      2. ``request.client.host`` (direct connection)
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # The header may contain a comma-separated list; the first is the client.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"

# ---------------------------------------------------------------------------
# Core function — reusable by other backend modules
# ---------------------------------------------------------------------------

def get_user_location(ip_address: str) -> dict:
    """Resolve *ip_address* to approximate city-level geodata.

    Returns a dict with keys: city, region, country, latitude, longitude,
    source, and accuracy.  On failure returns an error/fallback dict.
    """
    try:
        response = requests.get(
            _IP_API_URL.format(ip=ip_address),
            timeout=_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        data = response.json()

        if data.get("status") == "fail":
            return _error_response(data.get("message", "Invalid IP or lookup failed"))

        return {
            "city": data.get("city", "Unknown"),
            "region": data.get("regionName", "Unknown"),
            "country": data.get("country", "Unknown"),
            "latitude": data.get("lat"),
            "longitude": data.get("lon"),
            "source": "ip-based",
            "accuracy": "approximate",
        }
    except requests.RequestException as exc:
        return _error_response(str(exc))

# ---------------------------------------------------------------------------
# Private helper — error payload
# ---------------------------------------------------------------------------

def _error_response(detail: str = "Unable to fetch location") -> dict:
    """Build a standardised error payload."""
    return {
        "error": detail,
        "fallback": "manual_input_required",
    }

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get("/location")
async def locate_user(
    request: Request,
    ip: str | None = Query(default=None, description="Optional IP to look up (for testing)"),
):
    """Return the caller's approximate location based on their IP.

    Pass ``?ip=8.8.8.8`` to test with an explicit address.
    """
    target_ip = ip or _extract_client_ip(request)
    result = get_user_location(target_ip)

    if "error" in result:
        return JSONResponse(status_code=502, content=result)

    return result
