import asyncio

import pytest
from sqlalchemy import func, select

from app.db.models import ProfileChange
from app.agent.llm import LLMResponse
from scripts.check_agent_llm import check
from scripts.run_agent import drive
from tests.agentkit import ScriptedLLM, agent_env, down_llm, ideal_fn, ideal_llm  # noqa: F401

Q = "Look at Cynthia's English results over time."


def changes(env):
    with env.maker() as db:
        return db.scalar(select(func.count()).select_from(ProfileChange))


@pytest.fixture()
def drive_env(agent_env, monkeypatch):
    import scripts.run_agent as ra
    monkeypatch.setattr(ra, "SessionLocal", agent_env.maker)
    return agent_env


def test_drive_approve_reject_and_pause(drive_env):
    # one learner per scenario: a decided finding is (correctly) never re-proposed on a later run
    async def main():
        lines = []
        res = await drive(drive_env.manager, "L1044", Q, decide=lambda d: ("approved", None), out=lines.append, poll=0.01)
        assert res["state"] == "completed" and changes(drive_env) == 1 and "approved" in "\n".join(lines)
        assert any("interrupt" in l for l in lines) and any("final" in l for l in lines)

        res = await drive(drive_env.manager, "L1042", "Review Amina's mathematics progress.", decide=lambda d: ("rejected", None),
                          out=lambda s: None, poll=0.01)
        assert res["state"] == "completed" and changes(drive_env) == 1          # rejected: nothing new written

        res = await drive(drive_env.manager, "L1045", "Summarise David's mathematics profile.", decide=None,
                          out=lambda s: None, poll=0.01)
        assert res["state"] == "waiting_for_teacher" and res["result"] is None   # returns at the gate instead of hanging

        again = await drive(drive_env.manager, "L1044", Q, decide=lambda d: ("approved", None), out=lambda s: None, poll=0.01)
        assert again["state"] == "completed" and changes(drive_env) == 1         # approved findings are not re-proposed
        assert again["result"]["findings"][0]["outcome"] is None or "approved" in (again["result"]["findings"][0]["outcome"] or "")
    asyncio.run(main())


def test_drive_follows_a_more_evidence_then_approve_sequence(drive_env):
    answers = iter([("more_evidence", "What about writing?"), ("approved", None)])

    async def main():
        res = await drive(drive_env.manager, "L1044", Q, decide=lambda d: next(answers), out=lambda s: None, poll=0.01)
        assert res["state"] == "completed" and res["result"]["rounds"] == 2 and changes(drive_env) == 1
    asyncio.run(main())


def test_drive_reports_a_failed_run(drive_env, monkeypatch):
    import app.mcp_server.tools.get_learner_timeline as tl
    monkeypatch.setattr(tl, "SessionLocal", lambda: (_ for _ in ()).throw(RuntimeError("db down")))

    async def main():
        res = await drive(drive_env.manager, "L1044", Q, decide=lambda d: ("approved", None), out=lambda s: None, poll=0.01)
        assert res["state"] == "failed" and "Could not read" in res["result"]["error"]
    asyncio.run(main())


def test_check_agent_llm_passes_a_model_that_behaves():
    lines = []
    assert asyncio.run(check(ideal_llm(), out=lines.append)) is True
    assert sum(l.startswith("PASS") for l in lines) == 3


def test_check_agent_llm_names_each_way_a_model_can_fail():
    never_calls = ScriptedLLM(lambda m, t, j: LLMResponse(content="I will look into it.") if t else ideal_fn(m, t, j))
    lines = []
    assert asyncio.run(check(never_calls, out=lines.append)) is False
    assert lines[0].startswith("FAIL  1") and "no tool call" in lines[0]

    always_calls = ScriptedLLM(lambda m, t, j: ideal_fn(m, t, j) if not t else __import__("tests.agentkit", fromlist=["x"]).LLMResponse(
        content="", tool_calls=[__import__("tests.agentkit", fromlist=["x"]).ToolCall("get_evidence", {"pattern_id": "PAT-AB12CD34"})]))
    lines = []
    assert asyncio.run(check(always_calls, out=lines.append)) is False and any(l.startswith("FAIL  2") for l in lines)

    sloppy = ScriptedLLM(lambda m, t, j: ideal_fn(m, t, j) if t else "She is lazy and fell by 41 points.")
    lines = []
    assert asyncio.run(check(sloppy, out=lines.append)) is False
    assert any(l.startswith("FAIL  3") and "label" in l and "41" in l for l in lines)

    lines = []
    assert asyncio.run(check(down_llm(), out=lines.append)) is False and "unreachable" in lines[0]
