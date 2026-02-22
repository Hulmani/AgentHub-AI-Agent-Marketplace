"""End-to-end API tests for AgentHub backend routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from agenthub.app import main as app_main
from agenthub.app.database import Base, get_db
from agenthub.app.models import Agent, CallLog
from agenthub.app.rate_limit import InMemoryRateLimiter


@pytest.fixture
def api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Use a test-only API key for all protected endpoints."""
    key = "test-api-key"
    monkeypatch.setenv("AGENTHUB_API_KEY", key)
    return key


@pytest.fixture
def auth_headers(api_key: str) -> dict[str, str]:
    """Shared auth headers used by most tests."""
    return {"X-API-Key": api_key}


@pytest.fixture
def sample_agent_payload() -> dict[str, Any]:
    """Baseline payload for registering agents."""
    return {
        "name": "SummarizeAgent",
        "skills": ["summarize_text"],
        "input_schema": {"text": "string"},
        "output_schema": {"summary": "string"},
        "price_per_call": 0.001,
        "endpoint": "http://127.0.0.1:9001/run",
        "max_latency_ms": 500,
    }


@pytest.fixture
def db_setup(tmp_path: Path) -> tuple[sessionmaker, Any]:
    """Create a fresh SQLite database per test to keep tests independent."""
    db_file = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_file}", connect_args={"check_same_thread": False}, future=True)
    TestingSessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)
    Base.metadata.create_all(bind=engine)
    try:
        yield TestingSessionLocal, engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def client(
    db_setup: tuple[sessionmaker, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    """Wire FastAPI dependency overrides to the isolated test database."""
    db_session_factory, test_engine = db_setup

    def override_get_db():
        db = db_session_factory()
        try:
            yield db
        finally:
            db.close()

    # Ensure startup table creation (if triggered) uses this test DB engine.
    monkeypatch.setattr(app_main, "engine", test_engine)

    # Reset global rate limiter state for each test.
    monkeypatch.setattr(
        "agenthub.app.rate_limit.rate_limiter",
        InMemoryRateLimiter(max_requests=1000, window_seconds=60),
    )

    app_main.app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app_main.app) as test_client:
            yield test_client
    finally:
        app_main.app.dependency_overrides.clear()


def register_agent(client: TestClient, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    """Helper for concise agent registration inside tests."""
    response = client.post("/api/v1/agents/register", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def test_health_endpoints_available(client: TestClient) -> None:
    """Both operational and versioned health checks should return 200."""
    operational = client.get("/health")
    versioned = client.get("/api/v1/health")

    assert operational.status_code == 200
    assert operational.json() == {"status": "ok"}
    assert versioned.status_code == 200
    assert versioned.json() == {"status": "ok"}


def test_register_agent_success(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_agent_payload: dict[str, Any],
) -> None:
    """Registering a valid agent should persist it with default metrics."""
    response = client.post("/api/v1/agents/register", headers=auth_headers, json=sample_agent_payload)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] > 0
    assert body["name"] == "SummarizeAgent"
    assert body["skills"] == ["summarize_text"]
    assert body["total_calls"] == 0
    assert body["successful_calls"] == 0
    assert body["failed_calls"] == 0
    assert body["avg_latency"] == 0.0
    assert body["reputation_score"] == 0.0


def test_register_agent_validation_error(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_agent_payload: dict[str, Any],
) -> None:
    """Missing required fields should return validation errors."""
    invalid_payload = dict(sample_agent_payload)
    invalid_payload.pop("endpoint")

    response = client.post("/api/v1/agents/register", headers=auth_headers, json=invalid_payload)
    assert response.status_code == 422


def test_search_agents_filters_and_ranking(
    client: TestClient,
    auth_headers: dict[str, str],
    db_setup: tuple[sessionmaker, Any],
    sample_agent_payload: dict[str, Any],
) -> None:
    """Search should apply filters and rank by score desc, then price asc, then latency asc."""
    payload_a = dict(sample_agent_payload)
    payload_a["name"] = "A"
    payload_a["price_per_call"] = 0.002
    a = register_agent(client, auth_headers, payload_a)

    payload_b = dict(sample_agent_payload)
    payload_b["name"] = "B"
    payload_b["price_per_call"] = 0.001
    b = register_agent(client, auth_headers, payload_b)

    payload_c = dict(sample_agent_payload)
    payload_c["name"] = "C"
    payload_c["skills"] = ["translate_text"]
    payload_c["price_per_call"] = 0.0005
    c = register_agent(client, auth_headers, payload_c)

    # Manually set metrics so ranking order is deterministic.
    db_session_factory, _ = db_setup
    with db_session_factory() as db:
        agent_a = db.get(Agent, a["id"])
        agent_b = db.get(Agent, b["id"])
        agent_c = db.get(Agent, c["id"])
        assert agent_a and agent_b and agent_c

        agent_a.total_calls = 10
        agent_a.successful_calls = 9
        agent_a.failed_calls = 1
        agent_a.reputation_score = 0.9
        agent_a.avg_latency = 250.0

        agent_b.total_calls = 10
        agent_b.successful_calls = 9
        agent_b.failed_calls = 1
        agent_b.reputation_score = 0.9
        agent_b.avg_latency = 300.0

        agent_c.total_calls = 10
        agent_c.successful_calls = 8
        agent_c.failed_calls = 2
        agent_c.reputation_score = 0.8
        agent_c.avg_latency = 100.0
        db.commit()

    response = client.get(
        "/api/v1/agents/search",
        headers=auth_headers,
        params={"skill": "summarize_text", "max_price": 0.01, "min_score": 0.8},
    )
    assert response.status_code == 200
    body = response.json()

    # A and B have same score; B should come first because lower price.
    assert [agent["name"] for agent in body] == ["B", "A"]


def test_call_agent_success_updates_metrics_and_logs(
    client: TestClient,
    auth_headers: dict[str, str],
    db_setup: tuple[sessionmaker, Any],
    sample_agent_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Proxy call success should return upstream output and update call statistics."""
    registered = register_agent(client, auth_headers, sample_agent_payload)

    async def fake_post(self, url: str, json: dict[str, Any]):  # noqa: ANN001
        assert url == sample_agent_payload["endpoint"]
        assert json == {"text": "hello world"}
        return httpx.Response(status_code=200, json={"summary": "hello"})

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    response = client.post(
        "/api/v1/agents/call",
        headers=auth_headers,
        json={"agent_id": registered["id"], "payload": {"text": "hello world"}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["result"] == {"summary": "hello"}
    assert body["latency_ms"] >= 0

    db_session_factory, _ = db_setup
    with db_session_factory() as db:
        agent = db.get(Agent, registered["id"])
        assert agent is not None
        assert agent.total_calls == 1
        assert agent.successful_calls == 1
        assert agent.failed_calls == 0
        assert agent.reputation_score == 1.0
        assert agent.avg_latency >= 0

        logs = db.scalars(select(CallLog).where(CallLog.agent_id == registered["id"])).all()
        assert len(logs) == 1
        assert logs[0].success is True


def test_call_agent_timeout_failure_updates_metrics(
    client: TestClient,
    auth_headers: dict[str, str],
    db_setup: tuple[sessionmaker, Any],
    sample_agent_payload: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Timeouts from downstream agents should return 504 and count as failed calls."""
    registered = register_agent(client, auth_headers, sample_agent_payload)

    async def fake_post(self, url: str, json: dict[str, Any]):  # noqa: ANN001
        raise httpx.TimeoutException("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)

    response = client.post(
        "/api/v1/agents/call",
        headers=auth_headers,
        json={"agent_id": registered["id"], "payload": {"text": "hello world"}},
    )
    assert response.status_code == 504
    assert response.json()["detail"] == "Agent call timed out."

    db_session_factory, _ = db_setup
    with db_session_factory() as db:
        agent = db.get(Agent, registered["id"])
        assert agent is not None
        assert agent.total_calls == 1
        assert agent.successful_calls == 0
        assert agent.failed_calls == 1
        assert agent.reputation_score == 0.0


def test_call_agent_not_found_returns_404(client: TestClient, auth_headers: dict[str, str]) -> None:
    """Calling an unknown agent id should return 404."""
    response = client.post(
        "/api/v1/agents/call",
        headers=auth_headers,
        json={"agent_id": 99999, "payload": {"text": "hello world"}},
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found."


def test_report_result_updates_reputation(
    client: TestClient,
    auth_headers: dict[str, str],
    sample_agent_payload: dict[str, Any],
) -> None:
    """Explicit reports should update total/success/failure counts and reputation ratio."""
    registered = register_agent(client, auth_headers, sample_agent_payload)

    r1 = client.post("/api/v1/agents/report", headers=auth_headers, json={"agent_id": registered["id"], "success": True})
    assert r1.status_code == 200
    r2 = client.post("/api/v1/agents/report", headers=auth_headers, json={"agent_id": registered["id"], "success": True})
    assert r2.status_code == 200
    r3 = client.post("/api/v1/agents/report", headers=auth_headers, json={"agent_id": registered["id"], "success": False})
    assert r3.status_code == 200

    final_body = r3.json()
    assert final_body["total_calls"] == 3
    assert final_body["successful_calls"] == 2
    assert final_body["failed_calls"] == 1
    assert final_body["reputation_score"] == pytest.approx(2 / 3, rel=1e-6)
    # Report endpoint does not include latency measurements.
    assert final_body["avg_latency"] == 0.0


def test_delete_agent_success_removes_agent_and_logs(
    client: TestClient,
    auth_headers: dict[str, str],
    db_setup: tuple[sessionmaker, Any],
    sample_agent_payload: dict[str, Any],
) -> None:
    """Deleting an agent should remove the agent record and its call logs."""
    registered = register_agent(client, auth_headers, sample_agent_payload)

    # Create one call log via report endpoint before deletion.
    report_response = client.post(
        "/api/v1/agents/report",
        headers=auth_headers,
        json={"agent_id": registered["id"], "success": True},
    )
    assert report_response.status_code == 200

    delete_response = client.delete(f"/api/v1/agents/{registered['id']}", headers=auth_headers)
    assert delete_response.status_code == 204
    assert delete_response.text == ""

    db_session_factory, _ = db_setup
    with db_session_factory() as db:
        agent = db.get(Agent, registered["id"])
        assert agent is None
        logs = db.scalars(select(CallLog).where(CallLog.agent_id == registered["id"])).all()
        assert logs == []


def test_delete_agent_not_found_returns_404(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    """Deleting a missing agent id should return 404."""
    response = client.delete("/api/v1/agents/999999", headers=auth_headers)
    assert response.status_code == 404
    assert response.json()["detail"] == "Agent not found."


def test_authentication_missing_api_key_denied(
    client: TestClient,
    sample_agent_payload: dict[str, Any],
) -> None:
    """Protected endpoints should reject requests without API key."""
    response = client.post("/api/v1/agents/register", json=sample_agent_payload)
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key."


def test_authentication_invalid_api_key_denied(
    client: TestClient,
    sample_agent_payload: dict[str, Any],
) -> None:
    """Protected endpoints should reject incorrect API keys."""
    response = client.post(
        "/api/v1/agents/register",
        headers={"X-API-Key": "wrong-key"},
        json=sample_agent_payload,
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key."


def test_rate_limiting_returns_429(
    client: TestClient,
    auth_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When request count exceeds limit in window, endpoint should return HTTP 429."""
    monkeypatch.setattr(
        "agenthub.app.rate_limit.rate_limiter",
        InMemoryRateLimiter(max_requests=2, window_seconds=60),
    )

    # First two requests are within the allowed quota.
    r1 = client.get("/api/v1/agents/search", headers=auth_headers)
    r2 = client.get("/api/v1/agents/search", headers=auth_headers)
    assert r1.status_code == 200
    assert r2.status_code == 200

    # Third request should hit the limiter.
    r3 = client.get("/api/v1/agents/search", headers=auth_headers)
    assert r3.status_code == 429
    assert r3.json()["detail"] == "Rate limit exceeded."
    assert "Retry-After" in r3.headers
