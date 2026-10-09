from datetime import date

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Record(Base):
    """One measurable data point: quiz, assignment, project, attendance, participation.

    `kind` distinguishes them; `score` is nullable on purpose (missing scores are realistic).
    """

    __tablename__ = "records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), index=True)
    term: Mapped[str] = mapped_column(String(8), index=True)  # "2024-T2"
    kind: Mapped[str] = mapped_column(String(20))  # quiz|assignment|project|attendance|participation
    subject: Mapped[str] = mapped_column(String(40))
    skill: Mapped[str | None] = mapped_column(String(60), nullable=True)  # e.g. "reading_comprehension"
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    recorded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    submitted_late: Mapped[bool] = mapped_column(default=False)
    source: Mapped[str | None] = mapped_column(String(80), nullable=True)  # for traceability
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class Observation(Base):
    __tablename__ = "teacher_observations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    learner_id: Mapped[str] = mapped_column(ForeignKey("learners.id"), index=True)
    term: Mapped[str] = mapped_column(String(8), index=True)
    teacher_id: Mapped[str] = mapped_column(String(32))
    subject: Mapped[str | None] = mapped_column(String(40), nullable=True)
    skill: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sentiment: Mapped[str | None] = mapped_column(String(12), nullable=True)  # strong|neutral|concern
    text: Mapped[str] = mapped_column(Text)
    recorded_on: Mapped[date | None] = mapped_column(Date, nullable=True)
