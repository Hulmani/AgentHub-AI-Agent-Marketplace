from . import models


def update_reputation(agent: models.Agent) -> None:
    if agent.total_calls <= 0:
        agent.reputation_score = 0.0
        return
    agent.reputation_score = agent.successful_calls / agent.total_calls


def apply_call_metrics(
    agent: models.Agent,
    success: bool,
    latency_ms: float | None = None,
    previous_latency_samples: int | None = None,
) -> None:
    previous_total = agent.total_calls
    agent.total_calls += 1
    if success:
        agent.successful_calls += 1
    else:
        agent.failed_calls += 1

    if latency_ms is not None:
        samples = previous_latency_samples if previous_latency_samples is not None else previous_total
        if samples <= 0:
            agent.avg_latency = latency_ms
        else:
            agent.avg_latency = ((agent.avg_latency * samples) + latency_ms) / (samples + 1)

    update_reputation(agent)


def log_call(
    agent_id: int,
    success: bool,
    latency_ms: float | None = None,
    error_message: str | None = None,
) -> models.CallLog:
    return models.CallLog(
        agent_id=agent_id,
        success=success,
        latency_ms=latency_ms,
        error_message=error_message,
    )
