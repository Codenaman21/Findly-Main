"""
Prompt Templates — All prompts used for LLM interactions.
Every prompt enforces STRICT JSON output for reliable parsing.
"""


def extract_skills_prompt(user_input: str) -> str:
    """
    Prompt to extract skills, experience level, and preferred location
    from a user's natural language message.
    """
    return f"""You are a skill extraction engine. Analyze the user's message and extract structured information.

RULES:
- Extract ALL mentioned skills (technical, soft, trade, creative)
- Detect experience level from context clues
- Extract location if mentioned, otherwise use "not specified"
- Return ONLY valid JSON, no other text

OUTPUT FORMAT (strict JSON):
{{
  "skills": ["skill1", "skill2"],
  "experience_level": "beginner|intermediate|advanced",
  "location": "city or not specified",
  "raw_summary": "one line summary of what the user is looking for"
}}

USER MESSAGE: {user_input}

JSON RESPONSE:"""


def intent_prompt(user_input: str) -> str:
    """
    Prompt to classify the user's intent into one of the predefined categories.
    """
    return f"""You are an intent classifier. Classify the user's message into exactly ONE category.

CATEGORIES:
- "opportunity" → User is looking for jobs, gigs, freelance work, or earning opportunities
- "learning" → User wants to learn, upskill, take courses, or improve
- "risk" → User is asking about risks, challenges, or market conditions
- "startup" → User wants to start a business, become self-employed, or entrepreneurship
- "unknown" → Cannot determine intent clearly

RULES:
- Return ONLY valid JSON
- Choose the MOST likely single category
- When in doubt, default to "opportunity"

USER MESSAGE: {user_input}

OUTPUT FORMAT (strict JSON):
{{
  "intent": "opportunity",
  "confidence": 0.85
}}

JSON RESPONSE:"""


def response_prompt(user_input: str, results: dict) -> str:
    return f"""
You are a formatting engine. Convert structured data into a short response.

RULES:
- DO NOT think creatively
- DO NOT add new information
- ONLY use provided data
- Keep sentences short
- Maximum 120 words
- Use this structure EXACTLY:

1. Jobs (list 2 items)
2. Freelance (list 2 ideas)
3. Walk-in (list 2 places)

DATA:
{results}

OUTPUT:
"""