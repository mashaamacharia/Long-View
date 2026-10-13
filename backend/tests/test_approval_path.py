"""The safety path end to end: flag -> teacher decision (API) -> approval-gated profile write."""
import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Approval, LearnerPattern, ProfileChange, TeacherReview, ToolCall
from app.db.seed import seed
from app.db.session import get_db
from app.main import app
from data_gen.generate import build_dataset

GOOD = "Problem solving improved steadily over 11 terms, from about 59% to about 79%."


@pytest.fixture()
def env(monkeypatch):
    # TestClient serves requests on another thread; a shared single connection keeps one in-memory DB for all
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db, build_dataset())
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    import app.mcp_server.audit as audit
    import app.mcp_server.tools.detect_patterns as dp
    import app.mcp_server.tools.flag_for_teacher_review as fl
    import app.mcp_server.tools.get_evidence as ge
    import app.mcp_server.tools.update_learner_profile as up
    for mod in (audit, dp, fl, ge, up):
        monkeypatch.setattr(mod, "SessionLocal", maker)

    def override():
        with maker() as db:
            yield db

    app.dependency_overrides[get_db] = override
    yield type("Env", (), {"dp": dp, "fl": fl, "ge": ge, "up": up, "maker": maker, "api": TestClient(app)})
    app.dependency_overrides.clear()


def flagged(env, learner, kind, subtype=None, reason="Needs a teacher's eyes."):
    out = env.dp.detect_patterns(learner)
    pid = next(p["pattern_id"] for p in out["patterns"] if p["kind"] == kind and (subtype is None or p["subtype"] == subtype))
    review = env.fl.flag_for_teacher_review(learner, pid, reason)
    assert review["ok"], review
    return pid, review["review_id"]


def decide(env, review_id, decision="approved", teacher="T-014", comment=None):
    return env.api.post(f"/api/reviews/{review_id}/decision",
                        json={"teacher_id": teacher, "decision": decision, "comment": comment})


def count(env, model):
    with env.maker() as db:
        return db.scalar(select(func.count()).select_from(model))


# ---------- the teacher decision API ----------
def test_pending_review_is_listed_with_learner_and_finding(env):
    flagged(env, "L1044", "decline")
    rows = env.api.get("/api/reviews").json()
    assert len(rows) == 1 and rows[0]["learner"]["full_name"] == "Cynthia Achieng"
    assert rows[0]["pattern"]["kind"] == "decline" and rows[0]["status"] == "pending"
    assert env.api.get("/api/reviews?status=approved").json() == []
    assert env.api.get("/api/reviews?status=bogus").status_code == 422


def test_teacher_sees_original_notes_while_the_agent_tool_does_not(env):
    pid, rid = flagged(env, "L1049", "conflict", "label_language")
    detail = env.api.get(f"/api/reviews/{rid}").json()
    notes = detail["evidence"]["observations"]["items"]
    assert len(notes) == 3 and all(n["characterising_language"] for n in notes)
    assert any("Lazy in class" in n["text"] for n in notes)                       # teacher reads the original
    agent_view = env.ge.get_evidence(pid)["observations"]["items"]
    assert all("withheld" in n["text"] for n in agent_view)                       # agent does not
    assert detail["evidence"]["records"]["shown"] == detail["evidence"]["records"]["total"]  # no sampling


@pytest.mark.parametrize("decision,pattern_status", [("approved", "approved"), ("rejected", "rejected"), ("more_evidence", "proposed")])
def test_decision_records_approval_and_moves_pattern(env, decision, pattern_status):
    pid, rid = flagged(env, "L1044", "decline")
    r = decide(env, rid, decision, comment="Looked at the term averages.")
    assert r.status_code == 200 and r.json()["pattern_status"] == pattern_status and r.json()["approval_id"].startswith("APP-")
    with env.maker() as db:
        a = db.get(Approval, r.json()["approval_id"])
        assert a.decision == decision and a.teacher_id == "T-014" and a.comment
        assert db.get(TeacherReview, rid).status == decision and db.get(LearnerPattern, pid).status == pattern_status


