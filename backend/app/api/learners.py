from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Learner
from app.db.session import get_db
from app.services import reviews as reviews_svc

router = APIRouter(prefix="/learners", tags=["learners"])


@router.get("")
def list_learners(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Learner).order_by(Learner.id)).all()
    return [{"id": r.id, "full_name": r.full_name, "grade_level": r.grade_level} for r in rows]


@router.get("/{learner_id}")
def get_learner(learner_id: str, db: Session = Depends(get_db)) -> dict:
    learner = db.get(Learner, learner_id)
    if not learner:
        raise HTTPException(404, "Learner not found")
    return {"id": learner.id, "full_name": learner.full_name, "grade_level": learner.grade_level}


@router.get("/{learner_id}/profile")
def get_profile(learner_id: str, db: Session = Depends(get_db)) -> list[dict]:
    """Teacher-approved findings written to the learner's profile. Empty until a teacher approves something."""
    try:
        return reviews_svc.profile_entries(db, learner_id)
    except reviews_svc.ReviewError as exc:
        raise HTTPException(exc.status, str(exc))
