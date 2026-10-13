from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DecisionIn(BaseModel):
    """A teacher's decision on a pending review. (Demo has no login: the dashboard supplies teacher_id.)"""
    model_config = ConfigDict(extra="forbid")

    teacher_id: str = Field(min_length=1, max_length=32)
    decision: Literal["approved", "rejected", "more_evidence"]
    comment: str | None = Field(default=None, max_length=500)
