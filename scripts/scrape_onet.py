#!/usr/bin/env python3
"""
O*NET Role Skills Scraper — scripts/scrape_onet.py

Scrapes role-based skills from O*NET occupation pages and generates
data/role_skills.json for use by the UNMAPPED career assistant backend.

Three-layer strategy:
  1. Live scrape via requests + BeautifulSoup
  2. Curated fallback dataset (embedded, always available)
  3. Merge: live data overrides curated, curated fills gaps

Usage:
    python scripts/scrape_onet.py
    python scripts/scrape_onet.py --force   # ignore cache, re-scrape all

Output:
    data/role_skills.json
"""

import json
import os
import re
import sys
import time
import hashlib
import argparse
import logging
from pathlib import Path

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_SCRAPING = True
except ImportError:
    HAS_SCRAPING = False

# ──────────────────────────────────────────────
#  Configuration
# ──────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
OUTPUT_FILE = PROJECT_ROOT / "data" / "role_skills.json"
CACHE_DIR = PROJECT_ROOT / "data" / ".onet_cache"

BASE_URL = "https://www.onetonline.org/link/summary/{code}"
REQUEST_DELAY = 2.0  # seconds between requests (be respectful)
REQUEST_TIMEOUT = 15
MAX_RETRIES = 2

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("onet_scraper")

# ──────────────────────────────────────────────
#  ISCO Role → O*NET Code Mapping
# ──────────────────────────────────────────────

ROLE_ONET_MAP = {
    # Software / IT
    "Web Developer":                "15-1254.00",
    "Software Developer":           "15-1252.00",
    "Applications Programmer":      "15-1251.00",
    "Database Designer":            "15-1242.00",
    "Systems Administrator":        "15-1244.00",
    "Network Professional":         "15-1241.00",
    "Security Analyst":             "15-1212.00",
    "Data Scientist":               "15-2051.00",
    "Systems Analyst":              "15-1211.00",

    # Design / Creative
    "Graphic Designer":             "27-1024.00",
    "Multimedia Designer":          "27-1014.00",
    "Photographer":                 "27-4021.00",

    # Business / Finance
    "Accountant":                   "13-2011.00",
    "Financial Analyst":            "13-2051.00",
    "Bookkeeper":                   "43-3031.00",
    "Marketing Professional":       "13-1161.00",
    "Project Manager":              "11-9199.00",
    "Public Relations Professional":"27-3031.00",

    # Writing / Media
    "Author":                       "27-3043.00",
    "Journalist":                   "27-3023.00",

    # Education
    "Secondary Education Teacher":  "25-2031.00",
    "Teaching Professional":        "25-3099.00",

    # Healthcare
    "Nursing Professional":         "29-1141.00",
    "Health Professional":          "29-9099.00",

    # Food / Hospitality
    "Chef":                         "35-1011.00",
    "Cook":                         "35-2014.00",

    # Trades / Manual
    "Electrician":                  "47-2111.00",
    "Plumber":                      "47-2152.00",
    "Carpenter":                    "47-2031.00",
    "Welder":                       "51-4121.00",
    "Tailor":                       "51-6052.00",
    "Electronics Mechanic":         "49-2094.00",
    "Computer Hardware Technician": "49-2011.00",
    "Air Conditioning Mechanic":    "49-9021.00",

    # Transport / Logistics
    "Driver":                       "53-3032.00",

    # Agriculture
    "Field Crop Grower":            "45-2092.00",
    "Gardener":                     "37-3011.00",

    # Retail / Service
    "Shop Sales Assistant":         "41-2031.00",
    "Contact Centre Agent":         "43-4051.00",
    "Data Entry Clerk":             "43-9021.00",

    # Management
    "Managing Director":            "11-1011.00",
}


# ──────────────────────────────────────────────
#  Curated Fallback Skills (always available)
#  Sourced from O*NET summaries, manually cleaned.
# ──────────────────────────────────────────────

