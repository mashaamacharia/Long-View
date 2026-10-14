"""Runs the graph: start, pause at the teacher gate, resume on their decision, survive restarts.

One run at a time executes (a CPU-bound local model cannot serve two). A per-run lock makes sure a
decision can never resume a run that is still on its way to the pause, or resume it twice.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager
from typing import Any, AsyncContextManager, AsyncIterator, Callable

from langgraph.types import Command
from sqlalchemy import func, select

from app.agent.events import EventLog, set_run
from app.agent.graph import Deps, build_graph
from app.agent.llm import LLM, get_llm
from app.agent.tools import ToolRouter, open_router
from app.config import settings
from app.db.models import AgentRun, Approval, Learner, TeacherReview
from app.db.session import SessionLocal

log = logging.getLogger(__name__)
RouterFactory = Callable[[str, str], AsyncContextManager[ToolRouter]]


@asynccontextmanager
async def open_checkpointer(database_url: str | None = None) -> AsyncIterator[Any]:
    """Postgres checkpointer in production (runs survive restarts); in-memory otherwise (tests, CLI)."""
    url = database_url or settings.database_url
    if url.startswith("postgresql"):
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        async with AsyncPostgresSaver.from_conn_string(url.replace("postgresql+psycopg://", "postgresql://")) as saver:
            await saver.setup()
            yield saver
    else:
        from langgraph.checkpoint.memory import InMemorySaver
        yield InMemorySaver()


def default_router_factory(run_id: str, learner_id: str) -> AsyncContextManager[ToolRouter]:
    return open_router(run_id, learner_id)


def root_cause(exc: BaseException) -> str:
    """MCP transports run on anyio task groups, which wrap every error in an ExceptionGroup. Report the real one(s)."""
    if isinstance(exc, BaseExceptionGroup):
        leaves = [root_cause(e) for e in exc.exceptions]
        return "; ".join(dict.fromkeys(leaves))
    return f"{type(exc).__name__}: {exc}"


class RunManager:
    def __init__(self, saver: Any, router_factory: RouterFactory | None = None,
                 llm_factory: Callable[[], LLM | None] | None = None, max_concurrent: int = 1):
        self.saver = saver
        self.router_factory = router_factory or default_router_factory
        self.llm_factory = llm_factory or get_llm
        self._sem = asyncio.Semaphore(max_concurrent)
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: set[asyncio.Task] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    # ----- plumbing -----
    def attach_loop(self) -> None:
        self._loop = asyncio.get_running_loop()

    def _lock(self, run_id: str) -> asyncio.Lock:
        return self._locks.setdefault(run_id, asyncio.Lock())

    def _spawn(self, coro) -> None:
        """Schedule from the event loop or from a worker thread (sync FastAPI endpoints)."""
        try:
            task = asyncio.get_running_loop().create_task(coro)
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
        except RuntimeError:
            if self._loop is None:
                coro.close()
                raise
            asyncio.run_coroutine_threadsafe(coro, self._loop)

    async def drain(self) -> None:
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    # ----- public API -----
    async def start(self, learner_id: str, request: str) -> str:
        run_id = "RUN-" + uuid.uuid4().hex[:8].upper()
        with SessionLocal() as db:
            learner = db.get(Learner, learner_id)
            if learner is None:
                raise ValueError(f"Unknown learner {learner_id}")
            db.add(AgentRun(id=run_id, learner_id=learner_id, request=request, state="queued"))
            db.commit()
            name = learner.full_name
        EventLog(run_id).add("node", "runtime", "Run queued")
        self._spawn(self.execute_start(run_id, name))
        return run_id

    async def execute_start(self, run_id: str, learner_name: str) -> None:
        async with self._lock(run_id):
            await self._segment(run_id, self._start_input(run_id, learner_name))

    async def maybe_resume(self, run_id: str) -> bool:
        async with self._lock(run_id):
            with SessionLocal() as db:
                run = db.get(AgentRun, run_id)
                if run is None or run.state != "waiting_for_teacher":
                    return False
                pending = db.scalar(select(func.count()).select_from(TeacherReview)
                                    .where(TeacherReview.run_id == run_id, TeacherReview.status == "pending")) or 0
            if pending:
                return False
            await self._segment(run_id, self._resume_input)
            return True

    def on_decision(self, review_id: int) -> None:
        """Called after a teacher decides. Resumes the run once every review of its current round is decided."""
        with SessionLocal() as db:
            review = db.get(TeacherReview, review_id)
            run_id = review.run_id if review else None
        if run_id:
            self._spawn(self.maybe_resume(run_id))

    async def recover(self) -> None:
        """After a restart: interrupted runs are marked failed; paused runs resume if their decisions arrived meanwhile."""
        with SessionLocal() as db:
            stale = [r.id for r in db.scalars(select(AgentRun).where(AgentRun.state.in_(("queued", "running"))))]
            waiting = [r.id for r in db.scalars(select(AgentRun).where(AgentRun.state == "waiting_for_teacher"))]
        for rid in stale:
            set_run(rid, state="failed", result={"error": "The server restarted while this run was in progress. Start it again."})
            EventLog(rid).add("error", "runtime", "Server restarted mid-run; run marked failed")
        for rid in waiting:
            self._spawn(self.maybe_resume(rid))

    # ----- one execution segment (start, or resume after a pause) -----
    def _start_input(self, run_id: str, learner_name: str):
        async def build(graph, config):
            with SessionLocal() as db:
                run = db.get(AgentRun, run_id)
                learner_id, request = run.learner_id, run.request
            return {"run_id": run_id, "learner_id": learner_id, "learner_name": learner_name, "request": request,
                    "llm_ok": True, "loops": 0, "rounds": 0, "llm_calls": 0, "llm_seconds": 0.0, "fallbacks": [],
                    "followups": [], "gathered": {}, "reviews": [], "decisions": [], "applied": [],
                    "pending_decisions": [], "refresh": False}
        return build

    @staticmethod
    async def _resume_input(graph, config):
        snap = await graph.aget_state(config)
        decisions = []
        with SessionLocal() as db:
            for r in snap.values.get("reviews", []):
                review = db.get(TeacherReview, r["review_id"])
                approval = db.scalars(select(Approval).where(Approval.review_id == review.id)
                                      .order_by(Approval.decided_at.desc())).first()
                decisions.append({"review_id": review.id, "pattern_id": review.pattern_id, "decision": review.status,
                                  "approval_id": approval.id if approval else None,
                                  "comment": approval.comment if approval else None})
        return Command(resume=decisions)

    async def _segment(self, run_id: str, build_input) -> None:
        with SessionLocal() as db:
            learner_id = db.get(AgentRun, run_id).learner_id
        events = EventLog(run_id)
        async with self._sem:
            set_run(run_id, state="running")
            try:
                async with self.router_factory(run_id, learner_id) as router:
                    if router.external_error:
                        events.add("node", "runtime", "Documents server unavailable; continuing without documents",
                                   {"error": router.external_error})
                    llm = self.llm_factory()
                    set_run(run_id, llm_provider=getattr(llm, "provider", None), llm_model=getattr(llm, "model", None))
                    graph = build_graph(Deps(run_id=run_id, learner_id=learner_id, tools=router, llm=llm, events=events,
                                             max_llm_steps=settings.agent_max_llm_steps,
                                             max_rounds=settings.agent_max_rounds)).compile(checkpointer=self.saver)
                    config = {"configurable": {"thread_id": run_id}, "recursion_limit": 60}
                    await graph.ainvoke(await build_input(graph, config), config)
                    snap = await graph.aget_state(config)
                if snap.next:
                    set_run(run_id, state="waiting_for_teacher")
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("run %s failed", run_id)
                cause = root_cause(exc)
                events.add("error", "runtime", f"Run failed: {cause}")
                set_run(run_id, state="failed", result={"error": cause})
