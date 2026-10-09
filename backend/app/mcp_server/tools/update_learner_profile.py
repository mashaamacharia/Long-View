from app.db.session import SessionLocal
from app.mcp_server.approvals import ApprovalError, require_approval


def update_learner_profile(learner_id: str, pattern_id: str, summary: str,
                           approval_id: str | None = None) -> dict:
    """ACTION TOOL. Only runs with a valid teacher approval (enforced here, not by the model)."""
    with SessionLocal() as db:
        try:
            require_approval(db, approval_id, pattern_id)
        except ApprovalError as exc:
            return {"ok": False, "error": str(exc)}
        # TODO: insert ProfileChange, mark pattern approved.
        return {"ok": True, "learner_id": learner_id, "pattern_id": pattern_id, "note": "not implemented"}
