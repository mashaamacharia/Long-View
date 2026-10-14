import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.events import TERMINAL
from app.db.models import AgentEvent, AgentRun, Learner, TeacherReview
from app.db.session import SessionLocal, get_db

router = APIRouter(prefix="/runs", tags=["runs"])


class RunIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    learner_id: str = Field(min_length=1, max_length=16)
    request: str = Field(min_length=3, max_length=500)


def _manager(request: Request):
    mgr = getattr(request.app.state, "runs", None)
    if mgr is None:
        raise HTTPException(503, "The agent runtime is not running")
    return mgr


def _iso(dt):
    return dt.isoformat() if dt else None


def _run_dict(run: AgentRun, db: Session, full: bool = True) -> dict:
    learner = db.get(Learner, run.learner_id)
    out = {"run_id": run.id, "state": run.state, "request": run.request, "learner_id": run.learner_id,
           "learner_name": learner.full_name if learner else None, "llm": {"provider": run.llm_provider, "model": run.llm_model},
           "started_at": _iso(run.started_at), "finished_at": _iso(run.finished_at)}
    if full:
        out["result"] = run.result
        out["review_ids"] = [r.id for r in db.scalars(select(TeacherReview).where(TeacherReview.run_id == run.id).order_by(TeacherReview.id))]
    return out


def _event_dict(e: AgentEvent) -> dict:
    return {"seq": e.seq, "kind": e.kind, "node": e.node, "title": e.title, "detail": e.detail, "created_at": _iso(e.created_at)}


@router.post("", status_code=202)
async def start_run(body: RunIn, request: Request, db: Session = Depends(get_db)) -> dict:
    """Start an agent run for a learner. Returns immediately; follow progress via /events or /stream."""
    if db.get(Learner, body.learner_id) is None:
        raise HTTPException(404, f"Learner {body.learner_id} not found")
    run_id = await _manager(request).start(body.learner_id, body.request.strip())
    return {"run_id": run_id, "state": "queued"}


@router.get("")
def list_runs(limit: int = 20, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(AgentRun).order_by(AgentRun.started_at.desc()).limit(max(1, min(limit, 100)))).all()
    return [_run_dict(r, db, full=False) for r in rows]


@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db)) -> dict:
    run = db.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(404, f"Run {run_id} not found")
    return _run_dict(run, db)


@router.get("/{run_id}/events")
def get_events(run_id: str, after: int = 0, db: Session = Depends(get_db)) -> list[dict]:
    if db.get(AgentRun, run_id) is None:
        raise HTTPException(404, f"Run {run_id} not found")
    rows = db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > after).order_by(AgentEvent.seq)).all()
    return [_event_dict(e) for e in rows]


@router.get("/{run_id}/stream")
async def stream(run_id: str, after: int = 0):
    """Server-sent events: every step of the run as it happens, ending when the run completes or fails.
    A paused run (waiting for the teacher) keeps the stream open with heartbeats."""
    with SessionLocal() as db:
        if db.get(AgentRun, run_id) is None:
            raise HTTPException(404, f"Run {run_id} not found")

    async def gen():
        last, idle = after, 0
        while True:
            with SessionLocal() as db:
                rows = db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > last).order_by(AgentEvent.seq)).all()
                events = [_event_dict(e) for e in rows]
                state = db.get(AgentRun, run_id).state
            for e in events:
                last = e["seq"]
                yield f"id: {last}\nevent: step\ndata: {json.dumps(e)}\n\n"
            if state in TERMINAL and not events:
                yield f"event: end\ndata: {json.dumps({'state': state})}\n\n"
                return
            idle = 0 if events else idle + 1
            if idle and idle % 30 == 0:
                yield ": keep-alive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(gen(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
