"""get_evidence, flag_for_teacher_review, the audit wrapper, and the real MCP server layer."""
import asyncio
import json

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.base import Base
from app.db.models import AgentRun, LearnerPattern, TeacherReview, ToolCall
from app.db.seed import seed
from tests.dbutil import make_engine
from data_gen.generate import build_dataset

LABELS = ["lazy", "slow learner", "not an academic"]


@pytest.fixture()
def env(monkeypatch):
    engine = make_engine()
    with Session(engine) as db:
        seed(db, build_dataset())
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    import app.mcp_server.audit as audit
    import app.mcp_server.tools.detect_patterns as dp
    import app.mcp_server.tools.flag_for_teacher_review as fl
    import app.mcp_server.tools.get_evidence as ge
    for mod in (audit, dp, fl, ge):
        monkeypatch.setattr(mod, "SessionLocal", maker)
    return dp, ge, fl, maker


def pid(dp, learner, kind, subtype=None):
    out = dp.detect_patterns(learner)
    return next(p["pattern_id"] for p in out["patterns"] if p["kind"] == kind and (subtype is None or p["subtype"] == subtype))


# ---------- get_evidence ----------
def test_decline_evidence_is_a_sample_with_totals_and_corroboration(env):
    dp, ge, _, _ = env
    out = ge.get_evidence(pid(dp, "L1044", "decline"))
    json.dumps(out)
    assert out["ok"] and out["pattern"]["kind"] == "decline" and out["pattern"]["status"] == "proposed"
    assert out["records"]["total"] > 12 and out["records"]["shown"] == 12
    terms = [r["term"] for r in out["records"]["items"]]
    assert terms == sorted(terms) and terms[0] == "2023-T1" and terms[-1] == "2026-T2"  # earliest and latest
    assert out["attendance"]["total"] == 11 and out["attendance"]["items"][-1][1] < 85
    assert {o["sentiment"] for o in out["observations"]["items"]} == {"concern"}
    assert out["term_means"][0][0] == "2023-T1"
    assert len(json.dumps(out)) < 8000  # fits a small model's context


def test_anomaly_evidence_is_the_flagged_record_plus_its_same_term_context(env):
    dp, ge, _, _ = env
    out = ge.get_evidence(pid(dp, "L1043", "anomaly"), max_records=1)
    items = out["records"]["items"]
    assert out["records"]["total"] == 1 and len(items) == 1                # not the whole series
    assert items[0]["term"] == "2025-T2" and items[0]["pct"] < 30
    assert items[0]["title"].startswith("Science end-of-term test")
    texts = " ".join(o["text"] for o in out["observations"]["items"])
    assert "Absent for the assessment week" in texts                       # the context lives in the evidence
    assert dict(map(tuple, out["attendance"]["items"]))["2025-T2"] == 84.0


def test_label_notes_are_withheld_but_counted(env):
    dp, ge, _, _ = env
    out = ge.get_evidence(pid(dp, "L1049", "conflict", "label_language"))
    blob = json.dumps(out).lower()
    assert not [w for w in LABELS if w in blob]
    obs = out["observations"]["items"]
    assert len(obs) == 3 and all(o["characterising_language"] for o in obs)
    assert all("withheld" in o["text"] for o in obs)
    # the strength pattern for the same learner still carries ordinary, usable observations
    strength = ge.get_evidence(pid(dp, "L1049", "strength"))
    assert any("fair test" in o["text"] for o in strength["observations"]["items"])


def test_get_evidence_unknown_pattern_and_clamping(env):
    dp, ge, _, _ = env
    assert ge.get_evidence("PAT-NOPE")["ok"] is False
    out = ge.get_evidence(pid(dp, "L1042", "strength"), max_records=10_000, max_observations=0)
    assert out["records"]["shown"] <= 50 and out["observations"]["shown"] >= 1


# ---------- flag_for_teacher_review ----------
def test_flag_creates_pending_review_and_marks_pattern(env):
    dp, _, fl, maker = env
    p = pid(dp, "L1044", "decline")
    out = fl.flag_for_teacher_review("L1044", p, "Reading comprehension fell over five terms; attendance also slipped.")
    assert out["ok"] and out["status"] == "pending" and out["already_pending"] is False
    assert "No profile change" in out["message"]
    with maker() as db:
        assert db.get(LearnerPattern, p).status == "in_review"
        rev = db.get(TeacherReview, out["review_id"])
        assert rev.status == "pending" and rev.learner_id == "L1044" and "attendance" in rev.reason
    # a later detection run must not disturb a pattern that is in review
    assert next(x for x in dp.detect_patterns("L1044")["patterns"] if x["pattern_id"] == p)["status"] == "in_review"


def test_flag_is_idempotent_while_pending(env):
    dp, _, fl, maker = env
    p = pid(dp, "L1042", "strength")
    a = fl.flag_for_teacher_review("L1042", p, "Sustained improvement in problem solving.")
    b = fl.flag_for_teacher_review("L1042", p, "Same finding again.")
    assert b["ok"] and b["already_pending"] is True and b["review_id"] == a["review_id"]
    with maker() as db:
        assert db.scalar(select(func.count()).select_from(TeacherReview)) == 1