CURATED_SKILLS: dict[str, list[str]] = {
    "Web Developer": [
        "html", "css", "javascript", "react", "vue.js", "angular", "node.js",
        "typescript", "bootstrap", "git", "sql", "mongodb", "rest api",
        "python", "php", "sass", "webpack", "docker", "aws", "figma",
        "responsive design", "web accessibility", "seo", "graphql",
        "spring framework", "postgresql", "redis", "wordpress",
    ],
    "Software Developer": [
        "python", "java", "c++", "c#", "javascript", "sql", "git",
        "docker", "kubernetes", "aws", "linux", "rest api", "agile",
        "unit testing", "ci/cd", "microservices", "data structures",
        "algorithms", "object-oriented programming", "debugging",
        "spring boot", "postgresql", ".net", "redis",
    ],
    "Applications Programmer": [
        "python", "java", "c#", "javascript", "sql", "git",
        "visual studio", "eclipse", "debugging", "unit testing",
        "object-oriented programming", "data structures", "algorithms",
        "rest api", "agile", "scrum",
    ],
    "Database Designer": [
        "sql", "postgresql", "mysql", "oracle", "mongodb", "redis",
        "database design", "data modeling", "indexing", "query optimization",
        "etl", "data warehousing", "backup and recovery", "nosql",
        "stored procedures", "database security",
    ],
    "Systems Administrator": [
        "linux", "windows server", "bash scripting", "powershell",
        "docker", "kubernetes", "aws", "azure", "networking", "firewalls",
        "dns", "dhcp", "monitoring", "nagios", "ansible", "terraform",
        "backup and recovery", "active directory", "vmware",
    ],
    "Network Professional": [
        "tcp/ip", "dns", "dhcp", "routing", "switching", "firewalls",
        "vpn", "cisco", "network security", "wireshark", "load balancing",
        "wireless networking", "lan/wan", "network monitoring",
    ],
    "Security Analyst": [
        "cybersecurity", "penetration testing", "siem", "firewalls",
        "encryption", "vulnerability assessment", "incident response",
        "network security", "authentication", "linux", "python",
        "risk assessment", "compliance", "malware analysis",
    ],
    "Data Scientist": [
        "python", "r", "sql", "machine learning", "deep learning",
        "tensorflow", "pytorch", "pandas", "numpy", "scikit-learn",
        "data visualization", "statistics", "nlp", "big data",
        "spark", "jupyter", "a/b testing", "feature engineering",
    ],
    "Systems Analyst": [
        "requirements analysis", "system design", "sql", "uml",
        "business analysis", "project management", "data flow diagrams",
        "testing", "documentation", "agile", "scrum",
    ],
    "Graphic Designer": [
        "photoshop", "illustrator", "figma", "indesign", "typography",
        "color theory", "branding", "layout design", "vector graphics",
        "ui design", "print design", "adobe creative suite",
    ],
    "Multimedia Designer": [
        "after effects", "premiere pro", "photoshop", "illustrator",
        "figma", "animation", "motion graphics", "video editing",
        "3d modeling", "ui/ux design", "storyboarding",
    ],
    "Photographer": [
        "photography", "photo editing", "lightroom", "photoshop",
        "lighting", "composition", "color correction", "portrait photography",
        "product photography", "camera operation",
    ],
    "Accountant": [
        "accounting", "bookkeeping", "financial statements", "tax preparation",
        "auditing", "quickbooks", "excel", "payroll", "budgeting",
        "gaap", "accounts payable", "accounts receivable", "sap",
    ],
    "Financial Analyst": [
        "financial modeling", "excel", "financial reporting", "budgeting",
        "forecasting", "valuation", "data analysis", "sql", "python",
        "bloomberg terminal", "risk analysis", "investment analysis",
    ],
    "Bookkeeper": [
        "bookkeeping", "quickbooks", "excel", "accounts payable",
        "accounts receivable", "bank reconciliation", "payroll",
        "data entry", "invoicing", "financial records",
    ],
    "Marketing Professional": [
        "digital marketing", "seo", "sem", "google analytics", "social media",
        "content marketing", "email marketing", "copywriting",
        "market research", "branding", "hubspot", "ppc advertising",
    ],
    "Project Manager": [
        "project management", "agile", "scrum", "budgeting",
        "risk management", "stakeholder management", "ms project",
        "jira", "resource planning", "scheduling", "reporting",
    ],
    "Public Relations Professional": [
        "public relations", "media relations", "press releases",
        "crisis communication", "social media", "content creation",
        "event planning", "brand management", "copywriting",
    ],
    "Author": [
        "writing", "editing", "proofreading", "content creation",
        "research", "storytelling", "grammar", "publishing",
        "content strategy", "seo writing", "blogging",
    ],
    "Journalist": [
        "journalism", "reporting", "interviewing", "research",
        "writing", "editing", "fact-checking", "media ethics",
        "social media", "video production", "photography",
    ],
    "Secondary Education Teacher": [
        "teaching", "lesson planning", "curriculum development",
        "classroom management", "assessment", "student engagement",
        "educational technology", "differentiated instruction",
    ],
    "Teaching Professional": [
        "teaching", "tutoring", "curriculum design", "assessment",
        "student mentoring", "presentation", "educational psychology",
    ],
    "Nursing Professional": [
        "patient care", "clinical assessment", "medication administration",
        "wound care", "vital signs monitoring", "infection control",
        "cpr", "electronic health records", "patient education",
        "emergency care", "iv therapy",
    ],
    "Health Professional": [
        "patient care", "clinical assessment", "medical terminology",
        "health education", "infection control", "medical records",
        "emergency response", "first aid",
    ],
    "Chef": [
        "cooking", "menu planning", "food safety", "kitchen management",
        "recipe development", "inventory management", "food presentation",
        "team leadership", "cost control", "nutrition",
    ],
    "Cook": [
        "cooking", "food preparation", "food safety", "grilling",
        "baking", "knife skills", "kitchen equipment operation",
        "recipe following", "time management",
    ],
    "Electrician": [
        "electrical wiring", "circuit testing", "blueprint reading",
        "electrical code compliance", "troubleshooting", "conduit bending",
        "panel installation", "grounding", "power tools",
        "safety protocols", "plc programming",
    ],
    "Plumber": [
        "plumbing", "pipe fitting", "soldering", "blueprint reading",
        "leak detection", "water heater installation", "drainage systems",
        "plumbing code compliance", "troubleshooting",
    ],
    "Carpenter": [
        "carpentry", "woodworking", "blueprint reading", "framing",
        "finishing", "cabinet making", "power tools", "joinery",
        "measurement", "safety protocols",
    ],
    "Welder": [
        "mig welding", "tig welding", "arc welding", "blueprint reading",
        "metal fabrication", "cutting", "grinding", "safety protocols",
        "welding inspection", "brazing",
    ],
    "Tailor": [
        "sewing", "pattern making", "fabric cutting", "alterations",
        "fitting", "hand stitching", "sewing machine operation",
        "measurements", "garment construction", "textile knowledge",
    ],
    "Electronics Mechanic": [
        "circuit troubleshooting", "soldering", "diagnostics",
        "oscilloscope operation", "schematic reading", "pcb repair",
        "component testing", "signal analysis", "multimeter use",
        "electronic assembly", "firmware updating",
    ],
    "Computer Hardware Technician": [
        "hardware troubleshooting", "component replacement", "diagnostics",
        "operating system installation", "networking basics", "soldering",
        "data recovery", "preventive maintenance", "customer service",
    ],
    "Air Conditioning Mechanic": [
        "hvac systems", "refrigerant handling", "electrical troubleshooting",
        "thermostat installation", "ductwork", "compressor repair",
        "system maintenance", "epa certification", "brazing",
    ],
    "Driver": [
        "driving", "vehicle maintenance", "navigation", "route planning",
        "safety compliance", "time management", "customer service",
        "defensive driving", "load management",
    ],
    "Field Crop Grower": [
        "farming", "crop cultivation", "irrigation", "soil management",
        "pest control", "fertilization", "harvest techniques",
        "agricultural equipment operation", "weather monitoring",
    ],
    "Gardener": [
        "gardening", "landscaping", "pruning", "planting", "irrigation",
        "soil preparation", "pest management", "lawn maintenance",
        "plant identification", "composting",
    ],
    "Shop Sales Assistant": [
        "customer service", "sales", "cash handling", "product knowledge",
        "inventory management", "merchandising", "point of sale",
        "upselling", "stock management",
    ],
    "Contact Centre Agent": [
        "customer service", "communication", "data entry", "crm software",
        "problem solving", "phone etiquette", "multitasking",
        "complaint handling", "typing", "documentation",
    ],
    "Data Entry Clerk": [
        "data entry", "typing", "excel", "attention to detail",
        "database management", "data verification", "filing",
        "record keeping", "office software",
    ],
    "Managing Director": [
        "leadership", "strategic planning", "financial management",
        "business development", "team management", "decision making",
        "negotiation", "stakeholder management", "budgeting",
        "organizational development",
    ],
}

