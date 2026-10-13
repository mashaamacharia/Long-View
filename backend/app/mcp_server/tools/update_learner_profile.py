"""update_learner_profile: the ONLY tool that writes to a learner's profile.

Refuses unless a teacher approved this exact pattern for this exact learner. The check is here, in
the server, so it holds no matter what the model, the prompt or the user asks for.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from app.db.models import Learner, LearnerPattern, ProfileChange
from app.db.session import SessionLocal
from app.mcp_server.analysis.conflicts import has_label_language
from app.mcp_server.approvals import ApprovalError, require_approval

MAX_SUMMARY = 600


def _err(msg: str) -> dict[str, Any]:
    return {"ok": False, "error": msg}


def update_learner_profile(learner_id: str, pattern_id: str, summary: str,
                           approval_id: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    """Record a teacher-approved finding in the learner's profile. Requires a valid approval_id."""
    with SessionLocal() as db:
        if db.get(Learner, learner_id) is None:
            return _err(f"Unknown learner_id: {learner_id}")
        pattern = db.get(LearnerPattern, pattern_id)
        if pattern is None or pattern.learner_id != learner_id:
            return _err(f"Pattern {pattern_id} does not exist for learner {learner_id}.")
        try:  # approval is checked before anything else, so a refusal reveals nothing about the content
            approval = require_approval(db, approval_id, learner_id, pattern_id)
        except ApprovalError as exc:
            return _err(str(exc))

        existing = db.scalars(select(ProfileChange).where(ProfileChange.approval_id == approval.id)).first()
        if existing is not None:  # replay of an already-applied approval: report it, never duplicate it
            return {"ok": True, "change_id": existing.id, "learner_id": learner_id, "pattern_id": pattern_id,
                    "approval_id": approval.id, "already_applied": True,
                    "message": "This approval was already applied; no duplicate entry was written."}

        summary = (summary or "").strip()[:MAX_SUMMARY]
        if not summary:
            return _err("A summary is required: one or two sentences describing the approved finding.")
        if has_label_language(summary):
            return _err("The summary contains characterising language (a trait or ability label). Describe the "
                        "measured evidence instead, then try again; the approval is still valid.")

        change = ProfileChange(learner_id=learner_id, pattern_id=pattern_id, approval_id=approval.id, summary=summary)
        db.add(change)
        db.commit()
        return {"ok": True, "change_id": change.id, "learner_id": learner_id, "pattern_id": pattern_id,
                "approval_id": approval.id, "already_applied": False,
                "message": "Profile updated with the teacher-approved finding."}