def test_flag_after_teacher_asks_for_more_evidence_makes_a_new_review(env):
    dp, _, fl, maker = env
    p = pid(dp, "L1042", "strength")
    first = fl.flag_for_teacher_review("L1042", p, "Sustained improvement.")
    with maker() as db:
        db.get(TeacherReview, first["review_id"]).status = "more_evidence"
        db.commit()
    second = fl.flag_for_teacher_review("L1042", p, "Added the project report as further evidence.")
    assert second["ok"] and second["review_id"] != first["review_id"] and second["already_pending"] is False


def test_flag_refuses_insufficient_findings_and_creates_nothing(env):
    dp, _, fl, maker = env
    p = pid(dp, "L1046", "insufficient")
    out = fl.flag_for_teacher_review("L1046", p, "Please review.")
    assert out["ok"] is False and "insufficient" in out["error"]
    with maker() as db:
        assert db.scalar(select(func.count()).select_from(TeacherReview)) == 0
        assert db.get(LearnerPattern, p).status == "proposed"


def test_flag_input_validation(env):
    dp, _, fl, maker = env
    p = pid(dp, "L1044", "decline")
    assert fl.flag_for_teacher_review("L1044", p, "   ")["ok"] is False                       # empty reason
    assert fl.flag_for_teacher_review("NOPE", p, "x")["ok"] is False                        # unknown learner
    assert fl.flag_for_teacher_review("L1044", "PAT-NOPE", "x")["ok"] is False              # unknown pattern
    assert "different learner" in fl.flag_for_teacher_review("L1042", p, "x")["error"]      # wrong learner
    assert "run_id" in fl.flag_for_teacher_review("L1044", p, "x", run_id="RUN-404")["error"]
    with maker() as db:
        assert db.scalar(select(func.count()).select_from(TeacherReview)) == 0


@pytest.mark.parametrize("status", ["approved", "rejected"])
def test_flag_does_not_reopen_decided_patterns(env, status):
    dp, _, fl, maker = env
    p = pid(dp, "L1044", "decline")
    with maker() as db:
        db.get(LearnerPattern, p).status = status
        db.commit()
    out = fl.flag_for_teacher_review("L1044", p, "Trying again.")
    assert out["ok"] is False and status in out["error"]


def test_flag_records_a_valid_run(env):
    dp, _, fl, maker = env
    with maker() as db:
        db.add(AgentRun(id="RUN-001", learner_id="L1044", request="review"))
        db.commit()
    out = fl.flag_for_teacher_review("L1044", pid(dp, "L1044", "decline"), "Needs attention.", run_id="RUN-001")
    assert out["ok"]
    with maker() as db:
        assert db.get(TeacherReview, out["review_id"]).run_id == "RUN-001"


# ---------- the real MCP server layer: schemas, argument handling, audit trail ----------
def test_server_registers_all_tools_with_expected_parameters(env):
    from app.mcp_server.server import mcp
    tools = {t.name: t for t in asyncio.run(mcp.list_tools())}
    assert set(tools) == {"get_learner_timeline", "detect_patterns", "get_evidence",
                          "flag_for_teacher_review", "update_learner_profile"}
    props = lambda n: set(tools[n].inputSchema["properties"])  # noqa: E731
    assert {"pattern_id", "max_records"} <= props("get_evidence")
    assert {"learner_id", "pattern_id", "reason"} <= props("flag_for_teacher_review")
    assert tools["flag_for_teacher_review"].inputSchema["required"] == ["learner_id", "pattern_id", "reason"]


def test_calls_through_the_server_are_audited_including_refusals(env):
    from app.mcp_server.server import mcp
    dp, _, _, maker = env
    with maker() as db:
        db.add(AgentRun(id="RUN-007", learner_id="L1043", request="review"))
        db.commit()

    async def go():
        await mcp.call_tool("detect_patterns", {"learner_id": "L1043", "run_id": "RUN-007"})
        p = pid(dp, "L1043", "anomaly")
        await mcp.call_tool("get_evidence", {"pattern_id": p, "run_id": "RUN-007"})
        await mcp.call_tool("flag_for_teacher_review", {"learner_id": "L1043", "pattern_id": p, "reason": "  ", "run_id": "RUN-007"})
        await mcp.call_tool("flag_for_teacher_review", {"learner_id": "L1043", "pattern_id": p, "reason": "x", "run_id": "RUN-404"})

    asyncio.run(go())
    with maker() as db:
        rows = db.scalars(select(ToolCall).order_by(ToolCall.id)).all()
    names = [r.tool_name for r in rows]
    assert names[0] == "detect_patterns" and names.count("flag_for_teacher_review") == 2 and "get_evidence" in names
    assert rows[0].run_id == "RUN-007" and rows[0].tool_input["learner_id"] == "L1043" and rows[0].tool_output["ok"] is True
    refused = [r for r in rows if r.tool_name == "flag_for_teacher_review"]
    assert all(r.error for r in refused)                       # refusals are recorded with their reason
    assert refused[1].run_id is None                           # unknown run id: row kept, FK not violated