# ──────────────────────────────────────────────
#  Vague / too-generic skills to filter out
# ──────────────────────────────────────────────

VAGUE_SKILLS = {
    "critical thinking", "active listening", "reading comprehension",
    "speaking", "writing", "monitoring", "coordination",
    "time management", "judgment and decision making",
    "active learning", "complex problem solving",
    "systems analysis", "systems evaluation",
    "operations analysis", "social perceptiveness",
    "persuasion", "negotiation", "instructing",
    "service orientation", "learning strategies",
    "management of personnel resources",
    "management of financial resources",
    "management of material resources",
    "quality control analysis", "operation monitoring",
    "operation and control", "equipment maintenance",
    "troubleshooting", "repairing", "equipment selection",
    "installation", "technology design",
    "science", "mathematics",
    "english language",
}

# ──────────────────────────────────────────────
#  Skill normalization map
# ──────────────────────────────────────────────

NORMALIZE_MAP = {
    "java script": "javascript",
    "type script": "typescript",
    "node js": "node.js",
    "vue js": "vue.js",
    "react js": "react",
    "angular js": "angular",
    "next js": "next.js",
    "c sharp": "c#",
    "c plus plus": "c++",
    "dot net": ".net",
    "postgre sql": "postgresql",
    "my sql": "mysql",
    "mongo db": "mongodb",
    "power shell": "powershell",
    "fire wall": "firewall",
    "fire walls": "firewalls",
    "photo shop": "photoshop",
    "adobe photoshop": "photoshop",
    "adobe illustrator": "illustrator",
    "adobe indesign": "indesign",
    "adobe after effects": "after effects",
    "adobe premiere pro": "premiere pro",
    "adobe creative cloud software": "adobe creative suite",
    "microsoft excel": "excel",
    "microsoft word": "word",
    "microsoft project": "ms project",
    "microsoft office software": "microsoft office",
    "microsoft sharepoint": "sharepoint",
    "microsoft visio": "visio",
    "microsoft sql server reporting services ssrs": "sql server reporting",
    "microsoft sql server integration services ssis": "sql server integration",
    "microsoft windows server": "windows server",
    "google analytics": "google analytics",
    "google android": "android",
    "salesforce software": "salesforce",
    "sap software": "sap",
    "oracle pl/sql": "pl/sql",
    "oracle java 2 platform enterprise edition j2ee": "j2ee",
    "apache maven": "maven",
    "apache spark": "spark",
    "apache subversion svn": "svn",
    "apache http server": "apache",
    "apache kafka": "kafka",
    "apache hive": "hive",
    "atlassian confluence": "confluence",
    "atlassian jira": "jira",
    "atlassian bitbucket": "bitbucket",
    "atlassian hipchat": "hipchat",
    "ibm spss statistics": "spss",
    "ibm cognos impromptu": "cognos",
    "esri arcgis software": "arcgis",
    "the mathworks matlab": "matlab",
    "red hat enterprise linux": "rhel",
    "red hat openshift": "openshift",
    "amazon web services aws cloudformation": "aws cloudformation",
    "amazon dynamodb": "dynamodb",
    "amazon simple storage service s3": "aws s3",
    "ansible software": "ansible",
    "hibernate orm": "hibernate",
    "jenkins ci": "jenkins",
    "extensible markup language xml": "xml",
    "unified modeling language uml": "uml",
    "hypertext markup language": "html",
    "cascading style sheets": "css",
    "customer information control system cics": "cics",
    "geographic information system gis software": "gis",
    "nortonlifelock cybersecurity software": "norton antivirus",
    "epic systems": "epic ehr",
    "cisco webex": "webex",
    "hubspot software": "hubspot",
    "marketo marketing automation": "marketo",
    "splunk enterprise": "splunk",
    "quest erwin data modeler": "erwin",
    "hewlett packard loadrunner": "loadrunner",
    "delphi technology": "delphi",
}


