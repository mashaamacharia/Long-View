"""The eval runner itself: does it judge correctly, reset between tasks, and fail when it should?"""
import asyncio
import json

import pytest
from sqlalchemy import func, select

import evals.run_evals as er
from app.db.models import LearnerPattern, ProfileChange, Record
from evals.checks import duplicate_truth
from tests.agentkit import ScriptedLLM, _summary_from_sheet, agent_env, ideal_fn  # noqa: F401


@pytest.fixture()
def env(agent_env, monkeypatch):
    monkeypatch.setattr(er, "SessionLocal", agent_env.maker)
    return agent_env


def suite(env, only=None, llm=None):
    return asyncio.run(er.run_suite(env.manager, er.load_tasks(only), llm, log=lambda s: None))


def by_id(report):
    return {r["id"]: r for r in report["results"]}


# ---------- it passes what should pass ----------
def test_all_ten_tasks_pass_with_a_well_behaved_model(env):
    report = suite(env)
    assert report["total"] == 10
    failing = {r["id"]: r["failures"] for r in report["results"] if not r["passed"]}
    assert failing == {} and report["passed"] == 10
    r = by_id(report)
    assert r["EVAL-09"]["state_at_first_stop"] == "waiting_for_teacher" and r["EVAL-09"]["reviews"] == 1
    assert r["EVAL-10"]["final_state"] == "completed"                       # the harness rejected, the run finished
    assert r["EVAL-08"]["final_state"] == "completed" and r["EVAL-08"]["summary"]  # approved both so the summary could be checked
    assert r["EVAL-02"]["documents_read"] >= 1 and r["EVAL-05"]["evidence_passes"] == 0
    assert r["EVAL-07"]["reviews"] == 0 and r["EVAL-05"]["final_state"] == "completed"


def test_each_task_starts_clean_even_when_learners_repeat(env):
    # EVAL-01 and EVAL-09 both use Amina; EVAL-03 and EVAL-10 both use Cynthia. Without a reset the
    # second task would find its finding already in review and never reach the gate.
    report = suite(env, only=["EVAL-01", "EVAL-09", "EVAL-03", "EVAL-10"])
    assert all(r["passed"] for r in report["results"]), [r["failures"] for r in report["results"]]
    with env.maker() as db:
        assert db.scalar(select(func.count()).select_from(ProfileChange)) == 0     # EVAL-10 rejected; EVAL-03 never approved


def test_without_any_model_the_deterministic_floor_still_passes_everything(env):
    env.llm = er.NullLLM()
    env.manager = env.make_manager()
    report = suite(env, llm=env.llm)
    assert report["passed"] == 10, {r["id"]: r["failures"] for r in report["results"] if not r["passed"]}
    assert all(r["fallbacks"] == [] or all("llm_unavailable" in f or "forced" in f for f in r["fallbacks"]) for r in report["results"])
    assert report["provider"] == "none" and report["warmup_seconds"] is None


# ---------- it fails what should fail ----------
def test_a_broken_review_policy_is_caught(env, monkeypatch):
    import app.agent.graph as g
    monkeypatch.setattr(g.policy, "select_candidates", lambda patterns: [])         # nothing ever reaches a teacher
    report = suite(env, only=["EVAL-01", "EVAL-09", "EVAL-07"])
    r = by_id(report)
    assert not r["EVAL-01"]["passed"] and any("flagged_for_review" in f for f in r["EVAL-01"]["failures"])
    assert not r["EVAL-09"]["passed"]
    assert r["EVAL-07"]["passed"]                                                    # Grace is supposed to flag nothing


def test_a_label_in_the_summary_is_caught_even_if_the_verifier_is_off(env, monkeypatch):
    import app.agent.graph as g
    monkeypatch.setattr(g.summ, "verify", lambda *a, **k: [])                       # the verifier is sabotaged...
    env.llm = ScriptedLLM(lambda m, t, j: ideal_fn(m, t, j) if t else _summary_from_sheet(m[1]["content"]) + " Ian is lazy.")
    env.manager = env.make_manager()
    report = suite(env, only=["EVAL-08"])
    assert not report["results"][0]["passed"]
    assert any("must_not_assert_labels" in f for f in report["results"][0]["failures"])   # ...the eval check still sees it


