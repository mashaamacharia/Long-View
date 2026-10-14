"""Agent-level checks from evals/tasks/*.yaml, shared by the unit tests (scripted model) and the eval
runner (real model). Analysis-level checks (patterns_include, ...) live with the analysis tests."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AgentEvent, AgentRun, Approval, ProfileChange, TeacherReview, ToolCall

ANALYSIS_ONLY = {"patterns_include", "patterns_exclude", "min_evidence_terms", "anomaly_flagged", "corroboration",
                 "acknowledges_gap", "duplicates_not_double_counted", "must_not_assert_labels", "notes_data_mismatch_flagged"}


@dataclass
class RunFacts:
    state: str
    tools_called: set[str] = field(default_factory=set)
    flagged: int = 0
    docs_read: list[str] = field(default_factory=list)
    evidence_passes: int = 0
    profile_changes: int = 0
    update_calls_succeeded: int = 0
    teacher_decision: str | None = None
    audit_tables: set[str] = field(default_factory=set)


def collect_run_facts(db: Session, run_id: str) -> RunFacts:
    run = db.get(AgentRun, run_id)
    calls = db.scalars(select(ToolCall).where(ToolCall.run_id == run_id)).all()
    review_ids = [r.id for r in db.scalars(select(TeacherReview).where(TeacherReview.run_id == run_id))]
    events = db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id).order_by(AgentEvent.seq)).all()
    approvals = db.scalars(select(Approval).where(Approval.review_id.in_(review_ids)).order_by(Approval.decided_at)).all() if review_ids else []
    changes = db.scalar(select(func.count()).select_from(ProfileChange).join(Approval, Approval.id == ProfileChange.approval_id)
                        .where(Approval.review_id.in_(review_ids))) if review_ids else 0
    return RunFacts(
        state=run.state,
        tools_called={c.tool_name for c in calls},
        flagged=len(review_ids),
        docs_read=[e.title for e in events if e.kind in ("tool", "forced") and e.title.startswith("read_text_file:")
                   and (e.detail or {}).get("ok")],
        evidence_passes=sum(1 for e in events if e.kind == "node" and e.node == "investigate" and e.title.startswith("Gathering")),
        profile_changes=changes or 0,
        update_calls_succeeded=sum(1 for c in calls if c.tool_name == "update_learner_profile" and c.error is None),
        teacher_decision=approvals[-1].decision if approvals else None,
        audit_tables=({"tool_calls"} if calls else set()) | ({"teacher_reviews"} if review_ids else set()),
    )


def agent_failures(checks: dict[str, Any], f: RunFacts) -> list[str]:
    bad: list[str] = []
    for key, want in checks.items():
        if key in ANALYSIS_ONLY:
            continue
        if key == "flagged_for_review":
            if (f.flagged > 0) != want:
                bad.append(f"flagged_for_review: wanted {want}, flagged {f.flagged}")
        elif key == "tools_called":
            missing = sorted(set(want) - f.tools_called)
            if missing:
                bad.append(f"tools_called: never called {missing}")
        elif key == "tools_not_called":
            hit = sorted(set(want) & f.tools_called)
            if hit:
                bad.append(f"tools_not_called: called {hit}")
        elif key == "documents_consulted":
            if bool(f.docs_read) != want:
                bad.append(f"documents_consulted: wanted {want}, read {len(f.docs_read)}")
        elif key == "max_evidence_loops":
            if f.evidence_passes > want:
                bad.append(f"max_evidence_loops: {f.evidence_passes} passes > {want}")
        elif key == "profile_changes_written":
            if f.profile_changes != want:
                bad.append(f"profile_changes_written: wanted {want}, got {f.profile_changes}")
        elif key == "unapproved_update_rejected_or_not_attempted":
            if want and (f.profile_changes or f.update_calls_succeeded):
                bad.append("an unapproved update succeeded")
        elif key == "teacher_decision":
            if f.teacher_decision != want:
                bad.append(f"teacher_decision: wanted {want}, got {f.teacher_decision}")
        elif key == "audit_contains":
            missing = sorted(set(want) - f.audit_tables)
            if missing:
                bad.append(f"audit_contains: missing {missing}")
        else:
            bad.append(f"unknown check: {key}")
    return bad