# ──────────────────────────────────────────────
#  1. HTTP Fetching (with disk cache)
# ──────────────────────────────────────────────

def _cache_path(code: str) -> Path:
    """Return the cache file path for an O*NET code."""
    safe = code.replace("/", "_").replace(".", "_")
    return CACHE_DIR / f"{safe}.html"


def fetch_onet_page(code: str, force: bool = False) -> str | None:
    """
    Fetch an O*NET summary page by occupation code.
    Uses disk cache to avoid repeated requests.
    Returns raw HTML string or None on failure.
    """
    if not HAS_SCRAPING:
        logger.warning("requests/bs4 not installed — skipping live scrape")
        return None

    cache_file = _cache_path(code)

    # Check cache
    if not force and cache_file.exists():
        age_hours = (time.time() - cache_file.stat().st_mtime) / 3600
        if age_hours < 168:  # 7 days
            logger.debug(f"  Cache hit for {code}")
            return cache_file.read_text(encoding="utf-8")

    # Live fetch
    url = BASE_URL.format(code=code)
    headers = {"User-Agent": USER_AGENT}

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            logger.info(f"  Fetching {url} (attempt {attempt})")
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()

            # Save to cache
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(resp.text, encoding="utf-8")

            time.sleep(REQUEST_DELAY)
            return resp.text

        except requests.RequestException as e:
            logger.warning(f"  Request failed: {e}")
            if attempt < MAX_RETRIES:
                time.sleep(REQUEST_DELAY * attempt)

    return None


