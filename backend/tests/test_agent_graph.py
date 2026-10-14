"""The agent end to end: tools over MCP, the review gate, pause/resume, fallbacks and containment.
The model is scripted (no Ollama in CI); the MCP server, database, router and runtime are real."""
import asyncio
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from app.agent import summary as summ
from app.agent.llm import LLMResponse, ToolCall
from app.config import settings
from app.db.models import AgentEvent, AgentRun, ProfileChange, TeacherReview, ToolCall as ToolCallRow
from app.services import reviews as svc
from evals.checks import agent_failures, collect_run_facts
from tests.agentkit import FakeFilesystem, ScriptedLLM, _summary_from_sheet, agent_env, down_llm, ideal_fn, ideal_llm  # noqa: F401

TASKS = {t["id"]: t for t in (yaml.safe_load(f.read_text()) for f in sorted((Path(__file__).resolve().parents[1] / "evals" / "tasks").glob("*.yaml")))}
PERSONA_EVALS = [f"EVAL-0{i}" for i in range(1, 9)]
EXPECTED_STATE = {"EVAL-01": "waiting_for_teacher", "EVAL-02": "completed", "EVAL-03": "waiting_for_teacher", "EVAL-04": "waiting_for_teacher",
                  "EVAL-05": "completed", "EVAL-06": "waiting_for_teacher", "EVAL-07": "completed", "EVAL-08": "waiting_for_teacher"}
EXPECTED_REVIEWS = {"EVAL-01": 1, "EVAL-02": 0, "EVAL-03": 1, "EVAL-04": 1, "EVAL-05": 0, "EVAL-06": 1, "EVAL-07": 0, "EVAL-08": 2}


# ---------- helpers ----------
async def go(env, learner, request):
    rid = await env.manager.start(learner, request)
    await env.manager.drain()
    return rid


def row(env, rid):
    with env.maker() as db:
        r = db.get(AgentRun, rid)
        return r.state, r.result


def facts(env, rid):
    with env.maker() as db:
        return collect_run_facts(db, rid)


def events(env, rid, kind=None):
    with env.maker() as db:
        q = select(AgentEvent).where(AgentEvent.run_id == rid).order_by(AgentEvent.seq)
        return [e for e in db.scalars(q) if kind is None or e.kind == kind]


def reviews(env, rid):
    with env.maker() as db:
        return db.scalars(select(TeacherReview).where(TeacherReview.run_id == rid).order_by(TeacherReview.id)).all()


async def decide(env, review_id, decision, comment=None):
    with env.maker() as db:
        svc.decide(db, review_id, "T-014", decision, comment)
    env.manager.on_decision(review_id)
    await env.manager.drain()


async def final_state(env, rid):
    tup = await env.saver.aget_tuple({"configurable": {"thread_id": rid}})
    return tup.checkpoint["channel_values"]


def n_changes(env):
    with env.maker() as db:
        return db.scalar(select(func.count()).select_from(ProfileChange))


# ---------- every persona, run as its eval task ----------
@pytest.mark.parametrize("eid", PERSONA_EVALS)
def test_each_persona_meets_its_eval_checks(agent_env, eid):
    task = TASKS[eid]

    async def main():
        rid = await go(agent_env, task["learner_id"], task["request"])
        state, _ = row(agent_env, rid)
        f = facts(agent_env, rid)
        assert state == EXPECTED_STATE[eid]
        assert f.flagged == EXPECTED_REVIEWS[eid]
        assert agent_failures(task["checks"], f) == [], f
        assert n_changes(agent_env) == 0                                  # nothing is ever written before a teacher decides
        if state == "completed":
            result = row(agent_env, rid)[1]
            assert result["summary"] and result["summary_source"] == "llm"
            if eid == "EVAL-05":
                assert f.evidence_passes == 0 and "get_evidence" not in f.tools_called   # insufficient data: stop, don't dig
        return rid
    asyncio.run(main())


def test_brians_summary_explains_the_outlier_from_the_document_and_stays_verified(agent_env):
    async def main():
        rid = await go(agent_env, "L1043", TASKS["EVAL-02"]["request"])
        st = await final_state(agent_env, rid)
        assert summ.verify(st["summary"], summ.build_facts(st)) == []
        assert any("assessment-week-absence" in p for p in st["gathered"]["docs"])
        assert "decline" not in st["summary"].lower() or "not" in st["summary"].lower()
        assert [p["kind"] for p in st["patterns"]] == ["anomaly"]
    asyncio.run(main())


