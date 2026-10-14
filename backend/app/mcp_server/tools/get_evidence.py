"""get_evidence: the records, teacher observations and documents behind one pattern.

Sized for a small model: counts plus a representative sample, not a dump. Teacher notes that
contain trait or ability labels are withheld from this tool's output (flagged instead), so the
agent can say that such notes exist without repeating them as findings; the teacher reads the
original note in the dashboard (see app/services/evidence.py).
"""
from __future__ import annotations

from typing import Any

from app.db.session import SessionLocal
from app.services.evidence import build_evidence


def get_evidence(pattern_id: str, max_records: int = 12, max_observations: int = 8) -> dict[str, Any]:
    """Return the evidence behind a pattern: a sample of records, teacher observations, attendance."""
    max_records = max(1, min(int(max_records), 50))
    max_observations = max(1, min(int(max_observations), 20))
    with SessionLocal() as db:
        out = build_evidence(db, pattern_id, max_records=max_records, max_observations=max_observations,
                             redact_labels=True)
    if out["ok"]:
        out["note"] = ("Cite record_id and observation_id for every claim. Samples are the earliest and latest "
                       "records; raise max_records for more. Notes marked characterising_language are withheld "
                       "on purpose.")
    return out