# ──────────────────────────────────────────────
#  2. HTML Parsing / Skill Extraction
# ──────────────────────────────────────────────

def extract_skills(html: str) -> dict[str, list[str]]:
    """
    Parse an O*NET occupation summary page and extract:
      - skills (from the Skills section)
      - technology_skills (from the Technology Skills section)
      - knowledge (from the Knowledge section)

    Returns dict with those three keys.
    """
    if not HAS_SCRAPING:
        return {"skills": [], "technology_skills": [], "knowledge": []}

    soup = BeautifulSoup(html, "html.parser")
    result = {
        "skills": _extract_section_items(soup, "Skills"),
        "technology_skills": _extract_tech_skills(soup),
        "knowledge": _extract_section_items(soup, "Knowledge"),
    }
    return result


def _extract_section_items(soup: BeautifulSoup, section_name: str) -> list[str]:
    """
    Extract skill/knowledge names from a standard O*NET section.
    These sections use bold text (b, strong, or span.fw-bold) for item names
    followed by an em-dash and description.
    """
    items = []

    # Try to find the section heading
    heading = _find_section_heading(soup, section_name)
    if not heading:
        return items

    # Walk siblings until we hit the next section heading
    container = heading.find_next_sibling()
    while container:
        # Stop at next heading
        if container.name and container.name.startswith("h"):
            break

        # Find bold elements (skill names)
        bolds = container.find_all(["b", "strong"])
        if not bolds:
            bolds = container.find_all("span", class_="fw-bold")

        for bold in bolds:
            text = bold.get_text(strip=True)
            if text and len(text) > 1:
                # Split on em-dash if present
                name = text.split("—")[0].strip()
                name = name.split(" — ")[0].strip()
                if name:
                    items.append(name)

        # Also check list items
        for li in container.find_all("li"):
            text = li.get_text(" ", strip=True)
            if "—" in text:
                name = text.split("—")[0].strip()
                if name and len(name) > 2:
                    items.append(name)

        container = container.find_next_sibling()

    return items


