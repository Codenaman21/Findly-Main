# UNMAPPED — Skill-to-Opportunity Mapping Engine

A conversational AI backend that maps informal skills to real-world opportunities using a tiered search system.

## Architecture

```
app.py                          # Flask entry point (app factory)
├── routes/
│   ├── chat.py                 # POST /api/chat — Full conversational pipeline
│   └── opportunity.py          # POST /api/opportunities + GET per-tier endpoints
├── services/
│   ├── llm/
│   │   ├── llm_client.py       # Ollama (Qwen 2.5) client with health check
│   │   └── prompts.py          # Strict-JSON prompt templates
│   ├── core/
│   │   ├── skill_extractor.py  # LLM + keyword fallback extraction
│   │   ├── intent_detector.py  # Intent classification (5 categories)
│   │   └── isco_mapper.py      # Skill → ISCO occupation code mapping
│   └── opportunity_engine/
│       ├── job_search.py       # Tier 1: Indeed scraping
│       ├── freelance_search.py # Tier 2: Curated platform suggestions
│       ├── walkin_search.py    # Tier 3: Local walk-in businesses
│       └── aggregator.py       # Tiered priority orchestrator
├── data/
│   ├── isco_mapping.json       # 65+ skill → ISCO code mappings
│   ├── freelance_suggestions.json
│   └── walkin_businesses.json
├── utils/
│   └── helpers.py
└── db/
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Ensure Ollama is running with Qwen model
ollama run qwen2.5:1.5b

# 3. Start the server
python app.py
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API info & available endpoints |
| GET | `/api/health` | Health check (Ollama status) |
| POST | `/api/chat` | Full conversational pipeline |
| POST | `/api/opportunities` | Direct opportunity search |
| GET | `/api/opportunities/jobs?skill=X&location=Y` | Job search only |
| GET | `/api/opportunities/freelance?skill=X` | Freelance suggestions only |
| GET | `/api/opportunities/walkin?skill=X` | Walk-in businesses only |

## Example Chat Request

```bash
curl -X POST http://localhost:5000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I know Python and want work in Bangalore"}'
```

## Design Principles

- **No paid APIs** — Uses Ollama locally, scraping for jobs
- **Never crashes** — Every component has try/except + fallback
- **Deterministic decisions** — LLM is only for extraction & formatting, all logic is Python
- **Tiered reliability** — Jobs → Freelance → Walk-in (always has a result)
