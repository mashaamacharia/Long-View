"""Run state and the human-readable event stream. Event writes never break a run."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from app.db.models import AgentEvent, AgentRun
from app.db.session import SessionLocal

log = logging.getLogger(__name__)
TERMINAL = ("completed", "failed")


def _jsonable(x: Any) -> Any:
    return json.loads(json.dumps(x, default=str))


class EventLog:
    def __init__(self, run_id: str):
        self.run_id = run_id

    def add(self, kind: str, node: str | None, title: str, detail: dict[str, Any] | None = None) -> None:
        try:
            with SessionLocal() as db:
                last = db.scalar(select(func.max(AgentEvent.seq)).where(AgentEvent.run_id == self.run_id)) or 0
                db.add(AgentEvent(run_id=self.run_id, seq=last + 1, kind=kind, node=node,
                                  title=title[:300], detail=_jsonable(detail) if detail else None))
                db.commit()
        except Exception:  # noqa: BLE001
            log.exception("could not write agent event")


def set_run(run_id: str, **fields: Any) -> None:
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        if run is None:
            return
        for k, v in fields.items():
            setattr(run, k, _jsonable(v) if k == "result" else v)
        if fields.get("state") in TERMINAL and run.finished_at is None:
            run.finished_at = datetime.now(timezone.utc)
        db.commit()