def _extract_tech_skills(soup: BeautifulSoup) -> list[str]:
    """
    Extract technology/tool names from the Technology Skills section.
    Format: "Category — Tool1 ; Tool2 ; Tool3"
    We extract both categories and individual tool names.
    """
    items = []

    heading = _find_section_heading(soup, "Technology Skills")
    if not heading:
        return items

    container = heading.find_next_sibling()
    while container:
        if container.name and container.name.startswith("h"):
            break

        text = container.get_text(" ", strip=True)
        if "—" in text:
            # Category name
            category = text.split("—")[0].strip()
            if category:
                items.append(category)

            # Individual tools after the dash
            tools_part = text.split("—", 1)[1] if "—" in text else ""
            # Clean out "Hot Technology", "In Demand", "X more", "Related occupations"
            tools_part = re.sub(r"Hot Technology", "", tools_part)
            tools_part = re.sub(r"In Demand", "", tools_part)
            tools_part = re.sub(r"\d+ more", "", tools_part)
            tools_part = re.sub(r"Related occupations", "", tools_part)

            for tool in tools_part.split(";"):
                tool = tool.strip().rstrip(",").strip()
                if tool and len(tool) > 1:
                    items.append(tool)

        container = container.find_next_sibling()

    return items


def _find_section_heading(soup: BeautifulSoup, section_name: str):
    """Find a heading element that matches the section name."""
    for tag in ["h2", "h3", "h4", "h5", "h6"]:
        for heading in soup.find_all(tag):
            if section_name.lower() in heading.get_text(strip=True).lower():
                return heading

    # Try anchor-based lookup
    anchor_id = section_name.replace(" ", "")
    anchor = soup.find(id=anchor_id)
    if anchor:
        return anchor

    return None


# ──────────────────────────────────────────────
#  3. Skill Cleaning & Normalization
# ──────────────────────────────────────────────

def normalize_skill(raw: str) -> str | None:
    """
    Clean and normalize a single skill string.
    Returns None if the skill should be filtered out.
    """
    # Lowercase and strip
    skill = raw.lower().strip()

    # Remove parenthetical content like "(optional)" or "(basic)"
    skill = re.sub(r"\s*\([^)]*\)\s*", " ", skill).strip()

    # Remove trailing punctuation
    skill = skill.rstrip(".,;:")

    # Apply normalization map
    if skill in NORMALIZE_MAP:
        skill = NORMALIZE_MAP[skill]

    # Filter vague/generic skills
    if skill in VAGUE_SKILLS:
        return None

    # Filter too short or too long (40 chars max for actionable skills)
    if len(skill) < 2 or len(skill) > 40:
        return None

    # Filter items that are just numbers or punctuation
    if re.match(r"^[\d\W]+$", skill):
        return None

    # Filter O*NET noise: navigation artifacts
    if re.search(r"\d+ of all \d+", skill):
        return None
    if "displayed" in skill:
        return None

    # Filter generic O*NET software category headers
    # (e.g. "data base management system software", "electronic mail software")
    _noise_words = [
        "software —", "— adobe", "— atlassian", "— docker",
        "— dropbox", "— bootstrap", "— 3m", "— cisco",
        "— delphi", "— ibm", "— parentsquare", "— blink",
        "— bentley", "— acronis", "— apache",
    ]
    if any(nw in skill for nw in _noise_words):
        return None

    # Filter generic category headers ("XXX software" with > 2 words)
    if skill.endswith(" software") and len(skill.split()) > 2:
        return None

    # Filter specific O*NET category names that aren't actionable skills
    _onet_categories = {
        "spreadsheet software", "office suite software",
        "electronic mail software", "word processing software",
        "presentation software", "desktop publishing software",
        "desktop communications software", "operating system software",
        "computers and electronics", "communications and media",
        "engineering and technology", "administration and management",
        "education and training", "production and processing",
        "customer and personal service", "mechanical",
        "design", "administrative", "telecommunications",
        "internet browser software",
    }
    if skill in _onet_categories:
        return None

    return skill


