from typing import Any

from pydantic import BaseModel, Field


class RegisterAgentRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    skills: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    price_per_call: float = Field(..., ge=0)
    endpoint: str = Field(..., min_length=1, max_length=500)
    max_latency_ms: int = Field(..., gt=0)


class AgentResponse(BaseModel):
    id: int
    name: str
    skills: list[str]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    endpoint: str
    price_per_call: float
    max_latency_ms: int
    total_calls: int
    successful_calls: int
    failed_calls: int
    avg_latency: float
    reputation_score: float

    model_config = {"from_attributes": True}


class CallAgentRequest(BaseModel):
    agent_id: int = Field(..., gt=0)
    payload: dict[str, Any] = Field(default_factory=dict)


class CallAgentResponse(BaseModel):
    agent_id: int
    success: bool
    latency_ms: float
    result: dict[str, Any] | None = None
    error: str | None = None


class ReportResultRequest(BaseModel):
    agent_id: int = Field(..., gt=0)
    success: bool

