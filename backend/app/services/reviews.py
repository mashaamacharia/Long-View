"""Teacher review workflow: list, inspect, decide. Decisions mint the approvals that unlock the gate."""
from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Approval, Learner, LearnerPattern, ProfileChange, TeacherReview
from app.services.evidence import build_evidence

Decision = Literal["approved", "rejected", "more_evidence"]
DECISIONS = ("approved", "rejected", "more_evidence")
STATUS_FILTERS = ("pending", "approved", "rejected", "more_evidence", "all")


class ReviewError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def _iso(dt) -> str | None:
    return dt.isoformat() if dt is not None else None


def _pattern_dict(p: LearnerPattern) -> dict[str, Any]:
    return {"pattern_id": p.id, "kind": p.kind, "subtype": (p.detail or {}).get("subtype"), "subject": p.subject,
            "skill": p.skill, "statement": p.statement, "evidence_strength": p.evidence_strength,
            "n_terms": p.n_terms, "status": p.status}


def list_reviews(db: Session, status: str = "pending") -> list[dict[str, Any]]:
    if status not in STATUS_FILTERS:
        raise ReviewError(f"status must be one of {', '.join(STATUS_FILTERS)}", 422)
    q = (select(TeacherReview, LearnerPattern, Learner)
         .join(LearnerPattern, LearnerPattern.id == TeacherReview.pattern_id)
         .join(Learner, Learner.id == TeacherReview.learner_id)
         .order_by(TeacherReview.id))
    if status != "all":
        q = q.where(TeacherReview.status == status)
    return [{"review_id": r.id, "status": r.status, "reason": r.reason, "created_at": _iso(r.created_at),
             "learner": {"id": l.id, "full_name": l.full_name}, "pattern": _pattern_dict(p)}
            for r, p, l in db.execute(q).all()]


def review_detail(db: Session, review_id: int) -> dict[str, Any]:
    review = db.get(TeacherReview, review_id)
    if review is None:
        raise ReviewError(f"Review {review_id} not found", 404)
    learner = db.get(Learner, review.learner_id)
    # The teacher sees everything: full evidence, original notes (not redacted), no sampling.
    ev = build_evidence(db, review.pattern_id, max_records=500, max_observations=100, max_attendance=100,
                        redact_labels=False)
    history = db.scalars(select(Approval).where(Approval.review_id == review_id).order_by(Approval.decided_at)).all()
    return {
        "review_id": review.id, "status": review.status, "reason": review.reason, "run_id": review.run_id,
        "created_at": _iso(review.created_at),
        "learner": {"id": learner.id, "full_name": learner.full_name, "grade_level": learner.grade_level},
        "pattern": ev["pattern"], "evidence": {k: v for k, v in ev.items() if k not in ("ok", "pattern")},
        "decisions": [{"approval_id": a.id, "teacher_id": a.teacher_id, "decision": a.decision,
                       "comment": a.comment, "decided_at": _iso(a.decided_at)} for a in history],
    }


def decide(db: Session, review_id: int, teacher_id: str, decision: str, comment: str | None = None) -> dict[str, Any]:
    if decision not in DECISIONS:
        raise ReviewError(f"decision must be one of {', '.join(DECISIONS)}", 422)
    teacher_id = (teacher_id or "").strip()
    if not teacher_id:
        raise ReviewError("teacher_id is required", 422)
    review = db.scalars(select(TeacherReview).where(TeacherReview.id == review_id).with_for_update()).first()
    if review is None:
        raise ReviewError(f"Review {review_id} not found", 404)
    if review.status != "pending":
        raise ReviewError(f"Review {review_id} is already '{review.status}'; a decision cannot be changed or repeated.", 409)
    pattern = db.get(LearnerPattern, review.pattern_id)

    approval = Approval(id="APP-" + uuid.uuid4().hex[:8].upper(), review_id=review.id, teacher_id=teacher_id,
                        decision=decision, comment=(comment or "").strip()[:500] or None)
    db.add(approval)
    review.status = decision
    # approved: unlocks the gate. rejected: closed for good. more_evidence: back to 'proposed' so a
    # fresh detect_patterns run can refresh the evidence before it is flagged again.
    pattern.status = {"approved": "approved", "rejected": "rejected", "more_evidence": "proposed"}[decision]
    db.commit()
    return {"approval_id": approval.id, "review_id": review.id, "decision": decision,
            "pattern_id": pattern.id, "pattern_status": pattern.status}


def profile_entries(db: Session, learner_id: str) -> list[dict[str, Any]]:
    if db.get(Learner, learner_id) is None:
        raise ReviewError(f"Learner {learner_id} not found", 404)
    q = (select(ProfileChange, LearnerPattern)
         .join(LearnerPattern, LearnerPattern.id == ProfileChange.pattern_id)
         .where(ProfileChange.learner_id == learner_id).order_by(ProfileChange.id))
    return [{"change_id": c.id, "applied_at": _iso(c.applied_at), "summary": c.summary, "approval_id": c.approval_id,
             "pattern": _pattern_dict(p)} for c, p in db.execute(q).all()]
