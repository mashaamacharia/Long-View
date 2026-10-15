from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Learner, Observation, Record
from app.db.session import get_db
from app.schemas.records import RecordIn
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


def _record_dict(r: Record) -> dict:
    return {"id": r.id, "term": r.term, "kind": r.kind, "subject": r.subject, "skill": r.skill,
            "title": r.title, "score": r.score, "max_score": r.max_score,
            "recorded_on": r.recorded_on.isoformat() if r.recorded_on else None,
            "submitted_late": r.submitted_late, "notes": r.notes}


def _observation_dict(o: Observation) -> dict:
    return {"id": o.id, "term": o.term, "subject": o.subject, "skill": o.skill, "sentiment": o.sentiment,
            "text": o.text, "teacher_id": o.teacher_id,
            "recorded_on": o.recorded_on.isoformat() if o.recorded_on else None}


@router.get("/{learner_id}/records")
def get_records(learner_id: str, db: Session = Depends(get_db)) -> dict:
    """Every record and teacher observation for charts and the subject breakdown."""
    if db.get(Learner, learner_id) is None:
        raise HTTPException(404, "Learner not found")
    records = db.scalars(select(Record).where(Record.learner_id == learner_id).order_by(Record.term, Record.recorded_on)).all()
    observations = db.scalars(select(Observation).where(Observation.learner_id == learner_id).order_by(Observation.term, Observation.recorded_on)).all()
    return {"records": [_record_dict(r) for r in records], "observations": [_observation_dict(o) for o in observations]}


@router.post("/{learner_id}/records", status_code=201)
def create_record(learner_id: str, body: RecordIn, db: Session = Depends(get_db)) -> dict:
    """Add a teacher-entered assessment/observation data point."""
    if db.get(Learner, learner_id) is None:
        raise HTTPException(404, "Learner not found")
    record = Record(learner_id=learner_id, term=body.term, kind=body.kind, subject=body.subject,
                    skill=(body.skill or "").strip() or None, title=(body.title or "").strip() or None,
                    score=body.score, recorded_on=body.recorded_on, notes=(body.notes or "").strip() or None,
                    source="teacher-entry")
    db.add(record)
    db.commit()
    db.refresh(record)
    return _record_dict(record)
