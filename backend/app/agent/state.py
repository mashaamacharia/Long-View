from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    """Everything here must stay JSON-like: it is checkpointed so a run can pause for a teacher and resume."""
    run_id: str
    learner_id: str
    learner_name: str
    request: str
    subject: str | None
    timeline: dict[str, Any]
    patterns: list[dict[str, Any]]
    checked: list[dict[str, Any]]
    data_quality: dict[str, Any]
    gathered: dict[str, Any]          # evidence, docs_listed, doc_files, docs, docs_failed
    candidates: list[str]
    reviews: list[dict[str, Any]]     # this round's reviews: {review_id, pattern_id}
    pending_decisions: list[dict[str, Any]]
    decisions: list[dict[str, Any]]   # cumulative across rounds, each with its review_id
    applied: list[dict[str, Any]]
    followups: list[str]
    pending_followup: str | None
    refresh: bool
    loops: int
    rounds: int
    llm_ok: bool
    llm_calls: int
    llm_seconds: float
    fallbacks: list[str]
    summary: str
    result: dict[str, Any]