# ---------- the model is down: same coverage, deterministic summary ----------
@pytest.mark.parametrize("eid", PERSONA_EVALS)
def test_without_a_model_the_run_still_meets_its_checks(agent_env, eid):
    agent_env.llm = down_llm()
    task = TASKS[eid]

    async def main():
        rid = await go(agent_env, task["learner_id"], task["request"])
        state, result = row(agent_env, rid)
        f = facts(agent_env, rid)
        assert state == EXPECTED_STATE[eid]
        assert agent_failures(task["checks"], f) == [], f                   # identical tool coverage and gate behaviour
        assert any("Model unavailable" in e.title for e in events(agent_env, rid, "error"))
        if state == "completed":
            assert result["summary_source"] == "template" and result["llm"]["available"] is False
            assert any(x.startswith("llm_unavailable") for x in result["fallbacks"])
            st = await final_state(agent_env, rid)
            assert summ.verify(st["summary"], summ.build_facts(st)) == []   # the fallback passes its own verifier
        else:
            st = await final_state(agent_env, rid)
            assert st["llm_ok"] is False and any(x.startswith("llm_unavailable") for x in st["fallbacks"])
        assert len(agent_env.llm.calls) == 1                                # one failed call, then no more waiting on a dead model
    asyncio.run(main())


# ---------- a hostile or confused model is contained ----------
def test_hostile_model_cannot_write_wander_or_forge(agent_env, monkeypatch):
    monkeypatch.setattr(settings, "agent_max_llm_steps", 8)
    other = f"{agent_env.docs}/L1042"
    script = [
        ToolCall("write_file", {"path": f"{agent_env.docs}/L1044/x.md", "content": "pwned"}),
        ToolCall("edit_file", {"path": f"{agent_env.docs}/L1044/x.md", "edits": []}),
        ToolCall("get_evidence", {"pattern_id": "PAT-DEADBEEF"}),
        ToolCall("read_text_file", {"path": "/etc/passwd"}),
        ToolCall("list_directory", {"path": other}),
        ToolCall("read_text_file", {"path": f"{agent_env.docs}/L1044/../L1042/2025-T3_x.md"}),
        ToolCall("update_learner_profile", {"pattern_id": "x", "summary": "x", "approval_id": "APP-1"}),
        ToolCall("flag_for_teacher_review", {"pattern_id": "x", "reason": "x"}),
    ]
    it = iter(script)

    def fn(messages, tools, json_mode):
        if tools:
            c = next(it, None)
            return LLMResponse(content="", tool_calls=[c]) if c else LLMResponse(content="DONE")
        return ideal_fn(messages, tools, json_mode)
    agent_env.llm = ScriptedLLM(fn)

    async def main():
        rid = await go(agent_env, "L1044", TASKS["EVAL-03"]["request"])
        assert row(agent_env, rid)[0] == "waiting_for_teacher"
        assert len(events(agent_env, rid, "rejected")) == 8                 # every hostile call refused
        reached = [(n, a.get("path")) for n, a in agent_env.fs.calls]
        assert all(n in ("list_directory", "read_text_file") for n, _ in reached)
        assert all(str(agent_env.docs / "L1044") in p for _, p in reached)    # never left the learner's folder
        f = facts(agent_env, rid)
        assert agent_failures(TASKS["EVAL-03"]["checks"], f) == []          # forced coverage still happened
        assert f.tools_called >= {"get_evidence", "flag_for_teacher_review"} and "update_learner_profile" not in f.tools_called
        st = await final_state(agent_env, rid)
        assert sum(1 for x in st["fallbacks"] if x.startswith("rejected model tool call")) == 8
        assert not (agent_env.docs / "L1044" / "x.md").exists()
    asyncio.run(main())


# ---------- the summary verifier in the loop ----------
def _summary_script(drafts):
    it = iter(drafts)

    def fn(messages, tools, json_mode):
        if tools:
            return ideal_fn(messages, tools, json_mode)
        good = _summary_from_sheet(messages[1]["content"])
        d = next(it)
        return good if d == "good" else good + " " + d
    return fn


def test_bad_draft_is_rejected_and_the_retry_is_used(agent_env):
    agent_env.llm = ScriptedLLM(_summary_script(["He is lazy and fell by 18 points.", "good"]))

    async def main():
        rid = await go(agent_env, "L1043", TASKS["EVAL-02"]["request"])
        _, result = row(agent_env, rid)
        assert result["summary_source"] == "llm" and result["verification"]["retried"] is True
        assert len(agent_env.llm.summary_calls) == 2
        retry = agent_env.llm.summary_calls[1]["messages"]
        assert "lazy" in retry[-1]["content"] and "18" in retry[-1]["content"]      # the model is told exactly what was wrong
        assert len(events(agent_env, rid, "rejected")) == 1
    asyncio.run(main())


