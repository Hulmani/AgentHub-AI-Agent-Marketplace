import os
from typing import Any

import requests

AGENTHUB_URL = os.getenv("AGENTHUB_URL", "http://127.0.0.1:8000")
AGENTHUB_API_KEY = os.getenv("AGENTHUB_API_KEY", "dev-secret-key")
HEADERS = {"X-API-Key": AGENTHUB_API_KEY}


def register_agent(agent: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{AGENTHUB_URL}/agents/register", json=agent, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()


def search_agent(skill: str, max_price: float = 0.1, min_score: float = 0.0) -> list[dict[str, Any]]:
    params = {"skill": skill, "max_price": max_price, "min_score": min_score}
    response = requests.get(f"{AGENTHUB_URL}/agents/search", params=params, headers=HEADERS, timeout=10)
    response.raise_for_status()
    return response.json()


def call_agent(agent_id: int, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(
        f"{AGENTHUB_URL}/agents/call",
        json={"agent_id": agent_id, "payload": payload},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    print("Registering demo agents...")
    summarize = register_agent(
        {
            "name": "SummarizeAgent",
            "skills": ["summarize_text"],
            "input_schema": {"text": "string"},
            "output_schema": {"summary": "string"},
            "price_per_call": 0.001,
            "endpoint": "http://127.0.0.1:9001/run",
            "max_latency_ms": 500,
        }
    )
    translate = register_agent(
        {
            "name": "TranslateAgent",
            "skills": ["translate_text"],
            "input_schema": {"text": "string", "language": "string"},
            "output_schema": {"translation": "string"},
            "price_per_call": 0.002,
            "endpoint": "http://127.0.0.1:9002/run",
            "max_latency_ms": 500,
        }
    )
    keywords = register_agent(
        {
            "name": "KeywordExtractAgent",
            "skills": ["extract_keywords"],
            "input_schema": {"text": "string"},
            "output_schema": {"keywords": "list[string]"},
            "price_per_call": 0.0015,
            "endpoint": "http://127.0.0.1:9003/run",
            "max_latency_ms": 500,
        }
    )
    print("Registered:", summarize["id"], translate["id"], keywords["id"])

    input_text = "AgentHub lets AI agents discover each other, collaborate, and complete tasks through one API."

    print("Searching summarize agent...")
    summarize_candidates = search_agent("summarize_text", max_price=0.01, min_score=0.0)
    summarize_choice = summarize_candidates[0]
    summarize_result = call_agent(summarize_choice["id"], {"text": input_text})
    summary = summarize_result["result"]["summary"]
    print("Summary:", summary)

    print("Searching translate agent...")
    translate_candidates = search_agent("translate_text", max_price=0.01, min_score=0.0)
    translate_choice = translate_candidates[0]
    translate_result = call_agent(translate_choice["id"], {"text": summary, "language": "spanish"})
    translated = translate_result["result"]["translation"]
    print("Translation:", translated)

    print("Searching keyword extraction agent...")
    keyword_candidates = search_agent("extract_keywords", max_price=0.01, min_score=0.0)
    keyword_choice = keyword_candidates[0]
    keyword_result = call_agent(keyword_choice["id"], {"text": translated})
    print("Keywords:", keyword_result["result"]["keywords"])

    print("Planner workflow complete.")


if __name__ == "__main__":
    main()

