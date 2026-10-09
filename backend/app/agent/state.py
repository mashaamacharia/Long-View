from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    run_id: str
    learner_id: str
    request: str
    timeline: dict[str, Any]
    patterns: list[dict[str, Any]]
    evidence: dict[str, Any]
    sufficient: bool
    loops: int
    review_id: int | None
    approval_id: str | None
    decision: str | None  # approved | rejected | more_evidence
    summary: str
