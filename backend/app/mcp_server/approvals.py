"""Server-side approval gate. The model cannot bypass this.

An approval unlocks exactly one thing: writing the pattern its review was about, for the learner
that review was about, after a teacher said 'approved'. Rejections and 'more evidence' decisions
are recorded as approvals rows too, but never unlock anything.
"""
from sqlalchemy.orm import Session

from app.db.models import Approval, LearnerPattern, TeacherReview


class ApprovalError(Exception):
    pass


def require_approval(db: Session, approval_id: str | None, learner_id: str, pattern_id: str) -> Approval:
    if not approval_id:
        raise ApprovalError("update_learner_profile requires a teacher approval_id. Send the finding to the "
                            "teacher with flag_for_teacher_review and wait for their decision.")
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise ApprovalError(f"Unknown approval_id: {approval_id}")
    if approval.decision != "approved":
        raise ApprovalError(f"Approval {approval_id} is '{approval.decision}', not 'approved'. Nothing is written.")
    review = db.get(TeacherReview, approval.review_id)
    if review is None:
        raise ApprovalError(f"Approval {approval_id} has no matching review.")
    if review.pattern_id != pattern_id:
        raise ApprovalError(f"Approval {approval_id} was granted for a different pattern.")
    if review.learner_id != learner_id:
        raise ApprovalError(f"Approval {approval_id} was granted for a different learner.")
    pattern = db.get(LearnerPattern, pattern_id)
    if pattern is None or pattern.status != "approved":
        raise ApprovalError(f"Pattern {pattern_id} is not in the approved state.")
    return approval
