from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecordIn(BaseModel):
    """A teacher-entered data point. kind mirrors the seeded data; score may be omitted (missing scores are realistic)."""
    model_config = ConfigDict(extra="forbid")

    term: str = Field(min_length=4, max_length=8, pattern=r"^\d{4}-T[1-3]$")  # "2024-T2"
    kind: Literal["quiz", "assignment", "project", "attendance"]
    subject: str = Field(min_length=1, max_length=40)
    skill: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, max_length=200)
    score: float | None = Field(default=None, ge=0, le=100)
    recorded_on: date | None = None
    notes: str | None = Field(default=None, max_length=2000)