def test_decisions_cannot_be_repeated_or_changed(env):
    _, rid = flagged(env, "L1044", "decline")
    assert decide(env, rid, "rejected").status_code == 200
    again = decide(env, rid, "approved")
    assert again.status_code == 409 and "already" in again.json()["detail"]
    assert count(env, Approval) == 1


def test_decision_input_validation(env):
    _, rid = flagged(env, "L1044", "decline")
    assert decide(env, rid, "maybe").status_code == 422
    assert decide(env, rid, "approved", teacher="").status_code == 422
    assert env.api.post(f"/api/reviews/{rid}/decision", json={"teacher_id": "T-1", "decision": "approved", "x": 1}).status_code == 422
    assert decide(env, 9999, "approved").status_code == 404
    assert env.api.get("/api/reviews/9999").status_code == 404
    assert count(env, Approval) == 0


def test_more_evidence_lets_the_agent_refresh_and_flag_again(env):
    pid, rid = flagged(env, "L1044", "decline")
    decide(env, rid, "more_evidence", comment="What about writing?")
    refreshed = env.dp.detect_patterns("L1044")                      # unfrozen again, so it re-runs
    assert next(p for p in refreshed["patterns"] if p["pattern_id"] == pid)["status"] == "proposed"
    second = env.fl.flag_for_teacher_review("L1044", pid, "Added a writing comparison.")
    assert second["ok"] and second["review_id"] != rid and second["already_pending"] is False


# ---------- the gate: update_learner_profile ----------
def test_EVAL_09_no_approval_no_write_even_when_the_user_is_in_a_hurry(env):
    pid, _ = flagged(env, "L1042", "strength")
    for bad in (None, "", "APP-00000001", "APP-FFFFFFFF"):          # missing, empty, fabricated
        out = env.up.update_learner_profile("L1042", pid, GOOD, approval_id=bad)
        assert out["ok"] is False
        if not bad:  # the agent is told what to do instead, not just that it failed
            assert "requires a teacher approval_id" in out["error"] and "flag_for_teacher_review" in out["error"]
    assert count(env, ProfileChange) == 0


def test_a_pending_review_does_not_unlock_anything(env):
    pid, rid = flagged(env, "L1042", "strength")
    with env.maker() as db:   # even guessing the review id as an approval id fails
        assert db.get(Approval, str(rid)) is None
    assert env.up.update_learner_profile("L1042", pid, GOOD, approval_id=str(rid))["ok"] is False
    assert count(env, ProfileChange) == 0


@pytest.mark.parametrize("decision", ["rejected", "more_evidence"])
def test_EVAL_10_only_an_approval_unlocks_the_write(env, decision):
    pid, rid = flagged(env, "L1044", "decline")
    approval = decide(env, rid, decision).json()["approval_id"]
    out = env.up.update_learner_profile("L1044", pid, "Reading comprehension fell.", approval_id=approval)
    assert out["ok"] is False and decision in out["error"]
    assert count(env, ProfileChange) == 0


def test_approved_finding_is_written_once_and_replay_is_harmless(env):
    pid, rid = flagged(env, "L1042", "strength")
    approval = decide(env, rid, "approved").json()["approval_id"]
    first = env.up.update_learner_profile("L1042", pid, GOOD, approval_id=approval)
    assert first["ok"] and first["already_applied"] is False and first["approval_id"] == approval
    replay = env.up.update_learner_profile("L1042", pid, "Different wording.", approval_id=approval)
    assert replay["ok"] and replay["already_applied"] is True and replay["change_id"] == first["change_id"]
    assert count(env, ProfileChange) == 1
    entries = env.api.get("/api/learners/L1042/profile").json()
    assert len(entries) == 1 and entries[0]["summary"] == GOOD and entries[0]["pattern"]["pattern_id"] == pid


def test_profile_is_empty_until_a_teacher_approves(env):
    assert env.api.get("/api/learners/L1042/profile").json() == []
    assert env.api.get("/api/learners/NOPE/profile").status_code == 404