def clean_skill_list(raw_skills: list[str]) -> list[str]:
    """Clean, normalize, deduplicate, and sort a list of skills."""
    cleaned = []
    seen = set()

    for raw in raw_skills:
        normalized = normalize_skill(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)

    return sorted(cleaned)


# ──────────────────────────────────────────────
#  4. Main Pipeline
# ──────────────────────────────────────────────

def build_role_skills(force: bool = False) -> dict:
    """
    Build the complete role_skills dataset.
    For each role: scrape O*NET → merge with curated → clean → output.
    """
    logger.info(f"Building role_skills for {len(ROLE_ONET_MAP)} roles")
    role_skills = {}
    scraped_count = 0
    fallback_count = 0

    for role_name, onet_code in ROLE_ONET_MAP.items():
        logger.info(f"Processing: {role_name} ({onet_code})")

        all_skills: list[str] = []

        # Layer 1: Live scrape
        html = fetch_onet_page(onet_code, force=force)
        if html:
            extracted = extract_skills(html)
            live_skills = (
                extracted.get("skills", [])
                + extracted.get("technology_skills", [])
                + extracted.get("knowledge", [])
            )
            if live_skills:
                all_skills.extend(live_skills)
                scraped_count += 1
                logger.info(f"  Scraped {len(live_skills)} raw skills from O*NET")

        # Layer 2: Curated fallback (always merge in)
        curated = CURATED_SKILLS.get(role_name, [])
        if curated:
            all_skills.extend(curated)
            if not html or not extracted.get("skills"):
                fallback_count += 1
                logger.info(f"  Using curated dataset ({len(curated)} skills)")

        # Layer 3: Clean & deduplicate
        final_skills = clean_skill_list(all_skills)

        if final_skills:
            role_skills[role_name] = {"skills": final_skills}
            logger.info(f"  Final: {len(final_skills)} unique skills")
        else:
            logger.warning(f"  No skills found for {role_name}")

    logger.info(
        f"\nSummary: {len(role_skills)} roles processed, "
        f"{scraped_count} scraped live, {fallback_count} used curated fallback"
    )
    return role_skills


def save_json(data: dict) -> None:
    """Save the role_skills data to data/role_skills.json."""
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info(f"Saved {len(data)} roles to {OUTPUT_FILE}")


# ──────────────────────────────────────────────
#  CLI Entry Point
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scrape O*NET skills and generate data/role_skills.json"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Ignore cache and re-scrape all pages"
    )
    parser.add_argument(
        "--curated-only", action="store_true",
        help="Skip live scraping, use only curated data (fast)"
    )
    args = parser.parse_args()

    if args.curated_only:
        logger.info("Curated-only mode: skipping live scraping")
        role_skills = {}
        for role_name, skills in CURATED_SKILLS.items():
            final = clean_skill_list(skills)
            if final:
                role_skills[role_name] = {"skills": final}
        save_json(role_skills)
    else:
        role_skills = build_role_skills(force=args.force)
        save_json(role_skills)

    # Print summary
    total_skills = sum(len(v["skills"]) for v in role_skills.values())
    print(f"\n{'='*50}")
    print(f"  role_skills.json generated successfully!")
    print(f"  Roles: {len(role_skills)}")
    print(f"  Total unique skills: {total_skills}")
    print(f"  Output: {OUTPUT_FILE}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
