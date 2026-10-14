"""Run the evaluation suite against the configured model and write the results.

    make eval                       # all 10 tasks against your real model (about 30 minutes on CPU)
    make eval ONLY=EVAL-03,EVAL-05  # a subset
    make eval-quick                 # no model at all: the deterministic floor, about a minute

WARNING: before every task this wipes the FINDINGS tables (patterns, evidence, reviews, approvals,
profile changes) so each task starts clean. Learner records and notes are untouched. Run
`make seed-reset` afterwards if you want a fresh demo state.

How a task is judged
  1. The run starts and executes to its first stop (waiting for a teacher, or completed).
  2. Agent-level checks (tools called, review flagged, documents read, nothing written) are read at
     that first stop, before the harness decides anything.
  3. Tasks that name a teacher decision get that decision; tasks that check the final summary get
     both findings approved so the run completes. Then analysis checks and the summary verifier run.
  4. Universal checks apply to every task: the run did not fail, nothing was written to a profile
     before a teacher decided, and any model-written summary passes the verifier.
The natural-language `expect` and `must_not` lines are copied into the report for human review.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml
from sqlalchemy import delete, select

from app.agent import summary as summ
from app.agent.llm import LLM, LLMError, get_llm
from app.agent.runtime import RunManager, open_checkpointer
from app.db.models import AgentRun, Approval, Evidence, LearnerPattern, ProfileChange, TeacherReview
from app.db.session import SessionLocal
from app.services import reviews as svc
from evals.checks import agent_failures, analysis_failures, collect_run_facts, duplicate_truth

TASKS_DIR = Path(__file__).parent / "tasks"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"


class NullLLM:
    """No model at all. Every call fails, so the run exercises only the deterministic floor."""
    provider, model = "none", "deterministic-only"

    async def chat(self, *a: Any, **k: Any):
        raise LLMError("model disabled for this run (--llm none)")


def load_tasks(only: list[str] | None = None) -> list[dict[str, Any]]:
    tasks = [yaml.safe_load(f.read_text()) for f in sorted(TASKS_DIR.glob("*.yaml"))]
    if only:
        wanted = {o.upper() for o in only}
        unknown = wanted - {t["id"] for t in tasks}
        if unknown:
            raise SystemExit(f"unknown task id(s): {', '.join(sorted(unknown))}")
        tasks = [t for t in tasks if t["id"] in wanted]
    return tasks


def reset_findings(db) -> None:
    for model in (ProfileChange, Approval, Evidence, TeacherReview, LearnerPattern):
        db.execute(delete(model))
    db.commit()


async def _state(manager: RunManager, run_id: str) -> dict[str, Any]:
    tup = await manager.saver.aget_tuple({"configurable": {"thread_id": run_id}})
    return dict(tup.checkpoint["channel_values"]) if tup else {}


def _run_state(run_id: str) -> tuple[str, dict[str, Any] | None]:
    with SessionLocal() as db:
        r = db.get(AgentRun, run_id)
        return r.state, r.result


async def _decide_all(manager: RunManager, run_id: str, decision: str, comment: str | None = None) -> int:
    decided = 0
    for _ in range(4):                                   # a "more evidence" loop can open another round
        with SessionLocal() as db:
            pending = [r.id for r in db.scalars(select(TeacherReview).where(TeacherReview.run_id == run_id, TeacherReview.status == "pending"))]
        if not pending:
            break
        for rid in pending:
            with SessionLocal() as db:
                svc.decide(db, rid, "T-EVAL", decision, comment)
            manager.on_decision(rid)
            decided += 1
        await manager.drain()
    return decided


async def run_task(manager: RunManager, task: dict[str, Any]) -> dict[str, Any]:
    checks = task["checks"]
    needs_summary = "must_not_assert_labels" in checks
    forced = checks.get("teacher_decision")
    with SessionLocal() as db:
        reset_findings(db)
    t0 = time.monotonic()
    run_id = await manager.start(task["learner_id"], task["request"])
    await manager.drain()
    state, _ = _run_state(run_id)
    with SessionLocal() as db:
        at_stop = collect_run_facts(db, run_id)
    failures: list[str] = []
    if at_stop.profile_changes:
        failures.append(f"universal: {at_stop.profile_changes} profile change(s) written before any teacher decided")

    final = at_stop
    if state == "waiting_for_teacher" and (forced or needs_summary):
        await _decide_all(manager, run_id, forced or "approved")
        with SessionLocal() as db:
            final = collect_run_facts(db, run_id)
    state, result = _run_state(run_id)
    seconds = time.monotonic() - t0
    if state == "failed":
        failures.append(f"universal: the run failed: {(result or {}).get('error')}")

    agent_facts = final if forced else at_stop          # checks about "nothing written yet" belong at the first stop
    failures += [f"agent: {m}" for m in agent_failures({k: v for k, v in checks.items() if k != "teacher_decision" or forced}, agent_facts)]
    st = await _state(manager, run_id)
    summary_text = (result or {}).get("summary")
    with SessionLocal() as db:
        truth = duplicate_truth(db, task["learner_id"], st.get("subject"))
    failures += [f"analysis: {m}" for m in analysis_failures(checks, patterns=st.get("patterns", []),
                 data_quality=st.get("data_quality", {}), summary=summary_text, truth=truth)]
    if summary_text and (result or {}).get("summary_source") == "llm":
        problems = summ.verify(summary_text, summ.build_facts(st))
        if problems:
            failures.append(f"universal: model summary fails the verifier: {problems}")

    llm = (result or {}).get("llm") or {}
    return {
        "id": task["id"], "name": task["name"], "scenario": task["scenario"], "learner_id": task["learner_id"],
        "request": task["request"], "passed": not failures, "failures": failures,
        "state_at_first_stop": at_stop.state if at_stop.state != "running" else state, "final_state": state,
        "seconds": round(seconds, 1), "reviews": final.flagged, "tools_called": sorted(final.tools_called),
        "documents_read": len(final.docs_read), "evidence_passes": at_stop.evidence_passes,
        "llm_calls": llm.get("calls", st.get("llm_calls", 0)), "llm_seconds": llm.get("seconds", round(st.get("llm_seconds", 0), 1)),
        "summary_source": (result or {}).get("summary_source"),
        "fallbacks": (result or {}).get("fallbacks") or st.get("fallbacks", []),
        "summary": (summary_text or "")[:700], "expect": task.get("expect", []), "must_not": task.get("must_not", []),
    }


async def run_suite(manager: RunManager, tasks: list[dict[str, Any]], llm: LLM | None = None,
                    log: Callable[[str], None] = print) -> dict[str, Any]:
    warm = None
    if llm is not None and getattr(llm, "provider", "") != "none":
        log("warming the model up (the first call loads it into memory)...")
        t0 = time.monotonic()
        try:
            await llm.chat([{"role": "user", "content": "Reply with the single word OK."}], max_tokens=5)
            warm = round(time.monotonic() - t0, 1)
            log(f"  model ready in {warm}s")
        except LLMError as exc:
            log(f"  WARNING: model unreachable ({exc}); runs will use the deterministic fallbacks")
    results = []
    for i, task in enumerate(tasks, start=1):
        log(f"[{i}/{len(tasks)}] {task['id']} {task['name']}")
        r = await run_task(manager, task)
        log(f"      {'PASS' if r['passed'] else 'FAIL'}  {r['seconds']}s, {r['llm_calls']} model call(s), {len(r['fallbacks'])} fallback(s)")
        for f in r["failures"]:
            log(f"        - {f}")
        results.append(r)
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "provider": getattr(llm, "provider", None), "model": getattr(llm, "model", None), "warmup_seconds": warm,
        "passed": sum(r["passed"] for r in results), "total": len(results),
        "total_seconds": round(sum(r["seconds"] for r in results), 1), "results": results,
    }


def render_markdown(report: dict[str, Any]) -> str:
    L = [f"**Model:** `{report['provider']}/{report['model']}`  ",
         f"**Run:** {report['generated_at']}  ",
         f"**Result:** {report['passed']} of {report['total']} passed  ",
         f"**Time:** {report['total_seconds']}s across tasks" + (f" (model warm-up {report['warmup_seconds']}s, not counted)" if report.get("warmup_seconds") else ""), "",
         "| ID | Scenario | Result | Time | Model calls | Fallbacks used | Summary |", "|---|---|---|---|---|---|---|"]
    for r in report["results"]:
        L.append(f"| {r['id']} | {r['scenario']} | {'PASS' if r['passed'] else '**FAIL**'} | {r['seconds']}s | {r['llm_calls']} | "
                 f"{len(r['fallbacks'])} | {r['summary_source'] or 'n/a (paused for teacher)'} |")
    bad = [r for r in report["results"] if not r["passed"]]
    if bad:
        L += ["", "### Failures", ""]
        for r in bad:
            L.append(f"**{r['id']}** {r['name']}")
            L += [f"- {f}" for f in r["failures"]]
            L.append("")
    used = [r for r in report["results"] if r["fallbacks"]]
    if used:
        L += ["", "### Fallbacks the agent used (the model did not do what was asked, code covered for it)", ""]
        for r in used:
            L.append(f"**{r['id']}**")
            L += [f"- {f}" for f in r["fallbacks"]]
            L.append("")
    return "\n".join(L).rstrip() + "\n"


def write_outputs(report: dict[str, Any], evals_md: Path | None, json_path: Path | None) -> list[str]:
    wrote = []
    if json_path:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(report, indent=2))
        wrote.append(str(json_path))
    if evals_md:
        body = f"{START}\n{render_markdown(report)}{END}"
        text = evals_md.read_text() if evals_md.exists() else "# Evals\n\n"
        if START in text and END in text:
            text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: body, text, flags=re.DOTALL)
        else:
            text = text.rstrip() + "\n\n## Results\n\n" + body + "\n"
        evals_md.write_text(text)
        wrote.append(str(evals_md))
    return wrote


async def _main(args: argparse.Namespace) -> int:
    if not args.yes:
        print(__doc__.split("How a task is judged")[0])
        if input("This wipes findings tables before each task. Continue? [y/N] ").strip().lower() != "y":
            return 2
    tasks = load_tasks(args.only.split(",") if args.only else None)
    llm: LLM = NullLLM() if args.llm == "none" else get_llm()
    print(f"{len(tasks)} task(s), model: {llm.provider}/{llm.model}\n")
    async with open_checkpointer("memory://") as saver:
        manager = RunManager(saver, llm_factory=lambda: llm)
        manager.attach_loop()
        report = await run_suite(manager, tasks, llm)
    out_dir = Path(args.out)
    wrote = write_outputs(report, Path(args.evals_md) if args.evals_md and Path(args.evals_md).exists() else None,
                          out_dir / ("latest-nomodel.json" if args.llm == "none" else "latest.json"))
    print(f"\n{report['passed']} of {report['total']} passed in {report['total_seconds']}s. wrote: {', '.join(wrote)}")
    return 0 if report["passed"] == report["total"] else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated task ids, e.g. EVAL-03,EVAL-05")
    ap.add_argument("--llm", choices=["configured", "none"], default="configured")
    ap.add_argument("--out", default=str(Path(__file__).parent / "results"))
    ap.add_argument("--evals-md", default="/app/EVALS.md", help="results are written between markers in this file if it exists")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    sys.exit(asyncio.run(_main(ap.parse_args())))
