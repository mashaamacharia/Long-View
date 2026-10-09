from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # "RUN-001"
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), index=True)
    request: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(24), default="running")
    llm_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ToolCall(Base):
    __tablename__ = "tool_calls"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), index=True, nullable=True)
    tool_name: Mapped[str] = mapped_column(String(60))
    tool_input: Mapped[dict] = mapped_column(JSON)
    tool_output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, default=False)
    called_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeacherReview(Base):
    __tablename__ = "teacher_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(ForeignKey("learner_patterns.id"), index=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")  # pending|approved|rejected|more_evidence
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # "APP-001"
    review_id: Mapped[int] = mapped_column(ForeignKey("teacher_reviews.id"))
    teacher_id: Mapped[str] = mapped_column(String(32))
    decision: Mapped[str] = mapped_column(String(16))  # approved|rejected|more_evidence
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
