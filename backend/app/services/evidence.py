"""Shared evidence loader. The agent's tool view is sampled and redacted; the teacher's dashboard
view is complete and shows the original notes. Same data, same code, different arguments."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evidence, LearnerPattern, Observation, Record
from app.mcp_server.analysis.common import pct, term_ord
from app.mcp_server.analysis.conflicts import has_label_language

WITHHELD = ("[withheld: this note characterises the learner rather than describing observed work; "
            "the teacher can read the original in the dashboard]")


def _select(items: list[dict[str, Any]], k: int) -> list[dict[str, Any]]:
    """Up to k items in time order: split between the earliest and the latest."""
    if len(items) <= k:
        return items
    head, tail = (k + 1) // 2, k // 2
    return items[:head] + (items[-tail:] if tail else [])


def _strip(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{k: v for k, v in i.items() if k != "_order"} for i in items]


def build_evidence(db: Session, pattern_id: str, *, max_records: int = 12, max_observations: int = 8,
                   max_attendance: int = 12, redact_labels: bool = True) -> dict[str, Any]:
    pat = db.get(LearnerPattern, pattern_id)
    if pat is None:
        return {"ok": False, "error": f"Unknown pattern_id: {pattern_id}. Run detect_patterns first."}
    ev = db.scalars(select(Evidence).where(Evidence.pattern_id == pattern_id).order_by(Evidence.id)).all()
    rec_ids = [e.record_id for e in ev if e.record_id is not None]
    obs_ids = [e.observation_id for e in ev if e.observation_id is not None]
    recs = {r.id: r for r in db.scalars(select(Record).where(Record.id.in_(rec_ids)))} if rec_ids else {}
    obs = {o.id: o for o in db.scalars(select(Observation).where(Observation.id.in_(obs_ids)))} if obs_ids else {}
    documents = [{"document_ref": e.document_ref, "note": e.note} for e in ev if e.document_ref]
    detail = dict(pat.detail or {})

    records, attendance, observations = [], [], []
    for e in ev:
        if e.record_id in recs:
            r = recs[e.record_id]
            p = pct({"score": r.score, "max_score": r.max_score})
            order = (term_ord(r.term), r.id)
            if r.kind == "attendance":
                attendance.append({"term": r.term, "pct": None if p is None else round(p, 1), "_order": order})
                continue
            records.append({
                "record_id": r.id, "term": r.term, "kind": r.kind, "title": r.title,
                "pct": None if p is None else round(p, 1), "score": r.score, "max_score": r.max_score,
                "late": bool(r.submitted_late), "source": r.source, "_order": order,
            })
        elif e.observation_id in obs:
            o = obs[e.observation_id]
            labelled = has_label_language(o.text)
            observations.append({
                "observation_id": o.id, "term": o.term, "teacher_id": o.teacher_id, "subject": o.subject,
                "skill": o.skill, "sentiment": o.sentiment,
                "text": WITHHELD if (labelled and redact_labels) else o.text,
                "characterising_language": labelled, "_order": (term_ord(o.term), o.id),
            })
    for lst in (records, attendance, observations):
        lst.sort(key=lambda i: i["_order"])

    shown_records = _select(records, max_records)
    shown_obs = _select(observations, max_observations)
    shown_att = _select(attendance, max_attendance)
    term_means = detail.pop("term_means", None)
    out: dict[str, Any] = {
        "ok": True,
        "pattern": {
            "pattern_id": pat.id, "kind": pat.kind, "subtype": detail.get("subtype"), "subject": pat.subject,
            "skill": pat.skill, "statement": pat.statement, "evidence_strength": pat.evidence_strength,
            "status": pat.status, "n_terms": pat.n_terms, "channels": detail.get("channels", []),
            "caveats": detail.get("caveats", []),
        },
        "records": {"total": len(records), "shown": len(shown_records), "items": _strip(shown_records)},
        "observations": {"total": len(observations), "shown": len(shown_obs), "items": _strip(shown_obs)},
        "documents": documents,
    }
    if term_means:
        out["term_means"] = [[t["term"], t["mean"]] for t in term_means]
    if attendance:
        out["attendance"] = {"total": len(attendance), "items": [[a["term"], a["pct"]] for a in _strip(shown_att)]}
    return out
