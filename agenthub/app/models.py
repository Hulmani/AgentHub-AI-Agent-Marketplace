from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Agent(Base):
    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    skills: Mapped[list] = mapped_column(JSON, nullable=False)
    input_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    output_schema: Mapped[dict] = mapped_column(JSON, nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    price_per_call: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    max_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    total_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    successful_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_latency: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    reputation_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

    call_logs: Mapped[list["CallLog"]] = relationship(back_populates="agent", cascade="all, delete-orphan")


class CallLog(Base):
    __tablename__ = "call_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    agent_id: Mapped[int] = mapped_column(Integer, ForeignKey("agents.id"), index=True, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True, nullable=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    agent: Mapped[Agent] = relationship(back_populates="call_logs")

