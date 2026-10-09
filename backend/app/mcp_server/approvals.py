"""Server-side approval gate. The model cannot bypass this."""
from sqlalchemy.orm import Session

from app.db.models import Approval


class ApprovalError(Exception):
    pass


def require_approval(db: Session, approval_id: str | None, pattern_id: str) -> Approval:
    if not approval_id:
        raise ApprovalError("update_learner_profile requires a teacher approval_id.")
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise ApprovalError(f"Unknown approval_id: {approval_id}")
    if approval.decision != "approved":
        raise ApprovalError(f"Approval {approval_id} is '{approval.decision}', not 'approved'.")
    # TODO: also verify the approval's review belongs to this pattern_id.
    return approval
