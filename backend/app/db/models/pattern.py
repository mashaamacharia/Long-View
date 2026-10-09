from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LearnerPattern(Base):
    """A candidate finding. Never a label; always tied to evidence."""

    __tablename__ = "learner_patterns"

    id: Mapped[str] = mapped_column(String(24), primary_key=True)  # "PATTERN-0092"
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))  # strength|decline|conflict|insufficient
    skill: Mapped[str | None] = mapped_column(String(60), nullable=True)
    statement: Mapped[str] = mapped_column(Text)
    evidence_strength: Mapped[str] = mapped_column(String(10))  # high|medium|low
    n_observations: Mapped[int] = mapped_column(Integer, default=0)
    n_terms: Mapped[int] = mapped_column(Integer, default=0)
    n_sources: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="proposed")  # proposed|in_review|approved|rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern_id: Mapped[str] = mapped_column(ForeignKey("learner_patterns.id"), index=True)
    record_id: Mapped[int | None] = mapped_column(ForeignKey("records.id"), nullable=True)
    observation_id: Mapped[int | None] = mapped_column(ForeignKey("teacher_observations.id"), nullable=True)
    document_ref: Mapped[str | None] = mapped_column(String(300), nullable=True)  # external MCP file
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProfileChange(Base):
    """Applied only after teacher approval."""

    __tablename__ = "profile_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), index=True)
    pattern_id: Mapped[str] = mapped_column(ForeignKey("learner_patterns.id"))
    approval_id: Mapped[str] = mapped_column(String(24))
    summary: Mapped[str] = mapped_column(Text)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