def test_a_profile_write_before_any_decision_is_caught(env, monkeypatch):
    real = er.collect_run_facts

    def tampered(db, run_id):
        f = real(db, run_id)
        f.profile_changes = 1                                                         # as if a write had slipped through
        return f
    monkeypatch.setattr(er, "collect_run_facts", tampered)
    report = suite(env, only=["EVAL-09"])
    r = report["results"][0]
    assert not r["passed"] and any("before any teacher decided" in f for f in r["failures"])


# ---------- ground truth, reset and output ----------
def test_duplicate_truth_comes_from_stored_records(env):
    with env.maker() as db:
        assert duplicate_truth(db, "L1047", None)["removed"] == 3
        english = duplicate_truth(db, "L1047", "English")
        assert 0 <= english["removed"] <= 3 and english["unique_scored"][("English", "writing")] > 10
        assert duplicate_truth(db, "L1048", None)["removed"] == 0


def test_reset_findings_keeps_records_and_notes(env):
    suite(env, only=["EVAL-01"])
    with env.maker() as db:
        before = db.scalar(select(func.count()).select_from(Record))
        assert db.scalar(select(func.count()).select_from(LearnerPattern)) >= 1
        er.reset_findings(db)
        assert db.scalar(select(func.count()).select_from(LearnerPattern)) == 0
        assert db.scalar(select(func.count()).select_from(Record)) == before


def test_load_tasks_filtering():
    assert [t["id"] for t in er.load_tasks(["eval-03", "EVAL-01"])] == ["EVAL-01", "EVAL-03"]
    with pytest.raises(SystemExit):
        er.load_tasks(["EVAL-99"])


def _report(passed=True):
    r = {"id": "EVAL-01", "name": "n", "scenario": "s", "passed": passed, "seconds": 12.3, "llm_calls": 4,
         "fallbacks": [] if passed else ["forced get_evidence(pattern_id=\"PAT-1\")"], "summary_source": "llm",
         "failures": [] if passed else ["agent: flagged_for_review: wanted True, flagged 0"]}
    return {"generated_at": "2026-10-14 12:00 UTC", "provider": "ollama", "model": "qwen", "warmup_seconds": 70.0,
            "passed": int(passed), "total": 1, "total_seconds": 12.3, "results": [r]}


def test_results_are_written_between_markers_without_touching_the_rest(env, tmp_path):
    md = tmp_path / "EVALS.md"
    md.write_text("# Evals\n\nintro\n\n## Known failure\n\nhand-written text\n\n<!-- RESULTS:START -->\nold\n<!-- RESULTS:END -->\n\ntail\n")
    out = tmp_path / "r" / "latest.json"
    er.write_outputs(_report(True), md, out)
    er.write_outputs(_report(False), md, out)                                        # a second run replaces, never duplicates
    text = md.read_text()
    assert text.count("<!-- RESULTS:START -->") == 1 and "old" not in text
    assert "hand-written text" in text and text.rstrip().endswith("tail")
    assert "**FAIL**" in text and "### Failures" in text and "### Fallbacks the agent used" in text
    assert json.loads(out.read_text())["passed"] == 0


def test_markers_are_added_when_missing(tmp_path):
    md = tmp_path / "EVALS.md"
    md.write_text("# Evals\n\nintro\n")
    er.write_outputs(_report(True), md, None)
    t = md.read_text()
    assert t.startswith("# Evals") and "## Results" in t and t.count("RESULTS:START") == 1


def test_warmup_is_timed_and_a_dead_model_is_survivable(env):
    warm = suite(env, only=["EVAL-07"], llm=ScriptedLLM(lambda m, t, j: "OK"))
    assert warm["warmup_seconds"] is not None
    dead = suite(env, only=["EVAL-07"], llm=er.NullLLM.__new__(er.NullLLM))
    assert dead["warmup_seconds"] is None and dead["results"][0]["passed"]
