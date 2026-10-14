"""flag_for_teacher_review: put a pattern in front of a teacher. Changes no learner data."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.models import AgentRun, Learner, LearnerPattern, TeacherReview
from app.db.session import SessionLocal

MAX_REASON = 600


def _err(msg: str) -> dict[str, Any]:
    return {"ok": False, "error": msg}


def flag_for_teacher_review(learner_id: str, pattern_id: str, reason: str, run_id: str | None = None) -> dict[str, Any]:
    """Create a pending teacher review for a pattern. Nothing is written to the learner profile."""
    reason = (reason or "").strip()[:MAX_REASON]
    if not reason:
        return _err("A reason is required: say in a sentence why this pattern needs a teacher's attention.")
    with SessionLocal() as db:
        if db.get(Learner, learner_id) is None:
            return _err(f"Unknown learner_id: {learner_id}")
        pat = db.get(LearnerPattern, pattern_id)
        if pat is None:
            return _err(f"Unknown pattern_id: {pattern_id}. Run detect_patterns first.")
        if pat.learner_id != learner_id:
            return _err(f"Pattern {pattern_id} belongs to a different learner.")
        if pat.kind == "insufficient" or pat.evidence_strength == "none":
            return _err("There is nothing to approve: this is an 'insufficient data' finding. Report it in the "
                        "summary with what additional evidence is needed instead of sending it for review.")
        if pat.status in ("approved", "rejected"):
            return _err(f"Pattern {pattern_id} was already {pat.status} by a teacher and is not re-proposed.")
        if run_id is not None and db.get(AgentRun, run_id) is None:
            return _err(f"Unknown run_id: {run_id}")

        pending = db.scalars(
            select(TeacherReview).where(TeacherReview.pattern_id == pattern_id, TeacherReview.status == "pending")
            .order_by(TeacherReview.id.desc())
        ).first()
        if pending is not None:
            return {"ok": True, "review_id": pending.id, "pattern_id": pattern_id, "learner_id": learner_id,
                    "status": "pending", "already_pending": True,
                    "message": "This pattern is already waiting for a teacher. No duplicate was created."}

        review = TeacherReview(pattern_id=pattern_id, learner_id=learner_id, run_id=run_id,
                               reason=reason, status="pending")
        db.add(review)
        pat.status = "in_review"
        db.commit()
        return {"ok": True, "review_id": review.id, "pattern_id": pattern_id, "learner_id": learner_id,
                "status": "pending", "already_pending": False,
                "message": "Sent to the teacher for review. No profile change is made until a teacher approves it."}
