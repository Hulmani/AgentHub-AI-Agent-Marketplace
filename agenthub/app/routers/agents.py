from time import perf_counter

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Agent, CallLog
from ..rate_limit import enforce_rate_limit
from ..schemas import (
    AgentResponse,
    CallAgentRequest,
    CallAgentResponse,
    RegisterAgentRequest,
    ReportResultRequest,
)
from ..services import apply_call_metrics, log_call

router = APIRouter(
    prefix="/agents",
    tags=["agents"],
    dependencies=[Depends(enforce_rate_limit)],
)


@router.post("/register", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def register_agent(payload: RegisterAgentRequest, db: Session = Depends(get_db)) -> Agent:
    agent = Agent(
        name=payload.name,
        skills=payload.skills,
        input_schema=payload.input_schema,
        output_schema=payload.output_schema,
        endpoint=payload.endpoint,
        price_per_call=payload.price_per_call,
        max_latency_ms=payload.max_latency_ms,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


@router.get("/search", response_model=list[AgentResponse])
def search_agents(
    skill: str | None = Query(default=None),
    max_price: float | None = Query(default=None, ge=0),
    min_score: float | None = Query(default=None, ge=0, le=1),
    db: Session = Depends(get_db),
) -> list[Agent]:
    agents = list(db.execute(select(Agent)).scalars().all())

    if skill:
        agents = [agent for agent in agents if skill in (agent.skills or [])]
    if max_price is not None:
        agents = [agent for agent in agents if agent.price_per_call <= max_price]
    if min_score is not None:
        agents = [agent for agent in agents if agent.reputation_score >= min_score]

    def latency_sort_value(agent: Agent) -> float:
        return agent.avg_latency if agent.avg_latency > 0 else float("inf")

    agents.sort(
        key=lambda agent: (
            -agent.reputation_score,
            agent.price_per_call,
            latency_sort_value(agent),
        )
    )
    return agents


@router.post("/call", response_model=CallAgentResponse)
async def call_agent(payload: CallAgentRequest, db: Session = Depends(get_db)) -> CallAgentResponse:
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

    timeout_seconds = min(max(agent.max_latency_ms / 1000.0, 0.05), 30.0)
    started = perf_counter()
    latency_sample_count = db.scalar(
        select(func.count()).select_from(CallLog).where(CallLog.agent_id == agent.id, CallLog.latency_ms.is_not(None))
    ) or 0

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            upstream_response = await client.post(agent.endpoint, json=payload.payload)
        latency_ms = (perf_counter() - started) * 1000

        if upstream_response.status_code >= 400:
            error_message = f"Agent returned HTTP {upstream_response.status_code}."
            apply_call_metrics(
                agent,
                success=False,
                latency_ms=latency_ms,
                previous_latency_samples=latency_sample_count,
            )
            db.add(log_call(agent.id, success=False, latency_ms=latency_ms, error_message=error_message))
            db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error_message)

        try:
            result = upstream_response.json()
        except ValueError:
            error_message = "Agent returned a non-JSON response."
            apply_call_metrics(
                agent,
                success=False,
                latency_ms=latency_ms,
                previous_latency_samples=latency_sample_count,
            )
            db.add(log_call(agent.id, success=False, latency_ms=latency_ms, error_message=error_message))
            db.commit()
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error_message)

        apply_call_metrics(
            agent,
            success=True,
            latency_ms=latency_ms,
            previous_latency_samples=latency_sample_count,
        )
        db.add(log_call(agent.id, success=True, latency_ms=latency_ms))
        db.commit()
        return CallAgentResponse(
            agent_id=agent.id,
            success=True,
            latency_ms=latency_ms,
            result=result,
        )
    except httpx.TimeoutException:
        latency_ms = (perf_counter() - started) * 1000
        error_message = "Agent call timed out."
        apply_call_metrics(
            agent,
            success=False,
            latency_ms=latency_ms,
            previous_latency_samples=latency_sample_count,
        )
        db.add(log_call(agent.id, success=False, latency_ms=latency_ms, error_message=error_message))
        db.commit()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail=error_message)
    except httpx.RequestError:
        latency_ms = (perf_counter() - started) * 1000
        error_message = "Failed to reach agent endpoint."
        apply_call_metrics(
            agent,
            success=False,
            latency_ms=latency_ms,
            previous_latency_samples=latency_sample_count,
        )
        db.add(log_call(agent.id, success=False, latency_ms=latency_ms, error_message=error_message))
        db.commit()
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=error_message)


@router.post("/report", response_model=AgentResponse)
def report_result(payload: ReportResultRequest, db: Session = Depends(get_db)) -> Agent:
    agent = db.get(Agent, payload.agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found.")

    apply_call_metrics(agent, success=payload.success, latency_ms=None)
    db.add(log_call(agent.id, success=payload.success, latency_ms=None, error_message=None))
    db.commit()
    db.refresh(agent)
    return agent
