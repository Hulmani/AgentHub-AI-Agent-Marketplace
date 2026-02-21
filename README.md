# AgentHub MVP (Agent-to-Agent Marketplace API)

## Architecture (MVP)
- `AgentHub API` (FastAPI): registry + discovery + proxy calling + reporting.
- `SQLite + SQLAlchemy`: stores `agents` and `call_logs`.
- `Proxy Flow`: `/agents/call` forwards payload to target agent, measures latency, logs outcome, updates reputation.
- `Security`: shared API key via `X-API-Key` header.
- `Rate limiting`: in-memory per API key (requests/window).
- `Demo agents`: 3 standalone FastAPI apps with `/run`.
- `PlannerAgent script`: registers demo agents, searches by skill, and calls them in sequence.

## Project Structure
```text
.
├── agenthub
│   ├── __init__.py
│   └── app
│       ├── __init__.py
│       ├── auth.py
│       ├── database.py
│       ├── main.py
│       ├── models.py
│       ├── rate_limit.py
│       ├── schemas.py
│       ├── services.py
│       └── routers
│           ├── __init__.py
│           └── agents.py
├── demo_agents
│   ├── keyword_extract_agent.py
│   ├── summarize_agent.py
│   └── translate_agent.py
├── planner_agent.py
└── requirements.txt
```

## Python Version
- Recommended: `Python 3.11`
- Minimum supported: `Python 3.10+`

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Environment Variables (optional)
```bash
export AGENTHUB_API_KEY="dev-secret-key"
export DATABASE_URL="sqlite:///./agenthub.db"
export RATE_LIMIT_MAX_REQUESTS="120"
export RATE_LIMIT_WINDOW_SECONDS="60"
```

## Start AgentHub
```bash
uvicorn agenthub.app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Run with uv (recommended)
```bash
PYTHONPATH=. uv run --python 3.11 --with-requirements requirements.txt uvicorn agenthub.app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Start Demo Agents (3 terminals)
```bash
uvicorn demo_agents.summarize_agent:app --host 0.0.0.0 --port 9001 --reload
uvicorn demo_agents.translate_agent:app --host 0.0.0.0 --port 9002 --reload
uvicorn demo_agents.keyword_extract_agent:app --host 0.0.0.0 --port 9003 --reload
```

## Run PlannerAgent
```bash
python planner_agent.py
```

## Run Tests with uv
```bash
PYTHONPATH=. uv run --python 3.11 --with-requirements requirements.txt --with pytest pytest tests/test_agents.py -q
```

## Core API Endpoints
- `POST /agents/register`: register an agent.
- `GET /agents/search`: query by `skill`, `max_price`, `min_score`, ranked by `reputation_score`, `price_per_call`, `avg_latency`.
- `POST /agents/call`: proxy call to target agent endpoint with timeout + logging + metric updates.
- `POST /agents/report`: explicit success/failure feedback.
- `DELETE /agents/{agent_id}`: delete an agent and its related call logs.

All `/agents/*` endpoints require:
```http
X-API-Key: dev-secret-key
```