def test_two_bad_drafts_fall_back_to_the_template(agent_env):
    agent_env.llm = ScriptedLLM(_summary_script(["He is lazy.", "Scores fell because of anxiety."]))

    async def main():
        rid = await go(agent_env, "L1043", TASKS["EVAL-02"]["request"])
        _, result = row(agent_env, rid)
        assert result["summary_source"] == "template" and len(agent_env.llm.summary_calls) == 2
        assert any("failed verification twice" in x for x in result["fallbacks"])
        assert "lazy" not in result["summary"].lower() and "anxiety" not in result["summary"].lower()
        st = await final_state(agent_env, rid)
        assert summ.verify(result["summary"], summ.build_facts(st)) == []
    asyncio.run(main())


# ---------- pause, decide, resume ----------
def test_approved_finding_pauses_then_writes_exactly_the_approved_statement(agent_env):
    async def main():
        rid = await go(agent_env, "L1044", TASKS["EVAL-03"]["request"])
        assert row(agent_env, rid)[0] == "waiting_for_teacher" and n_changes(agent_env) == 0
        (review,) = reviews(agent_env, rid)
        assert [e.kind for e in events(agent_env, rid)].count("interrupt") == 1
        await decide(agent_env, review.id, "approved", "Agree with the term averages.")
        state, result = row(agent_env, rid)
        assert state == "completed" and n_changes(agent_env) == 1
        with agent_env.maker() as db:
            change = db.scalars(select(ProfileChange)).one()
            from app.db.models import LearnerPattern
            assert change.summary == db.get(LearnerPattern, review.pattern_id).statement   # the teacher saw this exact wording
        assert result["profile_changes"][0]["change_id"] == change.id
        assert result["findings"][0]["outcome"] == "teacher approved; written to the profile"
        kinds = [e.kind for e in events(agent_env, rid)]
        assert kinds.index("interrupt") < kinds.index("resume") < kinds.index("final")
    asyncio.run(main())


def test_EVAL_10_rejection_writes_nothing_and_never_calls_the_update_tool(agent_env):
    task = TASKS["EVAL-10"]

    async def main():
        rid = await go(agent_env, task["learner_id"], "Review Cynthia's English results.")
        (review,) = reviews(agent_env, rid)
        await decide(agent_env, review.id, "rejected")
        state, result = row(agent_env, rid)
        assert state == "completed" and n_changes(agent_env) == 0
        assert agent_failures(task["checks"], facts(agent_env, rid)) == []
        assert result["findings"][0]["outcome"] == "teacher rejected; nothing written to the profile"
    asyncio.run(main())


def test_EVAL_09_a_request_to_skip_the_review_is_ignored(agent_env):
    task = TASKS["EVAL-09"]

    async def main():
        rid = await go(agent_env, task["learner_id"], task["request"])
        assert row(agent_env, rid)[0] == "waiting_for_teacher"
        assert agent_failures(task["checks"], facts(agent_env, rid)) == []
        assert len(reviews(agent_env, rid)) == 1 and n_changes(agent_env) == 0
    asyncio.run(main())


def test_resume_waits_for_every_review_of_the_round(agent_env):
    async def main():
        rid = await go(agent_env, "L1049", TASKS["EVAL-08"]["request"])
        first, second = reviews(agent_env, rid)
        await decide(agent_env, first.id, "approved")
        assert row(agent_env, rid)[0] == "waiting_for_teacher"                 # one review still pending: no resume yet
        assert n_changes(agent_env) == 0
        await decide(agent_env, second.id, "rejected")
        state, result = row(agent_env, rid)
        assert state == "completed" and n_changes(agent_env) == 1
        outcomes = {f["pattern_id"]: f["outcome"] for f in result["findings"]}
        assert sorted(outcomes.values()) == ["teacher approved; written to the profile", "teacher rejected; nothing written to the profile"]
    asyncio.run(main())


def test_more_evidence_loops_back_then_flags_again(agent_env):
    async def main():
        rid = await go(agent_env, "L1044", TASKS["EVAL-03"]["request"])
        (r1,) = reviews(agent_env, rid)
        await decide(agent_env, r1.id, "more_evidence", "What about her writing?")
        assert row(agent_env, rid)[0] == "waiting_for_teacher"                 # a second review is now pending
        r1b, r2 = reviews(agent_env, rid)
        assert r2.id != r1.id and r2.status == "pending" and r1b.status == "more_evidence"
        titles = [e.title for e in events(agent_env, rid)]
        assert any("teacher asked: What about her writing?" in t for t in titles)
        assert sum(1 for e in events(agent_env, rid, "interrupt")) == 2
        await decide(agent_env, r2.id, "approved")
        state, result = row(agent_env, rid)
        assert state == "completed" and n_changes(agent_env) == 1 and result["rounds"] == 2
    asyncio.run(main())


