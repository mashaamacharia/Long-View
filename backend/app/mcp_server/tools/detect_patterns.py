"""detect_patterns: deterministic, evidence-backed candidate patterns for one learner.

Reads the learner's records and teacher observations, runs the analysis engine (no LLM), stores
each pattern with its evidence so get_evidence / flag_for_teacher_review can refer to it by id, and
returns a COMPACT summary sized for a small model's context window.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models import Evidence, Learner, LearnerPattern, Observation, Record
from app.db.session import SessionLocal
from app.mcp_server.analysis.engine import analyse

_REC = ("id", "learner_id", "term", "kind", "subject", "skill", "title", "score", "max_score", "submitted_late", "source")
_OBS = ("id", "learner_id", "term", "teacher_id", "subject", "skill", "sentiment", "text")


def _load(db: Session, learner_id: str) -> tuple[list[dict], list[dict]]:
    recs = db.scalars(select(Record).where(Record.learner_id == learner_id).order_by(Record.id)).all()
    obs = db.scalars(select(Observation).where(Observation.learner_id == learner_id).order_by(Observation.id)).all()
    return ([{k: getattr(r, k) for k in _REC} for r in recs], [{k: getattr(o, k) for k in _OBS} for o in obs])


def _persist(db: Session, learner_id: str, patterns: list[dict[str, Any]]) -> dict[str, str]:
    """Upsert by deterministic pattern id. Patterns a teacher has already reviewed are left untouched."""
    statuses: dict[str, str] = {}
    for p in patterns:
        row = db.get(LearnerPattern, p["pattern_id"])
        if row is not None and row.status != "proposed":
            statuses[p["pattern_id"]] = row.status
            continue
        fields = dict(
            learner_id=learner_id, kind=p["kind"], subject=p["subject"], skill=p["skill"],
            statement=p["statement"], evidence_strength=p["evidence_strength"],
            n_observations=p["n_records"] + p["n_supporting_observations"], n_terms=p["n_terms"],
            n_sources=len(p["channels"]), confidence=None,
            detail={"subtype": p["subtype"], "channels": p["channels"], "caveats": p["caveats"], **p["detail"]},
        )
        if row is None:
            db.add(LearnerPattern(id=p["pattern_id"], status="proposed", **fields))
        else:
            for k, v in fields.items():
                setattr(row, k, v)
            db.execute(delete(Evidence).where(Evidence.pattern_id == p["pattern_id"]))
        db.flush()
        for e in p["evidence"]:
            if e.get("id") is None:
                continue
            db.add(Evidence(
                pattern_id=p["pattern_id"],
                record_id=e["id"] if e["type"] == "record" else None,
                observation_id=e["id"] if e["type"] == "observation" else None,
                note=e.get("note"),
            ))
        statuses[p["pattern_id"]] = "proposed"
    db.commit()
    return statuses


def _compact(p: dict[str, Any], status: str) -> dict[str, Any]:
    detail = dict(p["detail"])
    term_means = detail.pop("term_means", None)
    out = {
        "pattern_id": p["pattern_id"], "kind": p["kind"], "subtype": p["subtype"],
        "subject": p["subject"], "skill": p["skill"], "statement": p["statement"],
        "evidence_strength": p["evidence_strength"], "status": status,
        "n_terms": p["n_terms"], "n_records": p["n_records"], "channels": p["channels"],
        "caveats": p["caveats"],
        "evidence_counts": {
            "records": sum(1 for e in p["evidence"] if e["type"] == "record"),
            "observations": p["n_supporting_observations"],
        },
        "key_observation_ids": [e["id"] for e in p["evidence"] if e["type"] == "observation" and e["id"] is not None][:5],
        "detail": detail,
    }
    if term_means:
        out["term_means"] = [[t["term"], t["mean"]] for t in term_means]
    return out


def detect_patterns(learner_id: str, subject: str | None = None) -> dict[str, Any]:
    """Detect evidence-backed patterns across terms. May return 'insufficient' instead of a pattern."""
    with SessionLocal() as db:
        if db.get(Learner, learner_id) is None:
            return {"ok": False, "error": f"Unknown learner_id: {learner_id}"}
        records, observations = _load(db, learner_id)
        result = analyse(learner_id, records, observations, subject)
        statuses = _persist(db, learner_id, result["patterns"])
    return {
        "ok": True,
        "learner_id": learner_id,
        "subject": subject,
        "patterns": [_compact(p, statuses[p["pattern_id"]]) for p in result["patterns"]],
        "checked": result["checked"],
        "data_quality": result["data_quality"],
        "note": ("Candidate patterns for teacher review, not conclusions. Use get_evidence(pattern_id) for the "
                 "underlying records. An empty list with a non-empty 'checked' means nothing met the evidence bar."),
    }
