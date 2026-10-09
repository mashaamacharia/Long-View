from sqlalchemy import select

from app.db.models import Observation, Record
from app.db.session import SessionLocal


def get_learner_timeline(learner_id: str, subject: str | None = None) -> dict:
    """Return a compact, term-ordered timeline for one learner (records + teacher observations)."""
    with SessionLocal() as db:
        q = select(Record).where(Record.learner_id == learner_id).order_by(Record.term, Record.recorded_on)
        if subject:
            q = q.where(Record.subject == subject)
        records = db.scalars(q).all()
        obs = db.scalars(
            select(Observation).where(Observation.learner_id == learner_id).order_by(Observation.term)
        ).all()
    return {
        "learner_id": learner_id,
        "records": [
            {"id": r.id, "term": r.term, "kind": r.kind, "subject": r.subject, "skill": r.skill,
             "score": r.score, "max_score": r.max_score, "source": r.source}
            for r in records
        ],
        "observations": [
            {"id": o.id, "term": o.term, "subject": o.subject, "skill": o.skill,
             "sentiment": o.sentiment, "text": o.text}
            for o in obs
        ],
    }