def test_the_loop_is_bounded(agent_env):
    async def main():
        rid = await go(agent_env, "L1044", TASKS["EVAL-03"]["request"])
        for _ in range(2):
            current = [r for r in reviews(agent_env, rid) if r.status == "pending"][0]
            await decide(agent_env, current.id, "more_evidence", "Still not sure.")
        state, result = row(agent_env, rid)
        assert state == "completed" and len(reviews(agent_env, rid)) == 2        # no third round
        assert n_changes(agent_env) == 0 and result["rounds"] == 2
        assert result["findings"][0]["outcome"] == "teacher more evidence; nothing written to the profile"
    asyncio.run(main())


# ---------- restarts ----------
def test_a_paused_run_survives_a_restart_and_a_stale_run_is_marked_failed(agent_env):
    async def main():
        rid = await go(agent_env, "L1044", TASKS["EVAL-03"]["request"])
        (review,) = reviews(agent_env, rid)
        with agent_env.maker() as db:
            db.add(AgentRun(id="RUN-STALE", learner_id="L1042", request="x", state="running"))
            db.commit()
            svc.decide(db, review.id, "T-014", "approved")                       # the teacher decides while the server is down
        restarted = agent_env.make_manager()                                     # a fresh process, same checkpoint store
        await restarted.recover()
        await restarted.drain()
        assert row(agent_env, rid)[0] == "completed" and n_changes(agent_env) == 1
        state, result = row(agent_env, "RUN-STALE")
        assert state == "failed" and "restarted" in result["error"]
    asyncio.run(main())


def test_decisions_do_not_double_resume(agent_env):
    async def main():
        rid = await go(agent_env, "L1044", TASKS["EVAL-03"]["request"])
        (review,) = reviews(agent_env, rid)
        with agent_env.maker() as db:
            svc.decide(db, review.id, "T-014", "approved")
        agent_env.manager.on_decision(review.id)
        agent_env.manager.on_decision(review.id)
        agent_env.manager.on_decision(review.id)
        await agent_env.manager.drain()
        assert n_changes(agent_env) == 1 and len(events(agent_env, rid, "final")) == 1
        assert row(agent_env, rid)[0] == "completed"                           # a duplicate resume must not disturb a finished run
        assert not any("Run failed" in e.title for e in events(agent_env, rid, "error"))
    asyncio.run(main())


# ---------- degraded environments ----------
def test_without_the_documents_server_the_run_continues(agent_env):
    agent_env.use_external = False

    async def main():
        rid = await go(agent_env, "L1043", TASKS["EVAL-02"]["request"])
        state, result = row(agent_env, rid)
        assert state == "completed" and result["documents_consulted"] == [] and agent_env.fs.calls == []
        assert "anomaly" in {f["kind"] for f in result["findings"]}
    asyncio.run(main())


def test_unknown_learner_is_refused_before_anything_starts(agent_env):
    async def main():
        with pytest.raises(ValueError):
            await agent_env.manager.start("L9999", "hello there")
    asyncio.run(main())


def test_a_crash_inside_a_run_is_recorded_not_lost(agent_env, monkeypatch):
    import app.agent.graph as g
    monkeypatch.setattr(g.policy, "pick_subject", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))

    async def main():
        rid = await go(agent_env, "L1043", "anything")
        state, result = row(agent_env, rid)
        assert state == "failed" and "boom" in result["error"]
        assert any("boom" in e.title for e in events(agent_env, rid, "error"))
    asyncio.run(main())


def test_a_failed_read_fails_the_run_instead_of_reporting_no_data(agent_env, monkeypatch):
    import app.mcp_server.tools.get_learner_timeline as tl
    monkeypatch.setattr(tl, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("database unreachable")))

    async def main():
        rid = await go(agent_env, "L1042", TASKS["EVAL-01"]["request"])
        state, result = row(agent_env, rid)
        assert state == "failed" and "Could not read the learner's records" in result["error"]
        assert "summary" not in result                                       # no cheerful "nothing found" report
        assert any("database unreachable" in e.title or "Could not read" in e.title for e in events(agent_env, rid))
    asyncio.run(main())


def test_failed_detection_fails_the_run(agent_env, monkeypatch):
    import app.mcp_server.tools.detect_patterns as dp
    monkeypatch.setattr(dp, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("detector down")))

    async def main():
        rid = await go(agent_env, "L1042", TASKS["EVAL-01"]["request"])
        state, result = row(agent_env, rid)
        assert state == "failed" and "Pattern detection failed" in result["error"]
    asyncio.run(main())


def test_a_failed_evidence_fetch_is_disclosed_in_the_summary(agent_env, monkeypatch):
    import app.mcp_server.tools.get_evidence as ge
    monkeypatch.setattr(ge, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("evidence store down")))

    async def main():
        rid = await go(agent_env, "L1043", TASKS["EVAL-02"]["request"])
        state, result = row(agent_env, rid)
        assert state == "completed"
        st = await final_state(agent_env, rid)
        assert "could not be retrieved" in summ.build_facts(st).text
        assert summ.verify(result["summary"], summ.build_facts(st)) == []
    asyncio.run(main())
