"""Run the agent from a terminal, with no dashboard.

    make agent L=L1044 Q="Look at Cynthia's English results"            # asks you to decide at the review gate
    make agent L=L1044 Q="..." A=approve                                  # or A=reject
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any, Callable

from sqlalchemy import select

from app.agent.events import TERMINAL
from app.agent.runtime import RunManager, open_checkpointer
from app.db.models import AgentEvent, AgentRun, TeacherReview
from app.db.session import SessionLocal
from app.services import reviews as svc

Decide = Callable[[dict[str, Any]], tuple[str, str | None]]


async def drive(manager: RunManager, learner_id: str, request: str, decide: Decide | None = None,
                out: Callable[[str], None] = print, poll: float = 0.25) -> dict[str, Any]:
    """Start a run, print its steps as they happen, answer review prompts via `decide`.
    With decide=None the function returns as soon as the run is waiting for a teacher."""
    run_id = await manager.start(learner_id, request)
    out(f"run {run_id} started")
    seen = 0
    while True:
        await asyncio.sleep(poll)
        with SessionLocal() as db:
            for e in db.scalars(select(AgentEvent).where(AgentEvent.run_id == run_id, AgentEvent.seq > seen).order_by(AgentEvent.seq)):
                seen = e.seq
                out(f"  [{e.kind:<9}] {e.node or '':<14} {e.title}")
            run = db.get(AgentRun, run_id)
            state = run.state
            pending = [r.id for r in db.scalars(select(TeacherReview).where(TeacherReview.run_id == run_id, TeacherReview.status == "pending"))] \
                if state == "waiting_for_teacher" else []
        if state in TERMINAL:
            break
        if pending:
            if decide is None:
                return {"run_id": run_id, "state": state, "result": None}
            for rid in pending:
                with SessionLocal() as db:
                    detail = svc.review_detail(db, rid)
                decision, comment = decide(detail)
                with SessionLocal() as db:
                    svc.decide(db, rid, "T-CLI", decision, comment)
                out(f"  >> review {rid}: {decision}" + (f" ({comment})" if comment else ""))
                manager.on_decision(rid)
    await manager.drain()
    with SessionLocal() as db:
        run = db.get(AgentRun, run_id)
        return {"run_id": run_id, "state": run.state, "result": run.result}


def _ask(detail: dict[str, Any]) -> tuple[str, str | None]:
    p = detail["pattern"]
    print(f"\n--- review {detail['review_id']}: {detail['learner']['full_name']} ---\n{p['statement']}\n"
          f"evidence: {p['evidence_strength']}, {p['n_terms']} terms. Agent's reason: {detail['reason']}")
    while True:
        a = input("[a]pprove / [r]eject / [m]ore evidence? ").strip().lower()[:1]
        if a in ("a", "r"):
            return ("approved" if a == "a" else "rejected"), None
        if a == "m":
            return "more_evidence", input("what should it look at? ").strip() or None


async def _main(args: argparse.Namespace) -> int:
    decide: Decide | None = _ask
    if args.approve:
        decide = lambda d: ("approved", None)
    elif args.reject:
        decide = lambda d: ("rejected", None)
    async with open_checkpointer("memory://") as saver:      # one process, so an in-memory checkpoint is enough
        manager = RunManager(saver)
        manager.attach_loop()
        res = await drive(manager, args.learner_id, args.request, decide)
    r = res["result"] or {}
    print(f"\nstate: {res['state']}")
    if r.get("summary"):
        print(f"\n{r['summary']}\n")
    if r.get("llm"):
        l = r["llm"]
        print(f"model: {l['provider']}/{l['model']}  calls: {l['calls']}  time: {l['seconds']}s  available: {l['available']}")
        print(f"summary source: {r['summary_source']}  fallbacks used: {len(r['fallbacks'])}")
        for f in r["fallbacks"]:
            print(f"  - {f}")
    if r.get("error"):
        print(f"error: {r['error']}")
    return 0 if res["state"] == "completed" else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("learner_id")
    ap.add_argument("request")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--approve", action="store_true", help="approve every finding automatically")
    g.add_argument("--reject", action="store_true", help="reject every finding automatically")
    sys.exit(asyncio.run(_main(ap.parse_args())))
