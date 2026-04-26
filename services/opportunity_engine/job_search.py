import requests
import logging
from urllib.parse import quote_plus

logger = logging.getLogger(__name__)

MAX_RESULTS = 3
SERPAPI_KEY = "cc5c16548358bf7d28e488060dfbeda3210a0ee59dcd4d8473befeefdec4fd85"  # 🔥 Replace with your key


# -----------------------------
# MAIN FUNCTION
# -----------------------------
def search_jobs(skill: str, location: str = "India") -> dict:
    skill = skill.lower().strip()

    try:
        data = _fetch_serpapi(skill, location)

        if data:
            return _parse_serpapi(data, skill, location)

    except Exception as e:
        logger.warning(f"SerpAPI failed: {e}")

    return _fallback_jobs(skill, location)


# -----------------------------
# FETCH FROM SERPAPI
# -----------------------------
def _fetch_serpapi(skill: str, location: str):
    url = "https://serpapi.com/search"

    params = {
        "engine": "google_jobs",
        "q": f"{skill} jobs {location}",
        "hl": "en",
        "api_key": SERPAPI_KEY
    }

    logger.info(f"Trying SerpAPI for: {skill} in {location}")

    response = requests.get(url, params=params, timeout=6)
    data = response.json()

    if "error" in data:
        logger.warning(f"SerpAPI error: {data['error']}")
        return None

    return data


# -----------------------------
# PARSE SERPAPI RESPONSE
# -----------------------------
def _parse_serpapi(data: dict, skill: str, location: str) -> dict:
    jobs = []

    # 🔥 GLOBAL FALLBACK LINK (VERY IMPORTANT)
    google_jobs_url = data.get("search_metadata", {}).get("google_jobs_url", "")

    for job in data.get("jobs_results", [])[:MAX_RESULTS]:
        link = _extract_job_link(job)

        # 🔥 GUARANTEE LINK
        if not link:
            link = google_jobs_url or _build_google_fallback(skill, location)

        jobs.append({
            "title": job.get("title", "Job"),
            "company": job.get("company_name", "Unknown"),
            "location": job.get("location", location),
            "link": link,
            "source": "Google Jobs (SerpAPI)"
        })

    # 🔥 OPTIONAL FILTERS (FOR DEMO WOW)
    filters = []
    for f in data.get("filters", [])[:2]:
        filters.append({
            "name": f.get("name"),
            "link": f.get("link")
        })

    return {
        "jobs": jobs,
        "filters": filters,
        "source": "serpapi",
        "count": len(jobs),
        "query": f"{skill} jobs {location}"
    }


# -----------------------------
# LINK EXTRACTION
# -----------------------------
def _extract_job_link(job: dict) -> str:
    # 1. Try apply options
    apply_options = job.get("apply_options", [])
    if apply_options and isinstance(apply_options, list):
        link = apply_options[0].get("link")
        if link:
            return link

    # 2. Try related links
    related_links = job.get("related_links", [])
    if related_links and isinstance(related_links, list):
        link = related_links[0].get("link")
        if link:
            return link

    return ""


# -----------------------------
# GOOGLE FALLBACK LINK
# -----------------------------
def _build_google_fallback(skill: str, location: str) -> str:
    encoded_skill = quote_plus(skill)
    encoded_loc = quote_plus(location)

    return f"https://www.google.com/search?q={encoded_skill}+jobs+{encoded_loc}&ibp=htl;jobs"


# -----------------------------
# FINAL FALLBACK (IF SERPAPI FAILS)
# -----------------------------
def _fallback_jobs(skill: str, location: str):
    encoded_skill = quote_plus(skill)
    encoded_loc = quote_plus(location)

    return {
        "jobs": [
            {
                "title": f"{skill.title()} Jobs — Indeed",
                "company": "Multiple Employers",
                "location": location,
                "link": f"https://www.indeed.com/jobs?q={encoded_skill}&l={encoded_loc}",
                "source": "Indeed"
            },
            {
                "title": f"{skill.title()} Jobs — LinkedIn",
                "company": "Multiple Employers",
                "location": location,
                "link": f"https://www.linkedin.com/jobs/search/?keywords={encoded_skill}&location={encoded_loc}",
                "source": "LinkedIn"
            },
            {
                "title": f"{skill.title()} Jobs — Google",
                "company": "Multiple Employers",
                "location": location,
                "link": _build_google_fallback(skill, location),
                "source": "Google Jobs"
            }
        ],
        "source": "fallback",
        "count": 3,
        "query": skill,
        "note": "SerpAPI unavailable. Direct search links provided."
    }