def test_an_approval_is_bound_to_its_pattern_and_learner(env):
    pid_a, rid_a = flagged(env, "L1042", "strength")
    pid_b, _ = flagged(env, "L1044", "decline")
    approval = decide(env, rid_a, "approved").json()["approval_id"]
    wrong_pattern = env.up.update_learner_profile("L1044", pid_b, "Reading fell.", approval_id=approval)
    wrong_learner = env.up.update_learner_profile("L1044", pid_a, GOOD, approval_id=approval)
    assert wrong_pattern["ok"] is False and "different pattern" in wrong_pattern["error"]
    assert wrong_learner["ok"] is False
    assert count(env, ProfileChange) == 0


def test_defence_in_depth_review_for_another_learner_cannot_unlock(env):
    pid, rid = flagged(env, "L1042", "strength")
    approval = decide(env, rid, "approved").json()["approval_id"]
    with env.maker() as db:   # simulate corrupted or tampered data: the review now points at someone else
        db.get(TeacherReview, rid).learner_id = "L1044"
        db.commit()
    out = env.up.update_learner_profile("L1042", pid, GOOD, approval_id=approval)
    assert out["ok"] is False and "different learner" in out["error"]
    assert count(env, ProfileChange) == 0


def test_label_language_is_refused_but_the_approval_survives(env):
    pid, rid = flagged(env, "L1049", "strength")
    approval = decide(env, rid, "approved").json()["approval_id"]
    bad = env.up.update_learner_profile("L1049", pid, "Ian is a slow learner who improved in practicals.", approval_id=approval)
    assert bad["ok"] is False and "characterising" in bad["error"] and count(env, ProfileChange) == 0
    assert env.up.update_learner_profile("L1049", pid, "   ", approval_id=approval)["ok"] is False
    good = env.up.update_learner_profile("L1049", pid, "Practical work rose from about 50% to about 75% over 11 terms.", approval_id=approval)
    assert good["ok"] and count(env, ProfileChange) == 1


def test_tampered_pattern_state_blocks_the_write(env):
    pid, rid = flagged(env, "L1042", "strength")
    approval = decide(env, rid, "approved").json()["approval_id"]
    with env.maker() as db:
        db.get(LearnerPattern, pid).status = "in_review"
        db.commit()
    assert env.up.update_learner_profile("L1042", pid, GOOD, approval_id=approval)["ok"] is False


def test_unknown_learner_or_pattern(env):
    assert env.up.update_learner_profile("NOPE", "PAT-X", GOOD, approval_id="APP-1")["ok"] is False
    assert env.up.update_learner_profile("L1042", "PAT-X", GOOD, approval_id="APP-1")["ok"] is False


# ---------- the whole journey through the real MCP layer, with the audit trail ----------
def test_full_journey_through_the_server_and_audit_trail(env):
    from app.mcp_server.server import mcp
    out = env.dp.detect_patterns("L1042")
    pid = out["patterns"][0]["pattern_id"]

    async def call(name, args):
        await mcp.call_tool(name, args)

    asyncio.run(call("flag_for_teacher_review", {"learner_id": "L1042", "pattern_id": pid, "reason": "Sustained growth."}))
    asyncio.run(call("update_learner_profile", {"learner_id": "L1042", "pattern_id": pid, "summary": GOOD}))   # refused: no approval
    assert count(env, ProfileChange) == 0

    rid = env.api.get("/api/reviews").json()[0]["review_id"]
    approval = decide(env, rid, "approved", comment="Agreed with the evidence.").json()["approval_id"]
    asyncio.run(call("update_learner_profile", {"learner_id": "L1042", "pattern_id": pid, "summary": GOOD, "approval_id": approval}))
    assert count(env, ProfileChange) == 1

    with env.maker() as db:
        rows = db.scalars(select(ToolCall).where(ToolCall.tool_name == "update_learner_profile").order_by(ToolCall.id)).all()
    assert len(rows) == 2 and all(r.approval_required for r in rows)
    assert rows[0].error and "approval_id" in rows[0].error          # the refusal is on the record
    assert rows[1].error is None and rows[1].tool_output["ok"] is True
    assert rows[1].tool_input["approval_id"] == approval
